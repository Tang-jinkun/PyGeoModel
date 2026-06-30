import json
import math
import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import numpy
from pyproj import CRS, Transformer
from rasterio.features import shapes
from rasterio.transform import array_bounds
from rasterio.windows import from_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds
from shapely.geometry import GeometryCollection, mapping, shape
from shapely.ops import unary_union

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.watchpost import (
    WatchpostDetectionMetrics,
    WatchpostDetectionOutputs,
    WatchpostDetectionRequest,
    WatchpostModelMetadata,
)
from app.services.dem_store import find_dem_file
from app.services.geometry import make_range_geometry, project_geometry
from app.services.projection import utm_epsg_from_lonlat
from app.services.watchpost_output_files import (
    WATCHPOST_OUTPUT_FILENAMES,
    describe_watchpost_output_files,
    list_watchpost_task_output_files,
)
from app.services.watchpost_task_store import mark_watchpost_failed, mark_watchpost_finished, mark_watchpost_running


class PreparedWatchpostDem:
    def __init__(
        self,
        projected_dem: Path,
        target_epsg: int,
        observer_x: float,
        observer_y: float,
        bounds,
        resolution_m: tuple[float, float],
    ) -> None:
        self.projected_dem = projected_dem
        self.target_epsg = target_epsg
        self.observer_x = observer_x
        self.observer_y = observer_y
        self.bounds = bounds
        self.resolution_m = resolution_m


def run_watchpost_task(task_id: str, payload: WatchpostDetectionRequest) -> None:
    try:
        mark_watchpost_running(task_id, "Preparing DEM and watchpost projection.", 15)
        output_dir = settings.outputs_dir / task_id
        output_dir.mkdir(parents=True, exist_ok=True)
        staging_dir = output_dir / f".staging-{uuid4().hex}"
        staging_dir.mkdir(parents=True, exist_ok=False)

        try:
            prepared = _prepare_watchpost_dem(find_dem_file(payload.dem_id), staging_dir / "dem_projected.tif", payload)
            mark_watchpost_running(task_id, "Running viewshed.", 45)
            viewshed = staging_dir / "viewshed.tif"
            gdal_command = _run_gdal_viewshed(prepared.projected_dem, viewshed, prepared, payload)
            mark_watchpost_running(task_id, "Vectorizing watchpost detection outputs.", 80)
            outputs, output_files, metrics, model, warnings = _write_watchpost_outputs(
                task_id, staging_dir, output_dir, prepared, payload, viewshed, gdal_command
            )
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)

        mark_watchpost_finished(task_id, metrics=metrics, outputs=outputs, output_files=output_files, model=model, warnings=warnings)
    except Exception as exc:
        mark_watchpost_failed(task_id, str(exc))


def _prepare_watchpost_dem(source: Path, destination: Path, payload: WatchpostDetectionRequest) -> PreparedWatchpostDem:
    import rasterio

    target_epsg = utm_epsg_from_lonlat(payload.observer.lon, payload.observer.lat)
    target_crs = CRS.from_epsg(target_epsg)
    to_target = Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)
    observer_x, observer_y = to_target.transform(payload.observer.lon, payload.observer.lat)

    with rasterio.open(source) as src:
        if src.crs is None:
            raise AppError("DEM_WITHOUT_CRS", "DEM is missing coordinate reference system.")
        src_observer_x, src_observer_y = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True).transform(
            payload.observer.lon, payload.observer.lat
        )
        if not (src.bounds.left <= src_observer_x <= src.bounds.right and src.bounds.bottom <= src_observer_y <= src.bounds.top):
            raise AppError("WATCHPOST_OUTSIDE_DEM", "Watchpost point is outside DEM bounds.", status_code=400)

        radius = payload.coverage.max_range_m
        target_bounds = (observer_x - radius, observer_y - radius, observer_x + radius, observer_y + radius)
        src_crop_bounds = transform_bounds(target_crs, src.crs, *target_bounds, densify_pts=21)
        crop_bounds = (
            max(src.bounds.left, src_crop_bounds[0]),
            max(src.bounds.bottom, src_crop_bounds[1]),
            min(src.bounds.right, src_crop_bounds[2]),
            min(src.bounds.top, src_crop_bounds[3]),
        )
        if crop_bounds[0] >= crop_bounds[2] or crop_bounds[1] >= crop_bounds[3]:
            raise AppError("RANGE_OUTSIDE_DEM", "Watchpost range does not intersect DEM bounds.", status_code=400)

        window = from_bounds(*crop_bounds, transform=src.transform).round_offsets().round_lengths()
        crop_transform = src.window_transform(window)
        crop_bounds_exact = array_bounds(int(window.height), int(window.width), crop_transform)
        dst_transform, dst_width, dst_height = calculate_default_transform(
            src.crs,
            target_crs,
            int(window.width),
            int(window.height),
            *crop_bounds_exact,
        )
        if dst_width <= 0 or dst_height <= 0:
            raise AppError("INVALID_DEM", "Projected DEM dimensions are empty.")

        source_data = src.read(1, window=window, masked=True)
        fill_value = src.nodata if src.nodata is not None else 0
        source_array = source_data.filled(fill_value)
        destination_array = numpy.full((dst_height, dst_width), fill_value, dtype=source_array.dtype)

        reproject(
            source=source_array,
            destination=destination_array,
            src_transform=crop_transform,
            src_crs=src.crs,
            src_nodata=src.nodata,
            dst_transform=dst_transform,
            dst_crs=target_crs,
            dst_nodata=src.nodata,
            resampling=Resampling.bilinear,
        )

        metadata = src.meta.copy()
        metadata.update(
            {
                "driver": "GTiff",
                "crs": target_crs,
                "transform": dst_transform,
                "width": dst_width,
                "height": dst_height,
                "count": 1,
                "compress": "deflate",
            }
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(destination, "w", **metadata) as dst:
            dst.write(destination_array, 1)

    projected_bounds_tuple = array_bounds(dst_height, dst_width, dst_transform)
    bounds = type("Bounds", (), {
        "left": projected_bounds_tuple[0],
        "bottom": projected_bounds_tuple[1],
        "right": projected_bounds_tuple[2],
        "top": projected_bounds_tuple[3],
    })()
    return PreparedWatchpostDem(
        projected_dem=destination,
        target_epsg=target_epsg,
        observer_x=observer_x,
        observer_y=observer_y,
        bounds=bounds,
        resolution_m=(abs(dst_transform.a), abs(dst_transform.e)),
    )


def _run_gdal_viewshed(
    dem: Path,
    viewshed: Path,
    prepared: PreparedWatchpostDem,
    payload: WatchpostDetectionRequest,
) -> list[str]:
    if shutil.which("gdal_viewshed") is None:
        raise AppError("GDAL_VIEWSHED_NOT_FOUND", "gdal_viewshed command is not available.", status_code=500)

    command = [
        "gdal_viewshed",
        "-ox",
        str(prepared.observer_x),
        "-oy",
        str(prepared.observer_y),
        "-oz",
        str(payload.observer.height_m),
        "-tz",
        str(payload.target.height_m),
        "-md",
        str(payload.coverage.max_range_m),
        "-om",
        "NORMAL",
    ]
    if payload.analysis.use_curvature:
        command.extend(["-cc", str(payload.analysis.curvature_coeff)])
    command.extend([str(dem), str(viewshed)])
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AppError("GDAL_VIEWSHED_FAILED", result.stderr.strip() or "gdal_viewshed failed.", status_code=500)
    return command


def _write_watchpost_outputs(
    task_id: str,
    staging_dir: Path,
    output_dir: Path,
    prepared: PreparedWatchpostDem,
    payload: WatchpostDetectionRequest,
    viewshed: Path,
    gdal_command: list[str],
):
    import rasterio

    with rasterio.open(viewshed) as src:
        viewshed_data = src.read(1)
        transform = src.transform
        nodata = src.nodata
    visible_raw = viewshed_data > 0
    if nodata is not None:
        visible_raw &= viewshed_data != nodata

    theoretical_geom = make_range_geometry(
        prepared.observer_x,
        prepared.observer_y,
        payload.coverage.max_range_m,
        payload.coverage.scan_mode,
        payload.coverage.azimuth_deg,
        payload.coverage.view_angle_deg,
    )
    theoretical_mask = _geometry_to_mask(theoretical_geom, visible_raw.shape, transform)
    visible_mask = visible_raw & theoretical_mask
    blocked_mask = theoretical_mask & ~visible_mask

    theoretical_output_geom = _mask_to_geometry(theoretical_mask, transform)
    visible_geom = _mask_to_geometry(visible_mask, transform)
    blocked_geom = _mask_to_geometry(blocked_mask, transform)
    tolerance = payload.analysis.output_simplify_tolerance_m
    if tolerance is None:
        tolerance = max(prepared.resolution_m)
    if tolerance > 0:
        theoretical_output_geom = theoretical_output_geom.simplify(tolerance, preserve_topology=True)
        visible_geom = visible_geom.simplify(tolerance, preserve_topology=True)
        blocked_geom = blocked_geom.simplify(tolerance, preserve_topology=True)

    transformer = Transformer.from_crs(f"EPSG:{prepared.target_epsg}", "EPSG:4326", always_xy=True)
    range_geojson = staging_dir / "range.geojson"
    visible_geojson = staging_dir / "visible.geojson"
    blocked_geojson = staging_dir / "blocked.geojson"
    model_metadata_json = staging_dir / "model_metadata.json"
    output_manifest_json = staging_dir / "output_manifest.json"

    _write_feature_collection(range_geojson, project_geometry(theoretical_output_geom, transformer), {"kind": "watchpost_range"})
    _write_feature_collection(visible_geojson, project_geometry(visible_geom, transformer), {"kind": "watchpost_visible"})
    _write_feature_collection(blocked_geojson, project_geometry(blocked_geom, transformer), {"kind": "watchpost_blocked"})

    ground = _sample_nearest(prepared.projected_dem, prepared.observer_x, prepared.observer_y)
    observer_altitude = ground + payload.observer.height_m
    cell_area = abs(float(transform.a) * float(transform.e))
    theoretical_area = float(theoretical_mask.sum()) * cell_area
    visible_area = float(visible_mask.sum()) * cell_area
    blocked_area = float(blocked_mask.sum()) * cell_area
    metrics = WatchpostDetectionMetrics(
        theoretical_area_m2=theoretical_area,
        visible_area_m2=visible_area,
        blocked_area_m2=blocked_area,
        blocked_ratio=blocked_area / theoretical_area if theoretical_area > 0 else 0,
        max_range_m=payload.coverage.max_range_m,
        effective_view_angle_deg=360 if payload.coverage.scan_mode == "omni" else payload.coverage.view_angle_deg,
        observer_ground_elevation_m=ground,
        observer_altitude_m=observer_altitude,
    )
    model = WatchpostModelMetadata(
        target_epsg=prepared.target_epsg,
        observer_projected_xy=[prepared.observer_x, prepared.observer_y],
        projected_dem_bounds=[prepared.bounds.left, prepared.bounds.bottom, prepared.bounds.right, prepared.bounds.top],
        projected_dem_resolution_m=[prepared.resolution_m[0], prepared.resolution_m[1]],
        max_range_m=payload.coverage.max_range_m,
        scan_mode=payload.coverage.scan_mode,
        azimuth_deg=payload.coverage.azimuth_deg,
        view_angle_deg=payload.coverage.view_angle_deg,
        observer_ground_elevation_m=ground,
        observer_altitude_m=observer_altitude,
        target_height_m=payload.target.height_m,
        use_curvature=payload.analysis.use_curvature,
        curvature_coeff=payload.analysis.curvature_coeff,
        simplify_tolerance_m=tolerance,
        gdal_viewshed_command=gdal_command,
    )
    outputs = WatchpostDetectionOutputs(
        viewshed_tif=f"/outputs/{task_id}/viewshed.tif",
        visible_geojson=f"/outputs/{task_id}/visible.geojson",
        blocked_geojson=f"/outputs/{task_id}/blocked.geojson",
        range_geojson=f"/outputs/{task_id}/range.geojson",
        model_metadata_json=f"/outputs/{task_id}/model_metadata.json",
        output_manifest_json=f"/outputs/{task_id}/output_manifest.json",
    )

    _write_json_atomic(model_metadata_json, {"model": model.model_dump(), "metrics": metrics.model_dump(), "warnings": []})
    output_paths = {kind: staging_dir / filename for kind, filename in WATCHPOST_OUTPUT_FILENAMES.items()}
    manifest_files = describe_watchpost_output_files(task_id, output_paths)
    _write_json_atomic(
        output_manifest_json,
        {
            "files": [item.model_dump() for item in manifest_files],
            "metrics": metrics.model_dump(),
            "model": model.model_dump(),
            "warnings": [],
        },
    )
    _ensure_staged_outputs_exist(staging_dir)
    _commit_staged_outputs(staging_dir, output_dir)
    output_files = list_watchpost_task_output_files(task_id)
    return outputs, output_files, metrics, model, []


def _geometry_to_mask(geometry, out_shape, transform):
    from rasterio.features import rasterize

    if geometry.is_empty:
        return numpy.zeros(out_shape, dtype=bool)
    return rasterize([(geometry, 1)], out_shape=out_shape, transform=transform, fill=0, dtype=numpy.uint8).astype(bool)


def _mask_to_geometry(mask, transform):
    geometries = [
        shape(geom)
        for geom, value in shapes(mask.astype(numpy.uint8), mask=mask, transform=transform)
        if value > 0
    ]
    if not geometries:
        return GeometryCollection()
    return unary_union(geometries)


def _sample_nearest(path: Path, x: float, y: float) -> float:
    import rasterio

    with rasterio.open(path) as src:
        row, col = src.index(x, y)
        if row < 0 or col < 0 or row >= src.height or col >= src.width:
            return 0.0
        value = float(src.read(1, window=((row, row + 1), (col, col + 1)))[0, 0])
        if src.nodata is not None and value == src.nodata:
            return 0.0
        return value


def _write_feature_collection(path: Path, geometry, properties: dict | None = None) -> None:
    features = []
    if geometry is not None and not geometry.is_empty:
        features.append({"type": "Feature", "properties": properties or {}, "geometry": mapping(geometry)})
    _write_json_atomic(path, {"type": "FeatureCollection", "features": features})


def _ensure_staged_outputs_exist(staging_dir: Path) -> None:
    missing = [
        kind
        for kind, filename in WATCHPOST_OUTPUT_FILENAMES.items()
        if not (staging_dir / filename).exists() or (staging_dir / filename).stat().st_size <= 0
    ]
    if missing:
        raise AppError("OUTPUT_INCOMPLETE", f"Watchpost task staged outputs are incomplete: {', '.join(missing)}.", status_code=500)


def _commit_staged_outputs(staging_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename in WATCHPOST_OUTPUT_FILENAMES.values():
        (staging_dir / filename).replace(output_dir / filename)
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
