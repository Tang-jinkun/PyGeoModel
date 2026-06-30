import json
import math
import os
import shutil
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
from app.schemas.uav import (
    UavModelMetadata,
    UavPlatformInput,
    UavReconMetrics,
    UavReconOutputs,
    UavReconRequest,
)
from app.services.dem_store import find_dem_file
from app.services.projection import utm_epsg_from_lonlat
from app.services.uav_output_files import UAV_OUTPUT_FILENAMES, describe_uav_output_files, list_uav_task_output_files
from app.services.uav_task_store import mark_uav_failed, mark_uav_finished, mark_uav_running


def run_uav_recon_task(task_id: str, payload: UavReconRequest) -> None:
    try:
        mark_uav_running(task_id, "Preparing DEM and UAV projection.", 15)
        output_dir = settings.outputs_dir / task_id
        output_dir.mkdir(parents=True, exist_ok=True)
        staging_dir = output_dir / f".staging-{uuid4().hex}"
        staging_dir.mkdir(parents=True, exist_ok=False)

        try:
            prepared = _prepare_uav_dem(find_dem_file(payload.dem_id), staging_dir / "dem_projected.tif", payload)
            mark_uav_running(task_id, "Computing sensor footprint and terrain occlusion.", 55)
            outputs, output_files, metrics, model, warnings = _write_uav_outputs(task_id, staging_dir, output_dir, prepared, payload)
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)

        mark_uav_finished(task_id, metrics=metrics, outputs=outputs, output_files=output_files, model=model, warnings=warnings)
    except Exception as exc:
        mark_uav_failed(task_id, str(exc))


class PreparedUavDem:
    def __init__(
        self,
        projected_dem: Path,
        target_epsg: int,
        uav_x: float,
        uav_y: float,
        bounds,
        resolution_m: tuple[float, float],
    ) -> None:
        self.projected_dem = projected_dem
        self.target_epsg = target_epsg
        self.uav_x = uav_x
        self.uav_y = uav_y
        self.bounds = bounds
        self.resolution_m = resolution_m


def _prepare_uav_dem(source: Path, destination: Path, payload: UavReconRequest) -> PreparedUavDem:
    import rasterio

    coverage_points = _coverage_points(payload)
    target_epsg = utm_epsg_from_lonlat(payload.uav.lon, payload.uav.lat)
    target_crs = CRS.from_epsg(target_epsg)
    to_target = Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)
    uav_x, uav_y = to_target.transform(payload.uav.lon, payload.uav.lat)
    projected_points = [to_target.transform(point.lon, point.lat) for point in coverage_points]

    with rasterio.open(source) as src:
        if src.crs is None:
            raise AppError("DEM_WITHOUT_CRS", "DEM is missing coordinate reference system.")
        src_uav_x, src_uav_y = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True).transform(payload.uav.lon, payload.uav.lat)
        if not (src.bounds.left <= src_uav_x <= src.bounds.right and src.bounds.bottom <= src_uav_y <= src.bounds.top):
            raise AppError("UAV_OUTSIDE_DEM", "UAV point is outside DEM bounds.", status_code=400)

        radius = payload.sensor.max_range_m
        xs = [point[0] for point in projected_points]
        ys = [point[1] for point in projected_points]
        target_bounds = (min(xs) - radius, min(ys) - radius, max(xs) + radius, max(ys) + radius)
        src_crop_bounds = transform_bounds(target_crs, src.crs, *target_bounds, densify_pts=21)
        crop_bounds = (
            max(src.bounds.left, src_crop_bounds[0]),
            max(src.bounds.bottom, src_crop_bounds[1]),
            min(src.bounds.right, src_crop_bounds[2]),
            min(src.bounds.top, src_crop_bounds[3]),
        )
        if crop_bounds[0] >= crop_bounds[2] or crop_bounds[1] >= crop_bounds[3]:
            raise AppError("RANGE_OUTSIDE_DEM", "UAV sensor range does not intersect DEM bounds.", status_code=400)

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
    return PreparedUavDem(
        projected_dem=destination,
        target_epsg=target_epsg,
        uav_x=uav_x,
        uav_y=uav_y,
        bounds=bounds,
        resolution_m=(abs(dst_transform.a), abs(dst_transform.e)),
    )


def _write_uav_outputs(
    task_id: str,
    staging_dir: Path,
    output_dir: Path,
    prepared: PreparedUavDem,
    payload: UavReconRequest,
):
    import rasterio

    with rasterio.open(prepared.projected_dem) as src:
        dem = src.read(1)
        transform = src.transform
        nodata = src.nodata

    masks, model, point_count, route_length_m, visible_area_sum = _compute_uav_masks(dem, transform, nodata, prepared, payload)
    transformer = Transformer.from_crs(f"EPSG:{prepared.target_epsg}", "EPSG:4326", always_xy=True)

    footprint_geom = _mask_to_geometry(masks["footprint"], transform)
    visible_geom = _mask_to_geometry(masks["visible"], transform)
    blocked_geom = _mask_to_geometry(masks["blocked"], transform)
    tolerance = payload.analysis.output_simplify_tolerance_m
    if tolerance is None:
        tolerance = max(prepared.resolution_m)
    if tolerance > 0:
        footprint_geom = footprint_geom.simplify(tolerance, preserve_topology=True)
        visible_geom = visible_geom.simplify(tolerance, preserve_topology=True)
        blocked_geom = blocked_geom.simplify(tolerance, preserve_topology=True)

    footprint_path = staging_dir / "footprint.geojson"
    visible_path = staging_dir / "visible.geojson"
    blocked_path = staging_dir / "blocked.geojson"
    model_path = staging_dir / "model_metadata.json"
    manifest_path = staging_dir / "output_manifest.json"

    _write_feature_collection(footprint_path, _project_geometry(footprint_geom, transformer), {"kind": "uav_footprint"})
    _write_feature_collection(visible_path, _project_geometry(visible_geom, transformer), {"kind": "uav_visible"})
    _write_feature_collection(blocked_path, _project_geometry(blocked_geom, transformer), {"kind": "uav_blocked"})

    cell_area = abs(float(transform.a) * float(transform.e))
    theoretical_area = float(masks["footprint"].sum()) * cell_area
    visible_area = float(masks["visible"].sum()) * cell_area
    blocked_area = float(masks["blocked"].sum()) * cell_area
    metrics = UavReconMetrics(
        theoretical_area_m2=theoretical_area,
        visible_area_m2=visible_area,
        blocked_area_m2=blocked_area,
        blocked_ratio=blocked_area / theoretical_area if theoretical_area > 0 else 0,
        max_ground_distance_m=payload.sensor.max_range_m,
        coverage_point_count=point_count,
        route_length_m=route_length_m,
        average_visible_area_m2=visible_area_sum / point_count if point_count > 0 else 0,
        overlap_area_m2=max(0.0, visible_area_sum - visible_area),
    )

    outputs = UavReconOutputs(
        footprint_geojson=f"/outputs/{task_id}/footprint.geojson",
        visible_geojson=f"/outputs/{task_id}/visible.geojson",
        blocked_geojson=f"/outputs/{task_id}/blocked.geojson",
        model_metadata_json=f"/outputs/{task_id}/model_metadata.json",
        output_manifest_json=f"/outputs/{task_id}/output_manifest.json",
    )
    _write_json_atomic(model_path, {"model": model.model_dump(), "metrics": metrics.model_dump(), "warnings": []})
    output_paths = {kind: staging_dir / filename for kind, filename in UAV_OUTPUT_FILENAMES.items()}
    manifest_files = describe_uav_output_files(task_id, output_paths)
    _write_json_atomic(
        manifest_path,
        {
            "files": [item.model_dump() for item in manifest_files],
            "metrics": metrics.model_dump(),
            "model": model.model_dump(),
            "warnings": [],
        },
    )
    _ensure_staged_outputs_exist(staging_dir)
    _commit_staged_outputs(staging_dir, output_dir)
    output_files = list_uav_task_output_files(task_id)
    return outputs, output_files, metrics, model, []


def _compute_uav_masks(dem, transform, nodata, prepared: PreparedUavDem, payload: UavReconRequest):
    height, width = dem.shape
    cols = numpy.arange(width, dtype=numpy.float64)
    rows = numpy.arange(height, dtype=numpy.float64)
    xs = transform.c + (cols + 0.5) * transform.a
    ys = transform.f + (rows + 0.5) * transform.e
    x_grid, y_grid = numpy.meshgrid(xs, ys)
    finite = numpy.isfinite(dem)
    if nodata is not None:
        finite &= dem != nodata

    target_z = dem + payload.analysis.target_height_m
    coverage_points = _coverage_points(payload)
    to_target = Transformer.from_crs("EPSG:4326", f"EPSG:{prepared.target_epsg}", always_xy=True)
    footprint = numpy.zeros_like(finite, dtype=bool)
    visible = numpy.zeros_like(finite, dtype=bool)
    visible_area_sum = 0.0
    cell_area = abs(float(transform.a) * float(transform.e))
    first_ground = 0.0
    first_altitude = 0.0
    for index, point in enumerate(coverage_points):
        point_x, point_y = to_target.transform(point.lon, point.lat)
        ground = _sample_nearest(dem, transform, point_x, point_y, nodata)
        if not math.isfinite(ground):
            continue
        uav_altitude = point.altitude_m if point.altitude_mode == "amsl" else ground + point.altitude_m
        if index == 0:
            first_ground = ground
            first_altitude = uav_altitude
        point_footprint = _footprint_mask_for_point(
            finite,
            target_z,
            x_grid,
            y_grid,
            point_x,
            point_y,
            uav_altitude,
            point,
            payload,
        )
        point_visible = numpy.zeros_like(point_footprint, dtype=bool)
        if payload.analysis.use_terrain_occlusion:
            candidate_indices = numpy.argwhere(point_footprint)
            max_candidates = max(20_000, int(140_000 / max(1, len(coverage_points))))
            if candidate_indices.shape[0] > max_candidates:
                step = math.ceil(candidate_indices.shape[0] / max_candidates)
                candidate_indices = candidate_indices[::step]
            for row, col in candidate_indices:
                point_visible[row, col] = _has_line_of_sight(
                    dem,
                    transform,
                    nodata,
                    point_x,
                    point_y,
                    uav_altitude,
                    float(x_grid[row, col]),
                    float(y_grid[row, col]),
                    float(target_z[row, col]),
                )
        else:
            point_visible = point_footprint.copy()
        footprint |= point_footprint
        visible |= point_visible
        visible_area_sum += float(point_visible.sum()) * cell_area
    blocked = footprint & ~visible
    route_length_m = _route_length_m(payload)
    model = UavModelMetadata(
        target_epsg=prepared.target_epsg,
        uav_projected_xy=[prepared.uav_x, prepared.uav_y],
        uav_altitude_amsl_m=float(first_altitude),
        ground_elevation_m=float(first_ground),
        projected_dem_bounds=[prepared.bounds.left, prepared.bounds.bottom, prepared.bounds.right, prepared.bounds.top],
        projected_dem_resolution_m=[prepared.resolution_m[0], prepared.resolution_m[1]],
        heading_deg=payload.uav.heading_deg,
        pitch_deg=payload.uav.pitch_deg,
        roll_deg=payload.uav.roll_deg,
        h_fov_deg=payload.sensor.h_fov_deg,
        v_fov_deg=payload.sensor.v_fov_deg,
        min_range_m=payload.sensor.min_range_m,
        max_range_m=payload.sensor.max_range_m,
        target_height_m=payload.analysis.target_height_m,
        sample_resolution_m=payload.analysis.sample_resolution_m or max(prepared.resolution_m),
        centerline_ground_point=None,
        coverage_mode="route" if _route_waypoints(payload) else "single",
        coverage_point_count=len(coverage_points),
        route_length_m=route_length_m,
    )
    return {"footprint": footprint, "visible": visible, "blocked": blocked}, model, len(coverage_points), route_length_m, visible_area_sum


def _footprint_mask_for_point(
    finite,
    target_z,
    x_grid,
    y_grid,
    point_x: float,
    point_y: float,
    uav_altitude: float,
    point: UavPlatformInput,
    payload: UavReconRequest,
):
    dx = x_grid - point_x
    dy = y_grid - point_y
    horizontal = numpy.hypot(dx, dy)
    dz = target_z - uav_altitude
    slant = numpy.sqrt(horizontal * horizontal + dz * dz)
    azimuth = (numpy.degrees(numpy.arctan2(dx, dy)) + 360) % 360
    half_h = payload.sensor.h_fov_deg / 2
    delta_az = numpy.abs((azimuth - point.heading_deg + 180) % 360 - 180)
    depression = numpy.degrees(numpy.arctan2(uav_altitude - target_z, numpy.maximum(horizontal, 0.001)))
    center_depression = -point.pitch_deg
    half_v = payload.sensor.v_fov_deg / 2
    return (
        finite
        & (horizontal >= payload.sensor.min_range_m)
        & (slant <= payload.sensor.max_range_m)
        & (delta_az <= half_h)
        & (numpy.abs(depression - center_depression) <= half_v)
    )


def _has_line_of_sight(dem, transform, nodata, x0: float, y0: float, z0: float, x1: float, y1: float, z1: float) -> bool:
    distance = math.hypot(x1 - x0, y1 - y0)
    resolution = max(abs(float(transform.a)), abs(float(transform.e)))
    samples = max(2, min(240, math.ceil(distance / max(resolution * 2, 1))))
    for index in range(1, samples):
        t = index / samples
        x = x0 + (x1 - x0) * t
        y = y0 + (y1 - y0) * t
        terrain = _sample_nearest(dem, transform, x, y, nodata)
        if not math.isfinite(terrain):
            continue
        line_z = z0 + (z1 - z0) * t
        if terrain > line_z:
            return False
    return True


def _route_waypoints(payload: UavReconRequest) -> list[UavPlatformInput]:
    return payload.route.waypoints if payload.route and payload.route.waypoints else []


def _coverage_points(payload: UavReconRequest) -> list[UavPlatformInput]:
    waypoints = _route_waypoints(payload)
    if not waypoints:
        return [payload.uav]
    interval = payload.route.sample_interval_m if payload.route else 500
    points: list[UavPlatformInput] = []
    to_projected = Transformer.from_crs("EPSG:4326", f"EPSG:{utm_epsg_from_lonlat(waypoints[0].lon, waypoints[0].lat)}", always_xy=True)
    to_wgs84 = Transformer.from_crs(f"EPSG:{utm_epsg_from_lonlat(waypoints[0].lon, waypoints[0].lat)}", "EPSG:4326", always_xy=True)
    for start, end in zip(waypoints, waypoints[1:]):
        sx, sy = to_projected.transform(start.lon, start.lat)
        ex, ey = to_projected.transform(end.lon, end.lat)
        distance = math.hypot(ex - sx, ey - sy)
        steps = max(1, math.ceil(distance / interval))
        for step in range(steps):
            t = step / steps
            lon, lat = to_wgs84.transform(sx + (ex - sx) * t, sy + (ey - sy) * t)
            points.append(_interpolate_platform(start, end, lon, lat, t))
    points.append(waypoints[-1])
    return points


def _interpolate_platform(start: UavPlatformInput, end: UavPlatformInput, lon: float, lat: float, t: float) -> UavPlatformInput:
    return UavPlatformInput(
        lon=lon,
        lat=lat,
        altitude_m=start.altitude_m + (end.altitude_m - start.altitude_m) * t,
        altitude_mode=start.altitude_mode,
        heading_deg=_interpolate_angle(start.heading_deg, end.heading_deg, t),
        pitch_deg=start.pitch_deg + (end.pitch_deg - start.pitch_deg) * t,
        roll_deg=start.roll_deg + (end.roll_deg - start.roll_deg) * t,
    )


def _interpolate_angle(start: float, end: float, t: float) -> float:
    delta = ((end - start + 540) % 360) - 180
    return (start + delta * t) % 360


def _route_length_m(payload: UavReconRequest) -> float:
    waypoints = _route_waypoints(payload)
    if len(waypoints) < 2:
        return 0.0
    epsg = utm_epsg_from_lonlat(waypoints[0].lon, waypoints[0].lat)
    to_projected = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    total = 0.0
    for start, end in zip(waypoints, waypoints[1:]):
        sx, sy = to_projected.transform(start.lon, start.lat)
        ex, ey = to_projected.transform(end.lon, end.lat)
        total += math.hypot(ex - sx, ey - sy)
    return total


def _sample_nearest(dem, transform, x: float, y: float, nodata) -> float:
    col = int((x - transform.c) / transform.a)
    row = int((y - transform.f) / transform.e)
    if row < 0 or col < 0 or row >= dem.shape[0] or col >= dem.shape[1]:
        return float("nan")
    value = float(dem[row, col])
    if nodata is not None and value == nodata:
        return float("nan")
    return value


def _mask_to_geometry(mask, transform):
    geometries = [
        shape(geom)
        for geom, value in shapes(mask.astype(numpy.uint8), mask=mask, transform=transform)
        if value > 0
    ]
    if not geometries:
        return GeometryCollection()
    return unary_union(geometries)


def _project_geometry(geometry, transformer: Transformer):
    if geometry is None or geometry.is_empty:
        return geometry
    from shapely.ops import transform as shp_transform

    return shp_transform(transformer.transform, geometry)


def _write_feature_collection(path: Path, geometry, properties: dict | None = None) -> None:
    features = []
    if geometry is not None and not geometry.is_empty:
        features.append({"type": "Feature", "properties": properties or {}, "geometry": mapping(geometry)})
    _write_json_atomic(path, {"type": "FeatureCollection", "features": features})


def _ensure_staged_outputs_exist(staging_dir: Path) -> None:
    missing = [
        kind
        for kind, filename in UAV_OUTPUT_FILENAMES.items()
        if not (staging_dir / filename).exists() or (staging_dir / filename).stat().st_size <= 0
    ]
    if missing:
        raise AppError("OUTPUT_INCOMPLETE", f"UAV task staged outputs are incomplete: {', '.join(missing)}.", status_code=500)


def _commit_staged_outputs(staging_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename in UAV_OUTPUT_FILENAMES.values():
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
