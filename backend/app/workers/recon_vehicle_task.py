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
from shapely.geometry import GeometryCollection, Point, mapping, shape
from shapely.ops import unary_union

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.recon_vehicle import (
    ReconVehicleCoverageMetrics,
    ReconVehicleCoverageOutputs,
    ReconVehicleCoverageRequest,
    ReconVehicleModelMetadata,
    ReconVehiclePositionInput,
)
from app.services.dem_store import find_dem_file
from app.services.geometry import make_range_geometry, project_geometry
from app.services.projection import utm_epsg_from_lonlat
from app.services.recon_vehicle_output_files import (
    RECON_VEHICLE_OUTPUT_FILENAMES,
    describe_recon_vehicle_output_files,
    list_recon_vehicle_task_output_files,
)
from app.services.recon_vehicle_task_store import (
    mark_recon_vehicle_failed,
    mark_recon_vehicle_finished,
    mark_recon_vehicle_running,
)


class PreparedReconVehicleDem:
    def __init__(
        self,
        projected_dem: Path,
        target_epsg: int,
        vehicle_x: float,
        vehicle_y: float,
        bounds,
        resolution_m: tuple[float, float],
    ) -> None:
        self.projected_dem = projected_dem
        self.target_epsg = target_epsg
        self.vehicle_x = vehicle_x
        self.vehicle_y = vehicle_y
        self.bounds = bounds
        self.resolution_m = resolution_m


def run_recon_vehicle_task(task_id: str, payload: ReconVehicleCoverageRequest) -> None:
    try:
        mark_recon_vehicle_running(task_id, "Preparing DEM and recon vehicle projection.", 15)
        output_dir = settings.outputs_dir / task_id
        output_dir.mkdir(parents=True, exist_ok=True)
        staging_dir = output_dir / f".staging-{uuid4().hex}"
        staging_dir.mkdir(parents=True, exist_ok=False)

        try:
            prepared = _prepare_recon_vehicle_dem(find_dem_file(payload.dem_id), staging_dir / "dem_projected.tif", payload)
            mark_recon_vehicle_running(task_id, "Computing terrain-visible recon coverage.", 55)
            outputs, output_files, metrics, model, warnings = _write_recon_vehicle_outputs(
                task_id, staging_dir, output_dir, prepared, payload
            )
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)

        mark_recon_vehicle_finished(task_id, metrics=metrics, outputs=outputs, output_files=output_files, model=model, warnings=warnings)
    except Exception as exc:
        mark_recon_vehicle_failed(task_id, str(exc))


def _prepare_recon_vehicle_dem(source: Path, destination: Path, payload: ReconVehicleCoverageRequest) -> PreparedReconVehicleDem:
    import rasterio

    coverage_points = _coverage_points(payload)
    target_epsg = utm_epsg_from_lonlat(payload.vehicle.lon, payload.vehicle.lat)
    target_crs = CRS.from_epsg(target_epsg)
    to_target = Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)
    vehicle_x, vehicle_y = to_target.transform(payload.vehicle.lon, payload.vehicle.lat)
    projected_points = [to_target.transform(point.lon, point.lat) for point in coverage_points]

    with rasterio.open(source) as src:
        if src.crs is None:
            raise AppError("DEM_WITHOUT_CRS", "DEM is missing coordinate reference system.")
        src_vehicle_x, src_vehicle_y = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True).transform(
            payload.vehicle.lon, payload.vehicle.lat
        )
        if not (src.bounds.left <= src_vehicle_x <= src.bounds.right and src.bounds.bottom <= src_vehicle_y <= src.bounds.top):
            raise AppError("RECON_VEHICLE_OUTSIDE_DEM", "Recon vehicle point is outside DEM bounds.", status_code=400)

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
            raise AppError("RANGE_OUTSIDE_DEM", "Recon vehicle sensor range does not intersect DEM bounds.", status_code=400)

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
    return PreparedReconVehicleDem(
        projected_dem=destination,
        target_epsg=target_epsg,
        vehicle_x=vehicle_x,
        vehicle_y=vehicle_y,
        bounds=bounds,
        resolution_m=(abs(dst_transform.a), abs(dst_transform.e)),
    )


def _write_recon_vehicle_outputs(
    task_id: str,
    staging_dir: Path,
    output_dir: Path,
    prepared: PreparedReconVehicleDem,
    payload: ReconVehicleCoverageRequest,
):
    import rasterio

    with rasterio.open(prepared.projected_dem) as src:
        dem = src.read(1)
        transform = src.transform
        nodata = src.nodata

    masks, model, point_count, route_length_m, visible_area_sum = _compute_recon_vehicle_masks(
        dem,
        transform,
        nodata,
        prepared,
        payload,
        staging_dir,
    )
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

    _write_feature_collection(footprint_path, project_geometry(footprint_geom, transformer), {"kind": "recon_vehicle_footprint"})
    _write_feature_collection(visible_path, project_geometry(visible_geom, transformer), {"kind": "recon_vehicle_visible"})
    _write_feature_collection(blocked_path, project_geometry(blocked_geom, transformer), {"kind": "recon_vehicle_blocked"})

    cell_area = abs(float(transform.a) * float(transform.e))
    theoretical_area = float(masks["footprint"].sum()) * cell_area
    visible_area = float(masks["visible"].sum()) * cell_area
    blocked_area = float(masks["blocked"].sum()) * cell_area
    metrics = ReconVehicleCoverageMetrics(
        theoretical_area_m2=theoretical_area,
        visible_area_m2=visible_area,
        blocked_area_m2=blocked_area,
        blocked_ratio=blocked_area / theoretical_area if theoretical_area > 0 else 0,
        max_range_m=payload.sensor.max_range_m,
        effective_view_angle_deg=360 if payload.sensor.scan_mode == "omni" else payload.sensor.view_angle_deg,
        coverage_point_count=point_count,
        route_length_m=route_length_m,
        average_visible_area_m2=visible_area_sum / point_count if point_count > 0 else 0,
        overlap_area_m2=max(0.0, visible_area_sum - visible_area),
        vehicle_ground_elevation_m=model.vehicle_ground_elevation_m,
        sensor_altitude_m=model.sensor_altitude_m,
    )
    outputs = ReconVehicleCoverageOutputs(
        footprint_geojson=f"/outputs/{task_id}/footprint.geojson",
        visible_geojson=f"/outputs/{task_id}/visible.geojson",
        blocked_geojson=f"/outputs/{task_id}/blocked.geojson",
        model_metadata_json=f"/outputs/{task_id}/model_metadata.json",
        output_manifest_json=f"/outputs/{task_id}/output_manifest.json",
    )
    _write_json_atomic(model_path, {"model": model.model_dump(), "metrics": metrics.model_dump(), "warnings": []})
    output_paths = {kind: staging_dir / filename for kind, filename in RECON_VEHICLE_OUTPUT_FILENAMES.items()}
    manifest_files = describe_recon_vehicle_output_files(task_id, output_paths)
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
    output_files = list_recon_vehicle_task_output_files(task_id)
    return outputs, output_files, metrics, model, []


def _compute_recon_vehicle_masks(
    dem,
    transform,
    nodata,
    prepared: PreparedReconVehicleDem,
    payload: ReconVehicleCoverageRequest,
    staging_dir: Path,
):
    finite = numpy.isfinite(dem)
    if nodata is not None:
        finite &= dem != nodata
    footprint = numpy.zeros_like(finite, dtype=bool)
    visible = numpy.zeros_like(finite, dtype=bool)
    visible_area_sum = 0.0
    cell_area = abs(float(transform.a) * float(transform.e))
    commands: list[list[str]] = []
    first_ground = 0.0
    first_altitude = 0.0
    coverage_points = _coverage_points(payload)
    to_target = Transformer.from_crs("EPSG:4326", f"EPSG:{prepared.target_epsg}", always_xy=True)

    for index, point in enumerate(coverage_points):
        point_x, point_y = to_target.transform(point.lon, point.lat)
        ground = _sample_nearest(dem, transform, point_x, point_y, nodata)
        if not math.isfinite(ground):
            continue
        sensor_altitude = ground + point.mast_height_m
        if index == 0:
            first_ground = ground
            first_altitude = sensor_altitude
        point_geom = _point_footprint_geometry(point_x, point_y, point, payload)
        point_footprint = _geometry_to_mask(point_geom, finite.shape, transform) & finite
        if payload.analysis.use_terrain_occlusion:
            viewshed = staging_dir / f"viewshed_{index}.tif"
            command = _run_gdal_viewshed(prepared.projected_dem, viewshed, point_x, point_y, point.mast_height_m, payload)
            commands.append(command)
            point_visible_raw = _read_viewshed_mask(viewshed)
            point_visible = point_visible_raw & point_footprint
        else:
            point_visible = point_footprint.copy()
        footprint |= point_footprint
        visible |= point_visible
        visible_area_sum += float(point_visible.sum()) * cell_area

    blocked = footprint & ~visible
    route_length_m = _route_length_m(payload)
    model = ReconVehicleModelMetadata(
        target_epsg=prepared.target_epsg,
        vehicle_projected_xy=[prepared.vehicle_x, prepared.vehicle_y],
        projected_dem_bounds=[prepared.bounds.left, prepared.bounds.bottom, prepared.bounds.right, prepared.bounds.top],
        projected_dem_resolution_m=[prepared.resolution_m[0], prepared.resolution_m[1]],
        vehicle_ground_elevation_m=float(first_ground),
        sensor_altitude_m=float(first_altitude),
        mast_height_m=payload.vehicle.mast_height_m,
        sensor_type=payload.sensor.sensor_type,
        min_range_m=payload.sensor.min_range_m,
        max_range_m=payload.sensor.max_range_m,
        scan_mode=payload.sensor.scan_mode,
        heading_deg=payload.vehicle.heading_deg,
        view_angle_deg=payload.sensor.view_angle_deg,
        target_height_m=payload.target.height_m,
        use_terrain_occlusion=payload.analysis.use_terrain_occlusion,
        use_curvature=payload.analysis.use_curvature,
        curvature_coeff=payload.analysis.curvature_coeff,
        simplify_tolerance_m=payload.analysis.output_simplify_tolerance_m or max(prepared.resolution_m),
        coverage_mode="route" if _route_waypoints(payload) else "single",
        coverage_point_count=len(coverage_points),
        route_length_m=route_length_m,
        gdal_viewshed_commands=commands,
    )
    return {"footprint": footprint, "visible": visible, "blocked": blocked}, model, len(coverage_points), route_length_m, visible_area_sum


def _point_footprint_geometry(point_x: float, point_y: float, point: ReconVehiclePositionInput, payload: ReconVehicleCoverageRequest):
    outer = make_range_geometry(
        point_x,
        point_y,
        payload.sensor.max_range_m,
        payload.sensor.scan_mode,
        point.heading_deg,
        payload.sensor.view_angle_deg,
    )
    if payload.sensor.min_range_m <= 0:
        return outer
    inner = Point(point_x, point_y).buffer(payload.sensor.min_range_m, resolution=96)
    return outer.difference(inner)


def _run_gdal_viewshed(
    dem: Path,
    viewshed: Path,
    observer_x: float,
    observer_y: float,
    observer_height_m: float,
    payload: ReconVehicleCoverageRequest,
) -> list[str]:
    if shutil.which("gdal_viewshed") is None:
        raise AppError("GDAL_VIEWSHED_NOT_FOUND", "gdal_viewshed command is not available.", status_code=500)
    command = [
        "gdal_viewshed",
        "-ox",
        str(observer_x),
        "-oy",
        str(observer_y),
        "-oz",
        str(observer_height_m),
        "-tz",
        str(payload.target.height_m),
        "-md",
        str(payload.sensor.max_range_m),
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


def _read_viewshed_mask(path: Path):
    import rasterio

    with rasterio.open(path) as src:
        data = src.read(1)
        nodata = src.nodata
    mask = data > 0
    if nodata is not None:
        mask &= data != nodata
    return mask


def _route_waypoints(payload: ReconVehicleCoverageRequest) -> list[ReconVehiclePositionInput]:
    return payload.route.waypoints if payload.route and payload.route.waypoints else []


def _coverage_points(payload: ReconVehicleCoverageRequest) -> list[ReconVehiclePositionInput]:
    waypoints = _route_waypoints(payload)
    if not waypoints:
        return [payload.vehicle]
    interval = payload.route.sample_interval_m if payload.route else 500
    points: list[ReconVehiclePositionInput] = []
    epsg = utm_epsg_from_lonlat(waypoints[0].lon, waypoints[0].lat)
    to_projected = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    to_wgs84 = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    for start, end in zip(waypoints, waypoints[1:]):
        sx, sy = to_projected.transform(start.lon, start.lat)
        ex, ey = to_projected.transform(end.lon, end.lat)
        distance = math.hypot(ex - sx, ey - sy)
        steps = max(1, math.ceil(distance / interval))
        for step in range(steps):
            t = step / steps
            lon, lat = to_wgs84.transform(sx + (ex - sx) * t, sy + (ey - sy) * t)
            points.append(
                ReconVehiclePositionInput(
                    lon=lon,
                    lat=lat,
                    heading_deg=_interpolate_angle(start.heading_deg, end.heading_deg, t),
                    mast_height_m=start.mast_height_m + (end.mast_height_m - start.mast_height_m) * t,
                )
            )
    points.append(waypoints[-1])
    return points


def _interpolate_angle(start: float, end: float, t: float) -> float:
    delta = ((end - start + 540) % 360) - 180
    return (start + delta * t) % 360


def _route_length_m(payload: ReconVehicleCoverageRequest) -> float:
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


def _geometry_to_mask(geometry, out_shape, transform):
    from rasterio.features import rasterize

    if geometry is None or geometry.is_empty:
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


def _write_feature_collection(path: Path, geometry, properties: dict | None = None) -> None:
    features = []
    if geometry is not None and not geometry.is_empty:
        features.append({"type": "Feature", "properties": properties or {}, "geometry": mapping(geometry)})
    _write_json_atomic(path, {"type": "FeatureCollection", "features": features})


def _ensure_staged_outputs_exist(staging_dir: Path) -> None:
    missing = [
        kind
        for kind, filename in RECON_VEHICLE_OUTPUT_FILENAMES.items()
        if not (staging_dir / filename).exists() or (staging_dir / filename).stat().st_size <= 0
    ]
    if missing:
        raise AppError("OUTPUT_INCOMPLETE", f"Recon vehicle task staged outputs are incomplete: {', '.join(missing)}.", status_code=500)


def _commit_staged_outputs(staging_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename in RECON_VEHICLE_OUTPUT_FILENAMES.values():
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
