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
from app.schemas.radar import (
    BeamClipProfile,
    CoverageDiagnostics,
    CoverageMetrics,
    CoverageModelMetadata,
    CoverageOutputFile,
    CoverageOutputs,
    CoverageRequest,
)
from app.services.dem_store import find_dem_file
from app.services.coverage_model import (
    PreparedCoverageDem,
    WARN_DEM_COVERAGE_RATIO,
    default_simplify_tolerance,
    prepare_coverage_dem,
)
from app.services.coverage_range import effective_max_range as _effective_max_range
from app.services.geometry import make_range_geometry, project_geometry
from app.services.output_files import OUTPUT_FILENAMES, describe_output_files, list_task_output_files
from app.services.task_store import mark_failed, mark_finished, mark_running

COVERAGE_MASK_ROW_CHUNK_SIZE = 256


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
            _generate_clipped_volume(staging_dir, min_visible_height, prepared, payload)

            mark_running(task_id, "Vectorizing viewshed outputs.", 85)
            outputs, output_files, metrics, model, diagnostics, warnings = _write_vector_outputs(
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
            diagnostics=diagnostics,
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


def _coverage_masks(
    data,
    transform,
    radar_x: float,
    radar_y: float,
    payload: CoverageRequest,
    target_height_m: float,
    effective_range_m: float,
    analysis_domain=None,
):
    height, width = data.shape
    domain_mask = (
        numpy.asarray(analysis_domain, dtype=bool)
        if analysis_domain is not None
        else numpy.ones_like(data, dtype=bool)
    )
    if domain_mask.shape != data.shape:
        raise AppError("DEM_DOMAIN_MISMATCH", "DEM analysis domain does not match viewshed dimensions.", status_code=500)

    masks = {
        name: numpy.empty_like(data, dtype=bool)
        for name in (
            "sector",
            "requested_range",
            "effective_range",
            "elevation",
            "terrain",
            "raw_theoretical",
            "theoretical",
            "unknown",
            "visible",
            "blocked",
        )
    }
    xs = transform.c + (numpy.arange(width, dtype=numpy.float64) + 0.5) * transform.a
    min_elevation_slope = math.tan(math.radians(payload.advanced.min_elevation_deg))
    max_elevation_slope = math.tan(math.radians(payload.advanced.max_elevation_deg))
    has_sector_limit = payload.coverage.scan_mode == "sector" and payload.coverage.beam_width_deg < 360
    sector_half_width = payload.coverage.beam_width_deg / 2
    sector_center = payload.coverage.azimuth_deg % 360

    for row_start in range(0, height, COVERAGE_MASK_ROW_CHUNK_SIZE):
        row_stop = min(height, row_start + COVERAGE_MASK_ROW_CHUNK_SIZE)
        rows = numpy.arange(row_start, row_stop, dtype=numpy.float64)
        ys = transform.f + (rows + 0.5) * transform.e
        x_grid, y_grid = numpy.meshgrid(xs, ys)
        dx = x_grid - radar_x
        dy = y_grid - radar_y
        distance = numpy.hypot(dx, dy)

        if has_sector_limit:
            azimuth = (numpy.degrees(numpy.arctan2(dx, dy)) + 360) % 360
            delta = numpy.abs((azimuth - sector_center + 180) % 360 - 180)
            sector = delta <= sector_half_width
        else:
            sector = numpy.ones(distance.shape, dtype=bool)
        requested_range = distance <= payload.coverage.max_range_m
        effective_range = distance <= effective_range_m
        min_height = distance * min_elevation_slope
        max_height = distance * max_elevation_slope
        elevation = (target_height_m >= min_height) & (target_height_m <= max_height)
        domain = domain_mask[row_start:row_stop]
        raw_theoretical = sector & effective_range & elevation
        theoretical = raw_theoretical & domain
        terrain = domain & numpy.isfinite(data[row_start:row_stop]) & (data[row_start:row_stop] <= target_height_m)
        visible = theoretical & terrain

        masks["sector"][row_start:row_stop] = sector
        masks["requested_range"][row_start:row_stop] = requested_range
        masks["effective_range"][row_start:row_stop] = effective_range
        masks["elevation"][row_start:row_stop] = elevation
        masks["terrain"][row_start:row_stop] = terrain
        masks["raw_theoretical"][row_start:row_stop] = raw_theoretical
        masks["theoretical"][row_start:row_stop] = theoretical
        masks["unknown"][row_start:row_stop] = raw_theoretical & ~domain
        masks["visible"][row_start:row_stop] = visible
        masks["blocked"][row_start:row_stop] = theoretical & ~visible

    return {
        **masks,
        "analysis_domain": domain_mask,
        "final": masks["visible"],
    }


def _coverage_masks_for_prepared(
    data,
    transform,
    prepared: PreparedCoverageDem,
    payload: CoverageRequest,
    target_height_m: float,
    effective_range_m: float,
):
    return _coverage_masks(
        data,
        transform,
        prepared.radar_x,
        prepared.radar_y,
        payload,
        target_height_m,
        effective_range_m,
        prepared.analysis_domain,
    )


def _mask_to_geometry(mask, transform):
    from rasterio.features import shapes
    from shapely.geometry import shape as shp_shape
    from shapely.ops import unary_union

    geometries = [
        shp_shape(geom)
        for geom, value in shapes(mask.astype(numpy.uint8), mask=mask, transform=transform)
        if value > 0
    ]
    if not geometries:
        from shapely.geometry import GeometryCollection

        return GeometryCollection()
    return unary_union(geometries)


def _mask_area(mask, transform) -> float:
    return float(mask.sum()) * abs(float(transform.a) * float(transform.e))


def _build_coverage_metrics(masks, transform, radar_equation_limited_area: float) -> CoverageMetrics:
    requested_theoretical_area = _mask_area(masks["raw_theoretical"], transform)
    theoretical_area = _mask_area(masks["theoretical"], transform)
    unknown_area = _mask_area(masks["unknown"], transform)
    visible_area = _mask_area(masks["visible"], transform)
    blocked_area = _mask_area(masks["blocked"], transform)
    terrain_visible_area = _mask_area(
        masks["terrain"] & masks["sector"] & masks["requested_range"],
        transform,
    )
    beam_eligible_area = _mask_area(
        masks["elevation"]
        & masks["sector"]
        & masks["requested_range"]
        & masks["analysis_domain"],
        transform,
    )
    return CoverageMetrics(
        requested_theoretical_area_m2=requested_theoretical_area,
        theoretical_area_m2=theoretical_area,
        unknown_area_m2=unknown_area,
        visible_area_m2=visible_area,
        blocked_area_m2=blocked_area,
        blocked_ratio=blocked_area / theoretical_area if theoretical_area > 0 else 0,
        terrain_visible_area_m2=terrain_visible_area,
        beam_eligible_area_m2=beam_eligible_area,
        radar_equation_limited_area_m2=radar_equation_limited_area,
    )


def _dem_coverage_ratio(metrics: CoverageMetrics) -> float:
    if metrics.requested_theoretical_area_m2 <= 0:
        return 1.0
    return metrics.theoretical_area_m2 / metrics.requested_theoretical_area_m2


def _beam_clip_profile_for_range(
    prepared: PreparedCoverageDem,
    effective_range_m: float,
) -> BeamClipProfile | None:
    if not prepared.beam_clip_profile_m:
        return None
    return BeamClipProfile(
        azimuth_step_deg=prepared.beam_clip_azimuth_step_deg,
        radius_m=[
            max(0.0, min(float(radius_m), effective_range_m))
            for radius_m in prepared.beam_clip_profile_m
        ],
    )


def _analysis_domain_for_shape(prepared: PreparedCoverageDem, shape: tuple[int, int]) -> numpy.ndarray:
    if prepared.analysis_domain is None:
        return numpy.ones(shape, dtype=bool)
    if prepared.analysis_domain.shape != shape:
        raise AppError("DEM_DOMAIN_MISMATCH", "DEM analysis domain does not match output dimensions.", status_code=500)
    return prepared.analysis_domain


def _generate_height_layers(
    staging_dir: Path,
    min_visible_height: Path,
    prepared: PreparedCoverageDem,
    payload: CoverageRequest,
) -> None:
    import rasterio

    height_layers = payload.advanced.height_layers_m or [0, 100, 300, 500, 1000, 2000, 3000]
    effective_range, radar_equation_range = _effective_max_range(payload)
    with rasterio.open(min_visible_height) as src:
        data = src.read(1)
        transform = src.transform

    transformer = Transformer.from_crs(f"EPSG:{prepared.target_epsg}", "EPSG:4326", always_xy=True)
    manifest = {
        "height_layers": [],
        "model": {
            "min_elevation_deg": payload.advanced.min_elevation_deg,
            "max_elevation_deg": payload.advanced.max_elevation_deg,
            "radar_equation_active": radar_equation_range is not None,
            "effective_max_range_m": effective_range,
        },
    }
    for height in height_layers:
        masks = _coverage_masks_for_prepared(data, transform, prepared, payload, height, effective_range)
        visible_mask = masks["visible"]
        theoretical_mask = masks["theoretical"]
        blocked_mask = masks["blocked"]
        visible_path = staging_dir / f"visible_h_{_height_filename_token(height)}.geojson"
        blocked_path = staging_dir / f"blocked_h_{_height_filename_token(height)}.geojson"

        _write_height_layer_geojson(visible_path, visible_mask, transform, transformer, height, "visible")
        _write_height_layer_geojson(blocked_path, blocked_mask, transform, transformer, height, "blocked")
        manifest["height_layers"].append({
            "height_m": height,
            "visible_filename": visible_path.name,
            "blocked_filename": blocked_path.name,
            "theoretical_area_m2": _mask_area(theoretical_mask, transform),
            "visible_area_m2": _mask_area(visible_mask, transform),
            "blocked_area_m2": _mask_area(blocked_mask, transform),
        })

    manifest_path = staging_dir / "height_layers_manifest.json"
    _write_json_atomic(manifest_path, manifest)


def _height_filename_token(height_m: float) -> str:
    if float(height_m).is_integer():
        return str(int(height_m))
    return str(height_m).replace("-", "neg_").replace(".", "p")


def _write_height_layer_geojson(path: Path, mask, transform, transformer: Transformer, height_m: float, kind: str) -> None:
    features = []
    geometry = _mask_to_geometry(mask, transform)
    if not geometry.is_empty:
        wgs84 = project_geometry(geometry, transformer)
        features.append({
            "type": "Feature",
            "properties": {"height_m": height_m, "kind": kind},
            "geometry": mapping(wgs84),
        })

    _write_feature_collection_geojson(path, features)


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
    min_elevation = payload.advanced.min_elevation_deg
    max_elevation = payload.advanced.max_elevation_deg
    effective_range, radar_equation_range = _effective_max_range(payload)

    with rasterio.open(min_visible_height) as src:
        data = src.read(1)
        transform = src.transform
        height, width = data.shape

    analysis_domain = _analysis_domain_for_shape(prepared, data.shape)

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
            if not analysis_domain[yi_int, xi_int]:
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
            if dist > effective_range:
                continue
            # Check azimuth for sector scan
            if payload.coverage.scan_mode == "sector":
                az = (math.degrees(math.atan2(dx, dy)) + 360) % 360
                half = payload.coverage.beam_width_deg / 2
                center = payload.coverage.azimuth_deg % 360
                delta = abs((az - center + 180) % 360 - 180)
                if delta > half:
                    continue
            # Apply the theoretical vertical beam envelope; DEM visibility is applied below.
            min_h_at_dist = max(0.0, dist * math.tan(math.radians(min_elevation))) if dist > 0 else 0.0
            if max_elevation > 0 and dist > 0:
                max_h_at_dist = min(max_height, dist * math.tan(math.radians(max_elevation)))
            else:
                max_h_at_dist = max_height
            if max_h_at_dist <= min_h_at_dist:
                continue

            for level in range(vertical_levels):
                z = min_h_at_dist + (level + 0.5) * ((max_h_at_dist - min_h_at_dist) / vertical_levels)
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
        "min_elevation_deg": min_elevation,
        "max_elevation_deg": max_elevation,
        "vertical_beam_width_deg": max_elevation - min_elevation,
        "radar_equation_active": radar_equation_range is not None,
        "radar_equation_max_range_m": radar_equation_range,
        "effective_max_range_m": effective_range,
        "point_count": len(points),
        "point_format": "float32",
        "fields": ["lon", "lat", "z_agl_m", "clearance_m"],
        "bytes_per_point": 16,
    }
    _write_json_atomic(staging_dir / "voxel_manifest.json", manifest)


def _generate_clipped_volume(
    staging_dir: Path,
    min_visible_height: Path,
    prepared: PreparedCoverageDem,
    payload: CoverageRequest,
) -> None:
    import rasterio

    grid_size = min(payload.advanced.voxel_grid_size, 160)
    min_elevation = payload.advanced.min_elevation_deg
    max_elevation = payload.advanced.max_elevation_deg
    effective_range, radar_equation_range = _effective_max_range(payload)

    with rasterio.open(min_visible_height) as src:
        data = src.read(1)
        transform = src.transform
        height, width = data.shape

    analysis_domain = _analysis_domain_for_shape(prepared, data.shape)

    x_indices = numpy.linspace(0, width - 1, grid_size, dtype=numpy.int32)
    y_indices = numpy.linspace(0, height - 1, grid_size, dtype=numpy.int32)
    transformer = Transformer.from_crs(f"EPSG:{prepared.target_epsg}", "EPSG:4326", always_xy=True)

    cells = []
    blocked_count = 0
    visible_count = 0
    max_visible_top = 0.0
    max_blocked_top = 0.0
    for yi in y_indices:
        for xi in x_indices:
            yi_int = int(round(yi))
            xi_int = int(round(xi))
            if not (0 <= yi_int < height and 0 <= xi_int < width):
                continue
            if not analysis_domain[yi_int, xi_int]:
                continue
            min_visible_h = data[yi_int, xi_int]
            if not numpy.isfinite(min_visible_h) or min_visible_h < 0:
                continue

            x_proj = transform.c + (xi_int + 0.5) * transform.a
            y_proj = transform.f + (yi_int + 0.5) * transform.e
            dx = x_proj - prepared.radar_x
            dy = y_proj - prepared.radar_y
            dist = math.hypot(dx, dy)
            if dist <= 0 or dist > effective_range:
                continue

            if payload.coverage.scan_mode == "sector":
                az = (math.degrees(math.atan2(dx, dy)) + 360) % 360
                half = payload.coverage.beam_width_deg / 2
                center = payload.coverage.azimuth_deg % 360
                delta = abs((az - center + 180) % 360 - 180)
                if delta > half:
                    continue

            beam_bottom = max(0.0, dist * math.tan(math.radians(min_elevation)))
            beam_top = payload.advanced.voxel_max_height_m
            if max_elevation > 0:
                beam_top = min(beam_top, dist * math.tan(math.radians(max_elevation)))
            if beam_top <= beam_bottom:
                continue

            blocked_top = min(max(min_visible_h, beam_bottom), beam_top)
            visible_top = beam_top if min_visible_h < beam_top else beam_bottom
            if blocked_top > beam_bottom + 0.01:
                blocked_count += 1
                max_blocked_top = max(max_blocked_top, blocked_top)
            if visible_top > max(blocked_top, beam_bottom) + 0.01:
                visible_count += 1
                max_visible_top = max(max_visible_top, visible_top)

            lon, lat = transformer.transform(x_proj, y_proj)
            cells.append((lon, lat, beam_bottom, blocked_top, visible_top))

    cells_path = staging_dir / "clipped_volume_cells.bin"
    array = numpy.array(cells, dtype=numpy.float32).flatten()
    with open(cells_path, "wb") as file:
        file.write(array.tobytes())

    manifest = {
        "grid_size": grid_size,
        "source_width": int(width),
        "source_height": int(height),
        "cell_size_m": max(abs(float(transform.a)), abs(float(transform.e))) * max(1, math.ceil(max(width, height) / grid_size)),
        "min_elevation_deg": min_elevation,
        "max_elevation_deg": max_elevation,
        "max_height_m": payload.advanced.voxel_max_height_m,
        "radar_equation_active": radar_equation_range is not None,
        "radar_equation_max_range_m": radar_equation_range,
        "effective_max_range_m": effective_range,
        "cell_count": len(cells),
        "blocked_cell_count": blocked_count,
        "visible_cell_count": visible_count,
        "max_blocked_top_m": max_blocked_top,
        "max_visible_top_m": max_visible_top,
        "point_format": "float32",
        "fields": ["lon", "lat", "beam_bottom_m", "blocked_top_m", "visible_top_m"],
        "bytes_per_cell": 20,
    }
    _write_json_atomic(staging_dir / "clipped_volume_manifest.json", manifest)


def _write_vector_outputs(
    task_id: str,
    staging_dir: Path,
    output_dir: Path,
    prepared: PreparedCoverageDem,
    payload: CoverageRequest,
    viewshed: Path,
    min_visible_height: Path,
    gdal_command: list[str],
) -> tuple[CoverageOutputs, list[CoverageOutputFile], CoverageMetrics, CoverageModelMetadata, CoverageDiagnostics, list[str]]:
    requested_range_geom = make_range_geometry(
        prepared.radar_x,
        prepared.radar_y,
        payload.coverage.max_range_m,
        payload.coverage.scan_mode,
        payload.coverage.azimuth_deg,
        payload.coverage.beam_width_deg,
    )
    effective_range, radar_equation_range = _effective_max_range(payload)
    transformer = Transformer.from_crs(f"EPSG:{prepared.target_epsg}", "EPSG:4326", always_xy=True)

    import rasterio

    with rasterio.open(min_visible_height) as src:
        min_visible_data = src.read(1)
        min_visible_transform = src.transform

    masks = _coverage_masks_for_prepared(
        min_visible_data,
        min_visible_transform,
        prepared,
        payload,
        payload.target.height_m,
        effective_range,
    )
    theoretical_geom = _mask_to_geometry(masks["theoretical"], min_visible_transform)
    visible_clipped = _mask_to_geometry(masks["visible"], min_visible_transform)
    blocked_geom = _mask_to_geometry(masks["blocked"], min_visible_transform)

    tolerance = default_simplify_tolerance(prepared.resolution_m, payload.advanced.output_simplify_tolerance_m)
    if tolerance > 0:
        theoretical_geom = theoretical_geom.simplify(tolerance, preserve_topology=True)
        visible_clipped = visible_clipped.simplify(tolerance, preserve_topology=True)
        blocked_geom = blocked_geom.simplify(tolerance, preserve_topology=True)

    range_geojson = staging_dir / "radar_range.geojson"
    visible_geojson = staging_dir / "visible.geojson"
    blocked_geojson = staging_dir / "blocked.geojson"
    model_metadata_json = staging_dir / "model_metadata.json"
    output_manifest_json = staging_dir / "output_manifest.json"

    _write_feature_collection(
        range_geojson,
        project_geometry(theoretical_geom, transformer) if not theoretical_geom.is_empty else theoretical_geom,
        {
            "kind": "theoretical_footprint",
            "effective_max_range_m": effective_range,
            "min_elevation_deg": payload.advanced.min_elevation_deg,
            "max_elevation_deg": payload.advanced.max_elevation_deg,
        },
    )
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

    requested_area = requested_range_geom.area
    effective_range_geom = make_range_geometry(
        prepared.radar_x,
        prepared.radar_y,
        effective_range,
        payload.coverage.scan_mode,
        payload.coverage.azimuth_deg,
        payload.coverage.beam_width_deg,
    )
    radar_equation_limited_area = max(0.0, requested_area - effective_range_geom.area) if radar_equation_range is not None else 0.0
    metrics = _build_coverage_metrics(
        masks,
        min_visible_transform,
        radar_equation_limited_area=radar_equation_limited_area,
    )
    dem_coverage_ratio = _dem_coverage_ratio(metrics)
    diagnostics = CoverageDiagnostics(
        radar_equation_active=radar_equation_range is not None,
        radar_equation_max_range_m=radar_equation_range,
        effective_max_range_m=effective_range,
        terrain_blocked_area_m2=metrics.blocked_area_m2,
        elevation_limited_area_m2=max(
            0.0,
            _mask_area(
                masks["sector"] & masks["effective_range"] & masks["analysis_domain"],
                min_visible_transform,
            )
            - metrics.theoretical_area_m2,
        ),
        radar_equation_limited_area_m2=radar_equation_limited_area,
        notes=_build_diagnostic_notes(payload, effective_range, radar_equation_range),
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
        clipped_volume_manifest_json=f"/outputs/{task_id}/clipped_volume_manifest.json",
        clipped_volume_cells_bin=f"/outputs/{task_id}/clipped_volume_cells.bin",
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
        dem_coverage_ratio=dem_coverage_ratio,
        max_range_m=payload.coverage.max_range_m,
        scan_mode=payload.coverage.scan_mode,
        azimuth_deg=payload.coverage.azimuth_deg,
        beam_width_deg=payload.coverage.beam_width_deg,
        simplify_tolerance_m=tolerance,
        gdal_viewshed_command=gdal_command,
        voxel_grid_size=payload.advanced.voxel_grid_size,
        voxel_vertical_levels=payload.advanced.voxel_vertical_levels,
        voxel_max_height_m=payload.advanced.voxel_max_height_m,
        min_elevation_deg=payload.advanced.min_elevation_deg,
        max_elevation_deg=payload.advanced.max_elevation_deg,
        vertical_beam_width_deg=payload.advanced.vertical_beam_width_deg,
        visual_dome_mode=payload.advanced.visual_dome_mode,
        height_layers_m=height_layers,
        radar_equation_active=diagnostics.radar_equation_active,
        radar_equation_max_range_m=diagnostics.radar_equation_max_range_m,
        effective_max_range_m=effective_range,
        beam_clip_profile=_beam_clip_profile_for_range(prepared, effective_range),
    )
    warnings = _build_model_warnings(prepared, requested_range_geom, diagnostics, dem_coverage_ratio)
    _write_json_atomic(
        model_metadata_json,
        {
            "model": model.model_dump(),
            "metrics": metrics.model_dump(),
            "diagnostics": diagnostics.model_dump(),
            "warnings": warnings,
        },
    )
    output_paths = {kind: staging_dir / filename for kind, filename in OUTPUT_FILENAMES.items()}
    _write_output_manifest(output_manifest_json, [], metrics, model, warnings, diagnostics)
    manifest_files = describe_output_files(task_id, output_paths)
    _write_output_manifest(output_manifest_json, manifest_files, metrics, model, warnings, diagnostics)
    _ensure_staged_outputs_exist(staging_dir)
    _commit_staged_outputs(staging_dir, output_dir)
    output_files = list_task_output_files(task_id)
    _ensure_finished_outputs_exist(output_files)
    return outputs, output_files, metrics, model, diagnostics, warnings


def _write_output_manifest(
    path: Path,
    output_files: list[CoverageOutputFile],
    metrics: CoverageMetrics,
    model: CoverageModelMetadata,
    warnings: list[str],
    diagnostics: CoverageDiagnostics | None = None,
) -> None:
    _write_json_atomic(
        path,
        {
            "files": [item.model_dump() for item in output_files],
            "metrics": metrics.model_dump(),
            "model": model.model_dump(),
            "diagnostics": diagnostics.model_dump() if diagnostics else None,
            "warnings": warnings,
        },
    )


def _build_diagnostic_notes(
    payload: CoverageRequest,
    effective_range: float,
    radar_equation_range: float | None,
) -> list[str]:
    notes: list[str] = []
    if radar_equation_range is None:
        notes.append("Radar equation is inactive because one or more RF parameters are missing.")
    elif effective_range < payload.coverage.max_range_m:
        notes.append(
            f"Radar equation limits effective range to {effective_range:.0f} m, below requested {payload.coverage.max_range_m:.0f} m."
        )
    else:
        notes.append("Radar equation is active but does not reduce the requested maximum range.")

    if payload.advanced.min_elevation_deg > 0:
        notes.append(f"Targets below {payload.advanced.min_elevation_deg:.1f}° elevation are excluded.")
    if payload.advanced.max_elevation_deg < 90:
        notes.append(f"Targets above {payload.advanced.max_elevation_deg:.1f}° elevation are excluded.")
    return notes


def _build_model_warnings(
    prepared: PreparedCoverageDem,
    range_geom,
    diagnostics: CoverageDiagnostics | None = None,
    dem_coverage_ratio: float | None = None,
) -> list[str]:
    warnings: list[str] = []
    dem_bounds_geom = box(
        prepared.projected_bounds.left,
        prepared.projected_bounds.bottom,
        prepared.projected_bounds.right,
        prepared.projected_bounds.top,
    )
    coverage_ratio = prepared.dem_coverage_ratio if dem_coverage_ratio is None else dem_coverage_ratio
    if coverage_ratio < WARN_DEM_COVERAGE_RATIO:
        warnings.append(
            f"DEM covers {coverage_ratio:.1%} of the requested theoretical beam; the remainder is unknown."
        )
    if diagnostics is not None:
        warnings.extend(diagnostics.notes)
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
    for source in staging_dir.glob("blocked_h_*.geojson"):
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
