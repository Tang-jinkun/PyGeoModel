import json
import math
import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import numpy
from pyproj import Transformer
from shapely.geometry import box, mapping

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.radar import CoverageMetrics, CoverageModelMetadata, CoverageOutputFile, CoverageOutputs, CoverageRequest
from app.services.dem_store import find_dem_file
from app.services.coverage_model import (
    PreparedCoverageDem,
    default_simplify_tolerance,
    prepare_coverage_dem,
    vectorize_visible_viewshed,
)
from app.services.geometry import make_range_geometry, project_geometry
from app.services.output_files import OUTPUT_FILENAMES, describe_output_files, list_task_output_files
from app.services.task_store import mark_failed, mark_finished, mark_running


def run_coverage_task(task_id: str, payload: CoverageRequest) -> None:
    try:
        mark_running(task_id, "Preparing DEM and projection.", 15)
        output_dir = settings.outputs_dir / task_id
        output_dir.mkdir(parents=True, exist_ok=True)
        staging_dir = output_dir / f".staging-{uuid4().hex}"
        staging_dir.mkdir(parents=True, exist_ok=False)

        dem_path = find_dem_file(payload.dem_id)
        projected_dem = staging_dir / "dem_projected.tif"

        try:
            prepared = prepare_coverage_dem(dem_path, projected_dem, payload)

            mark_running(task_id, "Running gdal_viewshed (NORMAL).", 35)
            viewshed = staging_dir / "viewshed.tif"
            gdal_command = _run_gdal_viewshed(
                projected_dem, viewshed, prepared.radar_x, prepared.radar_y, payload, mode="NORMAL"
            )

            mark_running(task_id, "Running gdal_viewshed (GROUND).", 50)
            min_visible_height = staging_dir / "min_visible_height.tif"
            _run_gdal_viewshed(
                projected_dem, min_visible_height, prepared.radar_x, prepared.radar_y, payload, mode="GROUND"
            )

            mark_running(task_id, "Generating height layers and voxels.", 70)
            _generate_height_layers(staging_dir, min_visible_height, prepared, payload)
            _generate_voxels(staging_dir, min_visible_height, prepared, payload)

            mark_running(task_id, "Vectorizing viewshed outputs.", 85)
            outputs, output_files, metrics, model, warnings = _write_vector_outputs(
                task_id,
                staging_dir,
                output_dir,
                prepared,
                payload,
                viewshed,
                min_visible_height,
                gdal_command,
            )
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)
        mark_finished(
            task_id,
            metrics=metrics,
            outputs=outputs,
            output_files=output_files,
            model=model,
            warnings=warnings,
        )
    except Exception as exc:
        mark_failed(task_id, str(exc))


def _run_gdal_viewshed(
    dem: Path, viewshed: Path, radar_x: float, radar_y: float, payload: CoverageRequest, *, mode: str
) -> list[str]:
    if shutil.which("gdal_viewshed") is None:
        raise AppError("GDAL_VIEWSHED_NOT_FOUND", "gdal_viewshed command is not available.", status_code=500)

    command = [
        "gdal_viewshed",
        "-ox",
        str(radar_x),
        "-oy",
        str(radar_y),
        "-oz",
        str(payload.radar.height_m),
        "-tz",
        str(payload.target.height_m),
        "-md",
        str(payload.coverage.max_range_m),
        "-om",
        mode,
    ]

    if payload.advanced.use_curvature:
        command.extend(["-cc", str(payload.advanced.curvature_coeff)])

    command.extend([str(dem), str(viewshed)])
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AppError("GDAL_VIEWSHED_FAILED", result.stderr.strip() or "gdal_viewshed failed.", status_code=500)
    return command


def _generate_height_layers(
    staging_dir: Path,
    min_visible_height: Path,
    prepared: PreparedCoverageDem,
    payload: CoverageRequest,
) -> None:
    import rasterio
    from rasterio.features import shapes

    height_layers = payload.advanced.height_layers_m or [0, 100, 300, 500, 1000, 2000, 3000]
    with rasterio.open(min_visible_height) as src:
        data = src.read(1)
        transform = src.transform

    range_geom = make_range_geometry(
        prepared.radar_x,
        prepared.radar_y,
        payload.coverage.max_range_m,
        payload.coverage.scan_mode,
        payload.coverage.azimuth_deg,
        payload.coverage.beam_width_deg,
    )
    transformer = Transformer.from_crs(f"EPSG:{prepared.target_epsg}", "EPSG:4326", always_xy=True)
    manifest = {"height_layers": []}
    for height in height_layers:
        visible_mask = data <= height
        geometries = []
        for geom, value in shapes(visible_mask.astype(numpy.uint8), mask=visible_mask, transform=transform):
            if value > 0:
                geometries.append(geom)

        geojson_path = staging_dir / f"visible_h_{int(height)}.geojson"
        features = []
        if geometries:
            from shapely.geometry import shape as shp_shape
            from shapely.ops import unary_union

            union = unary_union([shp_shape(g) for g in geometries])
            clipped = union.intersection(range_geom)
            if not clipped.is_empty:
                wgs84 = project_geometry(clipped, transformer)
                features.append({"type": "Feature", "properties": {"height_m": height}, "geometry": mapping(wgs84)})

        _write_feature_collection_geojson(geojson_path, features)
        manifest["height_layers"].append({"height_m": height, "filename": geojson_path.name})

    manifest_path = staging_dir / "height_layers_manifest.json"
    _write_json_atomic(manifest_path, manifest)


def _generate_voxels(
    staging_dir: Path,
    min_visible_height: Path,
    prepared: PreparedCoverageDem,
    payload: CoverageRequest,
) -> None:
    import rasterio

    grid_size = payload.advanced.voxel_grid_size
    vertical_levels = payload.advanced.voxel_vertical_levels
    max_height = payload.advanced.voxel_max_height_m
    max_elevation = payload.advanced.max_elevation_deg

    with rasterio.open(min_visible_height) as src:
        data = src.read(1)
        transform = src.transform
        height, width = data.shape

    # Sample grid
    x_indices = numpy.linspace(0, width - 1, grid_size, dtype=numpy.int32)
    y_indices = numpy.linspace(0, height - 1, grid_size, dtype=numpy.int32)
    transformer = Transformer.from_crs(f"EPSG:{prepared.target_epsg}", "EPSG:4326", always_xy=True)

    points = []
    for yi in y_indices:
        for xi in x_indices:
            yi_int = int(round(yi))
            xi_int = int(round(xi))
            if not (0 <= yi_int < height and 0 <= xi_int < width):
                continue
            min_h = data[yi_int, xi_int]
            if not numpy.isfinite(min_h) or min_h < 0:
                continue
            # Convert pixel to projected coordinates
            x_proj = transform.c + xi_int * transform.a
            y_proj = transform.f + yi_int * transform.e
            # Check distance from radar
            dx = x_proj - prepared.radar_x
            dy = y_proj - prepared.radar_y
            dist = math.hypot(dx, dy)
            if dist > payload.coverage.max_range_m:
                continue
            # Check azimuth for sector scan
            if payload.coverage.scan_mode == "sector":
                az = (math.degrees(math.atan2(dx, dy)) + 360) % 360
                half = payload.coverage.beam_width_deg / 2
                center = payload.coverage.azimuth_deg % 360
                delta = abs((az - center + 180) % 360 - 180)
                if delta > half:
                    continue
            # Check elevation angle
            if max_elevation > 0 and dist > 0:
                elev = math.degrees(math.atan(max_height / dist))
                if elev > max_elevation:
                    max_h_at_dist = dist * math.tan(math.radians(max_elevation))
                else:
                    max_h_at_dist = max_height
            else:
                max_h_at_dist = max_height

            for level in range(vertical_levels):
                z = (level + 0.5) * (max_h_at_dist / vertical_levels)
                if z >= min_h:
                    clearance = z - min_h
                    lon, lat = transformer.transform(x_proj, y_proj)
                    points.append((lon, lat, z, clearance))

    # Write binary: each point is 4 x float32
    voxel_path = staging_dir / "voxel_points.bin"
    array = numpy.array(points, dtype=numpy.float32).flatten()
    with open(voxel_path, "wb") as f:
        f.write(array.tobytes())

    # Write manifest
    manifest = {
        "grid_size": grid_size,
        "vertical_levels": vertical_levels,
        "max_height_m": max_height,
        "max_elevation_deg": max_elevation,
        "point_count": len(points),
        "point_format": "float32",
        "fields": ["lon", "lat", "z_agl_m", "clearance_m"],
        "bytes_per_point": 16,
    }
    _write_json_atomic(staging_dir / "voxel_manifest.json", manifest)


def _write_vector_outputs(
    task_id: str,
    staging_dir: Path,
    output_dir: Path,
    prepared: PreparedCoverageDem,
    payload: CoverageRequest,
    viewshed: Path,
    min_visible_height: Path,
    gdal_command: list[str],
) -> tuple[CoverageOutputs, list[CoverageOutputFile], CoverageMetrics, CoverageModelMetadata, list[str]]:
    range_geom = make_range_geometry(
        prepared.radar_x,
        prepared.radar_y,
        payload.coverage.max_range_m,
        payload.coverage.scan_mode,
        payload.coverage.azimuth_deg,
        payload.coverage.beam_width_deg,
    )
    transformer = Transformer.from_crs(f"EPSG:{prepared.target_epsg}", "EPSG:4326", always_xy=True)
    range_wgs84 = project_geometry(range_geom, transformer)
    visible_geom = vectorize_visible_viewshed(viewshed)
    visible_clipped = visible_geom.intersection(range_geom)
    blocked_geom = range_geom.difference(visible_clipped)

    tolerance = default_simplify_tolerance(prepared.resolution_m, payload.advanced.output_simplify_tolerance_m)
    if tolerance > 0:
        visible_clipped = visible_clipped.simplify(tolerance, preserve_topology=True)
        blocked_geom = blocked_geom.simplify(tolerance, preserve_topology=True)

    range_geojson = staging_dir / "radar_range.geojson"
    visible_geojson = staging_dir / "visible.geojson"
    blocked_geojson = staging_dir / "blocked.geojson"
    model_metadata_json = staging_dir / "model_metadata.json"
    output_manifest_json = staging_dir / "output_manifest.json"

    _write_feature_collection(range_geojson, range_wgs84, {"kind": "theoretical_range"})
    _write_feature_collection(
        visible_geojson,
        project_geometry(visible_clipped, transformer) if not visible_clipped.is_empty else visible_clipped,
        {"kind": "visible"},
    )
    _write_feature_collection(
        blocked_geojson,
        project_geometry(blocked_geom, transformer) if not blocked_geom.is_empty else blocked_geom,
        {"kind": "blocked"},
    )

    metrics = CoverageMetrics(
        theoretical_area_m2=range_geom.area,
        visible_area_m2=visible_clipped.area,
        blocked_area_m2=blocked_geom.area,
        blocked_ratio=blocked_geom.area / range_geom.area if range_geom.area > 0 else 0,
    )
    outputs = CoverageOutputs(
        viewshed_tif=f"/outputs/{task_id}/{viewshed.name}",
        visible_geojson=f"/outputs/{task_id}/{visible_geojson.name}",
        blocked_geojson=f"/outputs/{task_id}/{blocked_geojson.name}",
        range_geojson=f"/outputs/{task_id}/{range_geojson.name}",
        model_metadata_json=f"/outputs/{task_id}/{model_metadata_json.name}",
        output_manifest_json=f"/outputs/{task_id}/{output_manifest_json.name}",
        min_visible_height_tif=f"/outputs/{task_id}/{min_visible_height.name}",
        voxel_manifest_json=f"/outputs/{task_id}/voxel_manifest.json",
        voxel_points_bin=f"/outputs/{task_id}/voxel_points.bin",
        height_layers_manifest_json=f"/outputs/{task_id}/height_layers_manifest.json",
    )
    height_layers = payload.advanced.height_layers_m or [0, 100, 300, 500, 1000, 2000, 3000]
    model = CoverageModelMetadata(
        target_epsg=prepared.target_epsg,
        radar_projected_xy=[prepared.radar_x, prepared.radar_y],
        projected_dem_bounds=[
            prepared.projected_bounds.left,
            prepared.projected_bounds.bottom,
            prepared.projected_bounds.right,
            prepared.projected_bounds.top,
        ],
        projected_dem_resolution_m=[prepared.resolution_m[0], prepared.resolution_m[1]],
        max_range_m=payload.coverage.max_range_m,
        scan_mode=payload.coverage.scan_mode,
        azimuth_deg=payload.coverage.azimuth_deg,
        beam_width_deg=payload.coverage.beam_width_deg,
        simplify_tolerance_m=tolerance,
        gdal_viewshed_command=gdal_command,
        voxel_grid_size=payload.advanced.voxel_grid_size,
        voxel_vertical_levels=payload.advanced.voxel_vertical_levels,
        voxel_max_height_m=payload.advanced.voxel_max_height_m,
        max_elevation_deg=payload.advanced.max_elevation_deg,
        height_layers_m=height_layers,
    )
    warnings = _build_model_warnings(prepared, range_geom)
    _write_json_atomic(
        model_metadata_json,
        {
            "model": model.model_dump(),
            "metrics": metrics.model_dump(),
            "warnings": warnings,
        },
    )
    output_paths = {kind: staging_dir / filename for kind, filename in OUTPUT_FILENAMES.items()}
    _write_output_manifest(output_manifest_json, [], metrics, model, warnings)
    manifest_files = describe_output_files(task_id, output_paths)
    _write_output_manifest(output_manifest_json, manifest_files, metrics, model, warnings)
    _ensure_staged_outputs_exist(staging_dir)
    _commit_staged_outputs(staging_dir, output_dir)
    output_files = list_task_output_files(task_id)
    _ensure_finished_outputs_exist(output_files)
    return outputs, output_files, metrics, model, warnings


def _write_output_manifest(
    path: Path,
    output_files: list[CoverageOutputFile],
    metrics: CoverageMetrics,
    model: CoverageModelMetadata,
    warnings: list[str],
) -> None:
    _write_json_atomic(
        path,
        {
            "files": [item.model_dump() for item in output_files],
            "metrics": metrics.model_dump(),
            "model": model.model_dump(),
            "warnings": warnings,
        },
    )


def _build_model_warnings(prepared: PreparedCoverageDem, range_geom) -> list[str]:
    warnings: list[str] = []
    dem_bounds_geom = box(
        prepared.projected_bounds.left,
        prepared.projected_bounds.bottom,
        prepared.projected_bounds.right,
        prepared.projected_bounds.top,
    )
    if not dem_bounds_geom.contains(range_geom):
        warnings.append("Requested radar range is not fully covered by the available DEM extent.")
    return warnings


def _write_feature_collection(path: Path, geometry, properties: dict | None = None) -> None:
    features = []
    if geometry is not None and not geometry.is_empty:
        features.append({"type": "Feature", "properties": properties or {}, "geometry": mapping(geometry)})
    _write_json_atomic(path, {"type": "FeatureCollection", "features": features})


def _write_feature_collection_geojson(path: Path, features: list) -> None:
    _write_json_atomic(path, {"type": "FeatureCollection", "features": features})


def _ensure_finished_outputs_exist(output_files: list[CoverageOutputFile]) -> None:
    missing = [item.kind for item in output_files if not item.exists or item.size_bytes is None or item.size_bytes <= 0]
    if missing:
        raise AppError(
            "OUTPUT_INCOMPLETE",
            f"Coverage task outputs are incomplete: {', '.join(missing)}.",
            status_code=500,
        )


def _ensure_staged_outputs_exist(staging_dir: Path) -> None:
    missing = [
        kind
        for kind, filename in OUTPUT_FILENAMES.items()
        if not (staging_dir / filename).exists() or (staging_dir / filename).stat().st_size <= 0
    ]
    if missing:
        raise AppError(
            "OUTPUT_INCOMPLETE",
            f"Coverage task staged outputs are incomplete: {', '.join(missing)}.",
            status_code=500,
        )


def _commit_staged_outputs(staging_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename in OUTPUT_FILENAMES.values():
        source = staging_dir / filename
        destination = output_dir / filename
        source.replace(destination)
    for source in staging_dir.glob("visible_h_*.geojson"):
        source.replace(output_dir / source.name)
    _fsync_directory(output_dir)


def _write_json_atomic(path: Path, payload: dict) -> None:
    _write_text_atomic(path, json.dumps(payload, ensure_ascii=False, indent=2))


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        temp_path.replace(path)
        _fsync_directory(path.parent)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
