import heapq
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
from shapely.geometry import GeometryCollection, LineString, MultiLineString, mapping, shape
from shapely.ops import unary_union

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.mobility import (
    MobilityAccessibilityMetrics,
    MobilityAccessibilityOutputs,
    MobilityAccessibilityRequest,
    MobilityModelMetadata,
    MobilityVehicleInput,
    MobilityVehicleMetrics,
)
from app.services.dem_store import find_dem_file
from app.services.geometry import project_geometry
from app.services.mobility_output_files import (
    MOBILITY_OUTPUT_FILENAMES,
    describe_mobility_output_files,
    list_mobility_task_output_files,
)
from app.services.mobility_task_store import mark_mobility_failed, mark_mobility_finished, mark_mobility_running
from app.services.projection import utm_epsg_from_lonlat


class PreparedMobilityDem:
    def __init__(
        self,
        projected_dem: Path,
        target_epsg: int,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        bounds,
        resolution_m: tuple[float, float],
    ) -> None:
        self.projected_dem = projected_dem
        self.target_epsg = target_epsg
        self.start_x = start_x
        self.start_y = start_y
        self.end_x = end_x
        self.end_y = end_y
        self.bounds = bounds
        self.resolution_m = resolution_m


class PathResult:
    def __init__(
        self,
        reachable: bool,
        path: list[tuple[int, int]],
        travel_time_seconds: float | None,
        failure_reason: str | None = None,
    ) -> None:
        self.reachable = reachable
        self.path = path
        self.travel_time_seconds = travel_time_seconds
        self.failure_reason = failure_reason


def run_mobility_task(task_id: str, payload: MobilityAccessibilityRequest) -> None:
    try:
        mark_mobility_running(task_id, "Preparing DEM and mobility projection.", 15)
        output_dir = settings.outputs_dir / task_id
        output_dir.mkdir(parents=True, exist_ok=True)
        staging_dir = output_dir / f".staging-{uuid4().hex}"
        staging_dir.mkdir(parents=True, exist_ok=False)

        try:
            prepared = _prepare_mobility_dem(find_dem_file(payload.dem_id), staging_dir / "dem_projected.tif", payload)
            mark_mobility_running(task_id, "Computing wheeled and tracked accessibility.", 55)
            outputs, output_files, metrics, model, warnings = _write_mobility_outputs(
                task_id, staging_dir, output_dir, prepared, payload
            )
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)

        mark_mobility_finished(task_id, metrics=metrics, outputs=outputs, output_files=output_files, model=model, warnings=warnings)
    except Exception as exc:
        mark_mobility_failed(task_id, str(exc))


def _prepare_mobility_dem(source: Path, destination: Path, payload: MobilityAccessibilityRequest) -> PreparedMobilityDem:
    import rasterio

    target_epsg = utm_epsg_from_lonlat(payload.start.lon, payload.start.lat)
    target_crs = CRS.from_epsg(target_epsg)
    to_target = Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)
    start_x, start_y = to_target.transform(payload.start.lon, payload.start.lat)
    end_x, end_y = to_target.transform(payload.end.lon, payload.end.lat)

    with rasterio.open(source) as src:
        if src.crs is None:
            raise AppError("DEM_WITHOUT_CRS", "DEM is missing coordinate reference system.")
        to_src = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        src_start_x, src_start_y = to_src.transform(payload.start.lon, payload.start.lat)
        src_end_x, src_end_y = to_src.transform(payload.end.lon, payload.end.lat)
        if not (src.bounds.left <= src_start_x <= src.bounds.right and src.bounds.bottom <= src_start_y <= src.bounds.top):
            raise AppError("MOBILITY_START_OUTSIDE_DEM", "Mobility start point is outside DEM bounds.", status_code=400)
        if not (src.bounds.left <= src_end_x <= src.bounds.right and src.bounds.bottom <= src_end_y <= src.bounds.top):
            raise AppError("MOBILITY_END_OUTSIDE_DEM", "Mobility end point is outside DEM bounds.", status_code=400)

        direct_distance = math.hypot(end_x - start_x, end_y - start_y)
        radius = payload.analysis.max_search_radius_m or max(3000.0, direct_distance * 1.5)
        min_x = min(start_x, end_x) - radius
        max_x = max(start_x, end_x) + radius
        min_y = min(start_y, end_y) - radius
        max_y = max(start_y, end_y) + radius
        src_crop_bounds = transform_bounds(target_crs, src.crs, min_x, min_y, max_x, max_y, densify_pts=21)
        crop_bounds = (
            max(src.bounds.left, src_crop_bounds[0]),
            max(src.bounds.bottom, src_crop_bounds[1]),
            min(src.bounds.right, src_crop_bounds[2]),
            min(src.bounds.top, src_crop_bounds[3]),
        )
        if crop_bounds[0] >= crop_bounds[2] or crop_bounds[1] >= crop_bounds[3]:
            raise AppError("RANGE_OUTSIDE_DEM", "Mobility search range does not intersect DEM bounds.", status_code=400)

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
    return PreparedMobilityDem(
        projected_dem=destination,
        target_epsg=target_epsg,
        start_x=start_x,
        start_y=start_y,
        end_x=end_x,
        end_y=end_y,
        bounds=bounds,
        resolution_m=(abs(dst_transform.a), abs(dst_transform.e)),
    )


def _write_mobility_outputs(
    task_id: str,
    staging_dir: Path,
    output_dir: Path,
    prepared: PreparedMobilityDem,
    payload: MobilityAccessibilityRequest,
):
    import rasterio

    with rasterio.open(prepared.projected_dem) as src:
        dem = src.read(1)
        transform = src.transform
        nodata = src.nodata

    result = _compute_mobility(dem, transform, nodata, prepared, payload)
    transformer = Transformer.from_crs(f"EPSG:{prepared.target_epsg}", "EPSG:4326", always_xy=True)
    tolerance = payload.analysis.output_simplify_tolerance_m
    if tolerance is None:
        tolerance = max(prepared.resolution_m)

    wheeled_path = _path_to_linestring(result["wheeled_path"], transform)
    tracked_path = _path_to_linestring(result["tracked_path"], transform)
    road_geom = _mask_to_geometry(result["road_mask"], transform)
    if tolerance > 0:
        if wheeled_path is not None and not wheeled_path.is_empty:
            wheeled_path = wheeled_path.simplify(tolerance, preserve_topology=True)
        if tracked_path is not None and not tracked_path.is_empty:
            tracked_path = tracked_path.simplify(tolerance, preserve_topology=True)
        road_geom = road_geom.simplify(tolerance, preserve_topology=True)

    wheeled_path_path = staging_dir / "wheeled_path.geojson"
    tracked_path_path = staging_dir / "tracked_path.geojson"
    road_mask_path = staging_dir / "road_mask.geojson"
    cost_summary_path = staging_dir / "cost_summary.json"
    model_path = staging_dir / "model_metadata.json"
    manifest_path = staging_dir / "output_manifest.json"

    _write_feature_collection(wheeled_path_path, project_geometry(wheeled_path, transformer), {"vehicle": "wheeled"})
    _write_feature_collection(tracked_path_path, project_geometry(tracked_path, transformer), {"vehicle": "tracked"})
    _write_feature_collection(road_mask_path, project_geometry(road_geom, transformer), {"kind": "road_mask"})

    metrics: MobilityAccessibilityMetrics = result["metrics"]
    model = MobilityModelMetadata(
        target_epsg=prepared.target_epsg,
        start_projected_xy=[prepared.start_x, prepared.start_y],
        end_projected_xy=[prepared.end_x, prepared.end_y],
        projected_dem_bounds=[prepared.bounds.left, prepared.bounds.bottom, prepared.bounds.right, prepared.bounds.top],
        projected_dem_resolution_m=[prepared.resolution_m[0], prepared.resolution_m[1]],
        start_ground_elevation_m=result["start_ground"],
        end_ground_elevation_m=result["end_ground"],
        allow_diagonal=payload.analysis.allow_diagonal,
        max_search_radius_m=payload.analysis.max_search_radius_m,
        simplify_tolerance_m=tolerance,
        road_network_used=bool(payload.road_network and payload.road_network.geojson),
        road_buffer_m=payload.road_network.road_buffer_m if payload.road_network else 0,
    )
    outputs = MobilityAccessibilityOutputs(
        wheeled_path_geojson=f"/outputs/{task_id}/wheeled_path.geojson",
        tracked_path_geojson=f"/outputs/{task_id}/tracked_path.geojson",
        road_mask_geojson=f"/outputs/{task_id}/road_mask.geojson",
        cost_summary_json=f"/outputs/{task_id}/cost_summary.json",
        model_metadata_json=f"/outputs/{task_id}/model_metadata.json",
        output_manifest_json=f"/outputs/{task_id}/output_manifest.json",
    )
    _write_json_atomic(cost_summary_path, result["cost_summary"])
    _write_json_atomic(model_path, {"model": model.model_dump(), "metrics": metrics.model_dump(), "warnings": []})
    output_paths = {kind: staging_dir / filename for kind, filename in MOBILITY_OUTPUT_FILENAMES.items()}
    manifest_files = describe_mobility_output_files(task_id, output_paths)
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
    output_files = list_mobility_task_output_files(task_id)
    return outputs, output_files, metrics, model, []


def _compute_mobility(dem, transform, nodata, prepared: PreparedMobilityDem, payload: MobilityAccessibilityRequest) -> dict:
    finite = numpy.isfinite(dem)
    if nodata is not None:
        finite &= dem != nodata
    slope = _slope_degrees(dem, transform, finite)
    road_mask, road_multiplier = _road_masks(dem.shape, transform, prepared, payload)
    start_rc = _xy_to_rc(transform, prepared.start_x, prepared.start_y)
    end_rc = _xy_to_rc(transform, prepared.end_x, prepared.end_y)
    if not _is_inside(dem.shape, start_rc):
        raise AppError("MOBILITY_START_OUTSIDE_DEM", "Mobility start point is outside projected DEM bounds.", status_code=400)
    if not _is_inside(dem.shape, end_rc):
        raise AppError("MOBILITY_END_OUTSIDE_DEM", "Mobility end point is outside projected DEM bounds.", status_code=400)
    start_ground = _value_at(dem, start_rc, nodata, "start")
    end_ground = _value_at(dem, end_rc, nodata, "end")

    wheeled_result = _vehicle_result(
        payload.vehicles.wheeled,
        "wheeled",
        finite,
        slope,
        road_mask,
        road_multiplier,
        transform,
        start_rc,
        end_rc,
        payload.analysis.allow_diagonal,
    )
    tracked_result = _vehicle_result(
        payload.vehicles.tracked,
        "tracked",
        finite,
        slope,
        road_mask,
        road_multiplier,
        transform,
        start_rc,
        end_rc,
        payload.analysis.allow_diagonal,
    )
    metrics = MobilityAccessibilityMetrics(
        wheeled=wheeled_result["metrics"],
        tracked=tracked_result["metrics"],
    )
    metrics.winner, metrics.time_saving_seconds, metrics.time_saving_ratio = _winner(metrics.wheeled, metrics.tracked)
    return {
        "metrics": metrics,
        "wheeled_path": wheeled_result["path"],
        "tracked_path": tracked_result["path"],
        "road_mask": road_mask,
        "start_ground": start_ground,
        "end_ground": end_ground,
        "cost_summary": {
            "wheeled": wheeled_result["summary"],
            "tracked": tracked_result["summary"],
            "road_network_used": bool(payload.road_network and payload.road_network.geojson),
        },
    }


def _vehicle_result(
    vehicle: MobilityVehicleInput,
    vehicle_name: str,
    finite,
    slope,
    road_mask,
    road_multiplier,
    transform,
    start_rc: tuple[int, int],
    end_rc: tuple[int, int],
    allow_diagonal: bool,
) -> dict:
    if not vehicle.enabled:
        metrics = MobilityVehicleMetrics(reachable=False, failure_reason=f"{vehicle_name} vehicle is disabled.")
        return {"metrics": metrics, "path": [], "summary": {"enabled": False}}
    passable = finite & (slope <= vehicle.max_slope_deg)
    if not passable[start_rc]:
        metrics = MobilityVehicleMetrics(reachable=False, failure_reason="Start point is not passable for this vehicle.")
        return {"metrics": metrics, "path": [], "summary": {"enabled": True, "passable_cell_count": int(passable.sum())}}
    if not passable[end_rc]:
        metrics = MobilityVehicleMetrics(reachable=False, failure_reason="End point is not passable for this vehicle.")
        return {"metrics": metrics, "path": [], "summary": {"enabled": True, "passable_cell_count": int(passable.sum())}}

    speed_mps = _speed_grid(vehicle, slope, road_mask, road_multiplier)
    path_result = _shortest_path(passable, speed_mps, transform, start_rc, end_rc, allow_diagonal)
    if not path_result.reachable:
        metrics = MobilityVehicleMetrics(reachable=False, failure_reason=path_result.failure_reason)
        return {"metrics": metrics, "path": [], "summary": {"enabled": True, "passable_cell_count": int(passable.sum())}}
    metrics = _path_metrics(path_result.path, path_result.travel_time_seconds or 0, slope, road_mask, transform)
    return {
        "metrics": metrics,
        "path": path_result.path,
        "summary": {
            "enabled": True,
            "passable_cell_count": int(passable.sum()),
            "min_speed_mps": float(numpy.nanmin(speed_mps[passable])) if passable.any() else 0,
            "max_speed_mps": float(numpy.nanmax(speed_mps[passable])) if passable.any() else 0,
        },
    }


def _slope_degrees(dem, transform, finite):
    filled = numpy.where(finite, dem, numpy.nan)
    mean_value = float(numpy.nanmean(filled)) if numpy.isfinite(filled).any() else 0.0
    filled = numpy.where(numpy.isfinite(filled), filled, mean_value)
    gy, gx = numpy.gradient(filled, abs(float(transform.e)), abs(float(transform.a)))
    slope = numpy.degrees(numpy.arctan(numpy.hypot(gx, gy)))
    return numpy.where(finite, slope, 90.0)


def _road_masks(shape, transform, prepared: PreparedMobilityDem, payload: MobilityAccessibilityRequest):
    from rasterio.features import rasterize

    road_mask = numpy.zeros(shape, dtype=bool)
    multiplier = numpy.ones(shape, dtype=numpy.float64)
    road_network = payload.road_network
    if not road_network or not road_network.geojson:
        return road_mask, multiplier
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{prepared.target_epsg}", always_xy=True)
    shapes_with_values = []
    for geometry, factor in _road_geometries(road_network.geojson, road_network.road_classes):
        projected = project_geometry(geometry, transformer)
        if road_network.road_buffer_m > 0:
            projected = projected.buffer(road_network.road_buffer_m, resolution=8)
        if not projected.is_empty:
            shapes_with_values.append((projected, float(factor)))
    if not shapes_with_values:
        return road_mask, multiplier
    values = rasterize(shapes_with_values, out_shape=shape, transform=transform, fill=1.0, dtype=numpy.float64)
    road_mask = values > 1.0
    multiplier = numpy.maximum(multiplier, values)
    return road_mask, multiplier


def _road_geometries(geojson: dict, road_classes: dict[str, float]):
    features = geojson.get("features") if geojson.get("type") == "FeatureCollection" else [{"type": "Feature", "geometry": geojson, "properties": {}}]
    if not isinstance(features, list):
        raise AppError("INVALID_ROAD_NETWORK", "Road network GeoJSON has invalid features.", status_code=400)
    for feature in features:
        if not isinstance(feature, dict) or not feature.get("geometry"):
            continue
        geometry = shape(feature["geometry"])
        if not isinstance(geometry, (LineString, MultiLineString)):
            continue
        properties = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
        road_class = str(properties.get("class") or properties.get("road_class") or properties.get("highway") or "").lower()
        factor = road_classes.get(road_class, 1.2)
        yield geometry, factor


def _speed_grid(vehicle: MobilityVehicleInput, slope, road_mask, road_multiplier):
    base_speed_mps = vehicle.base_speed_kph * 1000 / 3600
    slope_fraction = numpy.clip(slope / max(vehicle.max_slope_deg, 0.001), 0, 1)
    slope_factor = numpy.maximum(0.05, 1 - vehicle.slope_penalty * slope_fraction * slope_fraction)
    terrain_multiplier = numpy.where(road_mask, vehicle.road_speed_multiplier * road_multiplier, vehicle.offroad_speed_multiplier)
    return base_speed_mps * slope_factor * terrain_multiplier


def _shortest_path(passable, speed_mps, transform, start_rc, end_rc, allow_diagonal: bool) -> PathResult:
    height, width = passable.shape
    distances = numpy.full((height, width), numpy.inf, dtype=numpy.float64)
    previous: dict[tuple[int, int], tuple[int, int]] = {}
    distances[start_rc] = 0.0
    heap = [(0.0, start_rc)]
    neighbors = _neighbors(allow_diagonal)
    while heap:
        cost, current = heapq.heappop(heap)
        if cost > distances[current]:
            continue
        if current == end_rc:
            return PathResult(True, _reconstruct_path(previous, start_rc, end_rc), float(cost))
        row, col = current
        for dr, dc, distance_m in neighbors:
            next_rc = (row + dr, col + dc)
            if not _is_inside(passable.shape, next_rc) or not passable[next_rc]:
                continue
            step_distance = distance_m * max(abs(float(transform.a)), abs(float(transform.e)))
            avg_speed = max((float(speed_mps[current]) + float(speed_mps[next_rc])) / 2, 0.001)
            new_cost = cost + step_distance / avg_speed
            if new_cost < distances[next_rc]:
                distances[next_rc] = new_cost
                previous[next_rc] = current
                heapq.heappush(heap, (new_cost, next_rc))
    return PathResult(False, [], None, "No passable path connects start and end.")


def _neighbors(allow_diagonal: bool):
    base = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0)]
    if allow_diagonal:
        root2 = math.sqrt(2)
        base.extend([(-1, -1, root2), (-1, 1, root2), (1, -1, root2), (1, 1, root2)])
    return base


def _reconstruct_path(previous: dict[tuple[int, int], tuple[int, int]], start_rc, end_rc):
    path = [end_rc]
    current = end_rc
    while current != start_rc:
        current = previous[current]
        path.append(current)
    path.reverse()
    return path


def _path_metrics(path: list[tuple[int, int]], travel_time_seconds: float, slope, road_mask, transform) -> MobilityVehicleMetrics:
    distance = 0.0
    road_distance = 0.0
    slope_values = []
    for current, nxt in zip(path, path[1:]):
        dr = nxt[0] - current[0]
        dc = nxt[1] - current[1]
        step_distance = math.hypot(dr * float(transform.e), dc * float(transform.a))
        distance += step_distance
        if road_mask[current] or road_mask[nxt]:
            road_distance += step_distance
        slope_values.append(float(slope[nxt]))
    average_speed_kph = distance / travel_time_seconds * 3.6 if travel_time_seconds > 0 else 0
    return MobilityVehicleMetrics(
        reachable=True,
        travel_time_seconds=travel_time_seconds,
        travel_distance_m=distance,
        average_speed_kph=average_speed_kph,
        road_distance_m=road_distance,
        offroad_distance_m=max(0.0, distance - road_distance),
        max_slope_deg=max(slope_values) if slope_values else None,
        mean_slope_deg=sum(slope_values) / len(slope_values) if slope_values else None,
    )


def _winner(wheeled: MobilityVehicleMetrics, tracked: MobilityVehicleMetrics):
    if not wheeled.reachable and not tracked.reachable:
        return "none", None, None
    if wheeled.reachable and not tracked.reachable:
        return "wheeled", None, None
    if tracked.reachable and not wheeled.reachable:
        return "tracked", None, None
    wheeled_time = wheeled.travel_time_seconds or 0
    tracked_time = tracked.travel_time_seconds or 0
    if math.isclose(wheeled_time, tracked_time, rel_tol=0.01, abs_tol=5):
        return "tie", abs(wheeled_time - tracked_time), 0.0
    faster = min(wheeled_time, tracked_time)
    slower = max(wheeled_time, tracked_time)
    winner = "wheeled" if wheeled_time < tracked_time else "tracked"
    return winner, slower - faster, (slower - faster) / slower if slower > 0 else None


def _xy_to_rc(transform, x: float, y: float) -> tuple[int, int]:
    col = int((x - transform.c) / transform.a)
    row = int((y - transform.f) / transform.e)
    return row, col


def _is_inside(shape, rc: tuple[int, int]) -> bool:
    row, col = rc
    return 0 <= row < shape[0] and 0 <= col < shape[1]


def _value_at(dem, rc: tuple[int, int], nodata, label: str) -> float:
    value = float(dem[rc])
    if not math.isfinite(value) or (nodata is not None and value == nodata):
        raise AppError("MOBILITY_NO_DATA", f"The {label} point falls on DEM nodata.", status_code=400)
    return value


def _path_to_linestring(path: list[tuple[int, int]], transform):
    if len(path) < 2:
        return GeometryCollection()
    points = []
    for row, col in path:
        x = transform.c + (float(col) + 0.5) * transform.a
        y = transform.f + (float(row) + 0.5) * transform.e
        points.append((x, y))
    return LineString(points)


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
        for kind, filename in MOBILITY_OUTPUT_FILENAMES.items()
        if not (staging_dir / filename).exists() or (staging_dir / filename).stat().st_size <= 0
    ]
    if missing:
        raise AppError("OUTPUT_INCOMPLETE", f"Mobility task staged outputs are incomplete: {', '.join(missing)}.", status_code=500)


def _commit_staged_outputs(staging_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename in MOBILITY_OUTPUT_FILENAMES.values():
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
