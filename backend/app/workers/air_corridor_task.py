import heapq
import json
import math
import os
import shutil
from pathlib import Path
from uuid import uuid4

import numpy
from pyproj import CRS, Transformer
from rasterio.transform import array_bounds
from rasterio.windows import from_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds
from shapely.geometry import GeometryCollection, LineString, Point, mapping
from shapely.ops import unary_union

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.air_corridor import (
    AirCorridorModelMetadata,
    AirCorridorPlanningMetrics,
    AirCorridorPlanningOutputs,
    AirCorridorPlanningRequest,
)
from app.services.air_corridor_output_files import (
    AIR_CORRIDOR_OUTPUT_FILENAMES,
    describe_air_corridor_output_files,
    list_air_corridor_task_output_files,
)
from app.services.air_corridor_task_store import mark_air_corridor_failed, mark_air_corridor_finished, mark_air_corridor_running
from app.services.dem_store import find_dem_file
from app.services.geometry import project_geometry
from app.services.projection import utm_epsg_from_lonlat
from app.scene3d.air_corridor import write_air_corridor_glb


class PreparedAirCorridorDem:
    def __init__(
        self,
        projected_dem: Path,
        target_epsg: int,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        threat_xy: dict[str, tuple[float, float]],
        bounds,
        resolution_m: tuple[float, float],
    ) -> None:
        self.projected_dem = projected_dem
        self.target_epsg = target_epsg
        self.start_x = start_x
        self.start_y = start_y
        self.end_x = end_x
        self.end_y = end_y
        self.threat_xy = threat_xy
        self.bounds = bounds
        self.resolution_m = resolution_m


class CorridorPathResult:
    def __init__(self, found: bool, path: list[tuple[int, int, int]], cost: float | None, failure_reason: str | None = None) -> None:
        self.found = found
        self.path = path
        self.cost = cost
        self.failure_reason = failure_reason


def run_air_corridor_task(task_id: str, payload: AirCorridorPlanningRequest) -> None:
    try:
        mark_air_corridor_running(task_id, "Preparing DEM and air corridor projection.", 15)
        output_dir = settings.outputs_dir / task_id
        if output_dir.exists():
            raise AppError(
                "OUTPUT_DIRECTORY_EXISTS",
                f"Air corridor output directory already exists: {task_id}.",
                status_code=500,
            )
        staging_dir = output_dir.with_name(
            f".{output_dir.name}.staging-{uuid4().hex}"
        )
        staging_dir.mkdir(parents=True, exist_ok=False)

        try:
            prepared = _prepare_air_corridor_dem(find_dem_file(payload.dem_id), staging_dir / "dem_projected.tif", payload)
            mark_air_corridor_running(task_id, "Planning low-risk air corridor.", 55)
            outputs, output_files, metrics, model, warnings = _write_air_corridor_outputs(
                task_id, staging_dir, output_dir, prepared, payload
            )
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)

        mark_air_corridor_finished(task_id, metrics=metrics, outputs=outputs, output_files=output_files, model=model, warnings=warnings)
    except Exception as exc:
        mark_air_corridor_failed(task_id, str(exc))


def _prepare_air_corridor_dem(source: Path, destination: Path, payload: AirCorridorPlanningRequest) -> PreparedAirCorridorDem:
    import rasterio

    target_epsg = utm_epsg_from_lonlat(payload.start.lon, payload.start.lat)
    target_crs = CRS.from_epsg(target_epsg)
    to_target = Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)
    start_x, start_y = to_target.transform(payload.start.lon, payload.start.lat)
    end_x, end_y = to_target.transform(payload.end.lon, payload.end.lat)
    threat_xy = {threat.id: to_target.transform(threat.lon, threat.lat) for threat in payload.threats}

    with rasterio.open(source) as src:
        if src.crs is None:
            raise AppError("DEM_WITHOUT_CRS", "DEM is missing coordinate reference system.")
        to_src = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        src_start_x, src_start_y = to_src.transform(payload.start.lon, payload.start.lat)
        src_end_x, src_end_y = to_src.transform(payload.end.lon, payload.end.lat)
        if not (src.bounds.left <= src_start_x <= src.bounds.right and src.bounds.bottom <= src_start_y <= src.bounds.top):
            raise AppError("AIR_CORRIDOR_START_OUTSIDE_DEM", "Air corridor start point is outside DEM bounds.", status_code=400)
        if not (src.bounds.left <= src_end_x <= src.bounds.right and src.bounds.bottom <= src_end_y <= src.bounds.top):
            raise AppError("AIR_CORRIDOR_END_OUTSIDE_DEM", "Air corridor end point is outside DEM bounds.", status_code=400)

        direct_distance = math.hypot(end_x - start_x, end_y - start_y)
        max_threat_radius = max((threat.warning_zone_radius_m or threat.max_range_m for threat in payload.threats), default=0)
        radius = max(3000.0, direct_distance * 0.75, max_threat_radius)
        min_x = min([start_x, end_x, *[xy[0] for xy in threat_xy.values()]]) - radius
        max_x = max([start_x, end_x, *[xy[0] for xy in threat_xy.values()]]) + radius
        min_y = min([start_y, end_y, *[xy[1] for xy in threat_xy.values()]]) - radius
        max_y = max([start_y, end_y, *[xy[1] for xy in threat_xy.values()]]) + radius

        src_crop_bounds = transform_bounds(target_crs, src.crs, min_x, min_y, max_x, max_y, densify_pts=21)
        crop_bounds = (
            max(src.bounds.left, src_crop_bounds[0]),
            max(src.bounds.bottom, src_crop_bounds[1]),
            min(src.bounds.right, src_crop_bounds[2]),
            min(src.bounds.top, src_crop_bounds[3]),
        )
        if crop_bounds[0] >= crop_bounds[2] or crop_bounds[1] >= crop_bounds[3]:
            raise AppError("RANGE_OUTSIDE_DEM", "Air corridor planning range does not intersect DEM bounds.", status_code=400)

        window = from_bounds(*crop_bounds, transform=src.transform).round_offsets().round_lengths()
        crop_transform = src.window_transform(window)
        crop_bounds_exact = array_bounds(int(window.height), int(window.width), crop_transform)
        dst_transform, dst_width, dst_height = calculate_default_transform(
            src.crs,
            target_crs,
            int(window.width),
            int(window.height),
            *crop_bounds_exact,
            resolution=payload.planning.horizontal_resolution_m,
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
    return PreparedAirCorridorDem(
        projected_dem=destination,
        target_epsg=target_epsg,
        start_x=start_x,
        start_y=start_y,
        end_x=end_x,
        end_y=end_y,
        threat_xy=threat_xy,
        bounds=bounds,
        resolution_m=(abs(dst_transform.a), abs(dst_transform.e)),
    )


def _write_air_corridor_outputs(
    task_id: str,
    staging_dir: Path,
    output_dir: Path,
    prepared: PreparedAirCorridorDem,
    payload: AirCorridorPlanningRequest,
):
    import rasterio

    with rasterio.open(prepared.projected_dem) as src:
        dem = src.read(1)
        transform = src.transform
        nodata = src.nodata
        threat_ground_elevations_m = _threat_ground_elevations(
            dem,
            transform,
            nodata,
            prepared,
            payload,
        )

    result = _compute_air_corridor(dem, transform, nodata, prepared, payload)
    transformer = Transformer.from_crs(f"EPSG:{prepared.target_epsg}", "EPSG:4326", always_xy=True)
    tolerance = payload.planning.output_simplify_tolerance_m
    if tolerance is None:
        tolerance = max(prepared.resolution_m)

    path_geom = _path_to_linestring(result["path_points"])
    buffer_geom = path_geom.buffer(payload.planning.corridor_width_m / 2, resolution=12) if path_geom and not path_geom.is_empty else GeometryCollection()
    threat_geom = _threat_zones_geometry(prepared, payload)
    if tolerance > 0:
        if path_geom is not None and not path_geom.is_empty:
            path_geom = path_geom.simplify(tolerance, preserve_topology=True)
        if buffer_geom is not None and not buffer_geom.is_empty:
            buffer_geom = buffer_geom.simplify(tolerance, preserve_topology=True)
        if threat_geom is not None and not threat_geom.is_empty:
            threat_geom = threat_geom.simplify(tolerance, preserve_topology=True)

    corridor_path = staging_dir / "corridor_path.geojson"
    corridor_buffer = staging_dir / "corridor_buffer.geojson"
    threat_zones = staging_dir / "threat_zones.geojson"
    risk_samples = staging_dir / "risk_samples.geojson"
    cost_summary = staging_dir / "cost_summary.json"
    scene_path = staging_dir / "air_corridor_result.glb"
    model_path = staging_dir / "model_metadata.json"
    manifest_path = staging_dir / "output_manifest.json"

    _write_feature_collection(corridor_path, project_geometry(path_geom, transformer), {"kind": "air_corridor_path"})
    _write_feature_collection(corridor_buffer, project_geometry(buffer_geom, transformer), {"kind": "air_corridor_buffer"})
    _write_feature_collection(threat_zones, project_geometry(threat_geom, transformer), {"kind": "air_defense_threat_zones"})
    _write_risk_samples(risk_samples, result["sample_features"], transformer)

    metrics: AirCorridorPlanningMetrics = result["metrics"]
    scene_metadata = write_air_corridor_glb(
        scene_path,
        task_id=task_id,
        target_epsg=prepared.target_epsg,
        path_points=result["path_points"],
        sample_features=result["sample_features"],
        prepared_threat_xy=prepared.threat_xy,
        threat_ground_elevations_m=threat_ground_elevations_m,
        start_ground_elevation_m=result["start_ground"],
        end_ground_elevation_m=result["end_ground"],
        payload=payload,
        route_found=metrics.route_found,
    )
    model = AirCorridorModelMetadata(
        target_epsg=prepared.target_epsg,
        start_projected_xy=[prepared.start_x, prepared.start_y],
        end_projected_xy=[prepared.end_x, prepared.end_y],
        projected_dem_bounds=[prepared.bounds.left, prepared.bounds.bottom, prepared.bounds.right, prepared.bounds.top],
        projected_dem_resolution_m=[prepared.resolution_m[0], prepared.resolution_m[1]],
        start_ground_elevation_m=result["start_ground"],
        end_ground_elevation_m=result["end_ground"],
        altitude_layers_m=payload.altitude_layers_m,
        threat_count=len(payload.threats),
        horizontal_resolution_m=payload.planning.horizontal_resolution_m,
        corridor_width_m=payload.planning.corridor_width_m,
        allow_altitude_change=payload.planning.allow_altitude_change,
        simplify_tolerance_m=tolerance,
        scene3d=scene_metadata,
    )
    warnings = [
        f"Scene3D omitted unit '{omission.unit_id}': {omission.reason}"
        for omission in model.scene3d.omitted_units
    ]
    outputs = AirCorridorPlanningOutputs(
        corridor_path_geojson=f"/outputs/{task_id}/corridor_path.geojson",
        corridor_buffer_geojson=f"/outputs/{task_id}/corridor_buffer.geojson",
        threat_zones_geojson=f"/outputs/{task_id}/threat_zones.geojson",
        risk_samples_geojson=f"/outputs/{task_id}/risk_samples.geojson",
        cost_summary_json=f"/outputs/{task_id}/cost_summary.json",
        scene_glb=f"/outputs/{task_id}/air_corridor_result.glb",
        model_metadata_json=f"/outputs/{task_id}/model_metadata.json",
        output_manifest_json=f"/outputs/{task_id}/output_manifest.json",
    )
    _write_json_atomic(cost_summary, result["cost_summary"])
    _write_json_atomic(
        model_path,
        {
            "model": model.model_dump(),
            "metrics": metrics.model_dump(),
            "warnings": warnings,
        },
    )
    output_paths = {kind: staging_dir / filename for kind, filename in AIR_CORRIDOR_OUTPUT_FILENAMES.items()}
    manifest_files = describe_air_corridor_output_files(task_id, output_paths)
    _write_json_atomic(
        manifest_path,
        {
            "files": [item.model_dump() for item in manifest_files],
            "metrics": metrics.model_dump(),
            "model": model.model_dump(),
            "warnings": warnings,
        },
    )
    if prepared.projected_dem.parent == staging_dir:
        prepared.projected_dem.unlink(missing_ok=True)
    _ensure_staged_outputs_exist(staging_dir)
    _commit_staged_outputs(staging_dir, output_dir)
    output_files = list_air_corridor_task_output_files(task_id)
    return outputs, output_files, metrics, model, warnings


def _compute_air_corridor(dem, transform, nodata, prepared: PreparedAirCorridorDem, payload: AirCorridorPlanningRequest) -> dict:
    finite = numpy.isfinite(dem)
    if nodata is not None:
        finite &= dem != nodata
    start_rc = _xy_to_rc(transform, prepared.start_x, prepared.start_y)
    end_rc = _xy_to_rc(transform, prepared.end_x, prepared.end_y)
    if not _is_inside(dem.shape, start_rc):
        raise AppError("AIR_CORRIDOR_START_OUTSIDE_DEM", "Air corridor start point is outside projected DEM bounds.", status_code=400)
    if not _is_inside(dem.shape, end_rc):
        raise AppError("AIR_CORRIDOR_END_OUTSIDE_DEM", "Air corridor end point is outside projected DEM bounds.", status_code=400)
    start_ground = _value_at(dem, start_rc, nodata, "start")
    end_ground = _value_at(dem, end_rc, nodata, "end")
    start_layer = _nearest_layer(payload.start.altitude_m, payload.altitude_layers_m)
    end_layer = _nearest_layer(payload.end.altitude_m, payload.altitude_layers_m)
    risk_layers = _risk_layers(dem, transform, finite, prepared, payload)
    passable = _passable_layers(dem, finite, payload)
    path_result = _shortest_corridor_path(risk_layers, passable, transform, start_rc, end_rc, start_layer, end_layer, payload)
    if not path_result.found:
        metrics = AirCorridorPlanningMetrics(route_found=False, failure_reason=path_result.failure_reason)
        return {
            "metrics": metrics,
            "path_points": [],
            "sample_features": [],
            "start_ground": start_ground,
            "end_ground": end_ground,
            "cost_summary": _cost_summary(risk_layers, passable, payload),
        }
    path_points, sample_features = _path_points_and_samples(path_result.path, dem, transform, risk_layers, prepared, payload)
    metrics = _path_metrics(path_result.path, path_points, sample_features, path_result.cost or 0, prepared, payload)
    return {
        "metrics": metrics,
        "path_points": path_points,
        "sample_features": sample_features,
        "start_ground": start_ground,
        "end_ground": end_ground,
        "cost_summary": _cost_summary(risk_layers, passable, payload),
    }


def _risk_layers(dem, transform, finite, prepared: PreparedAirCorridorDem, payload: AirCorridorPlanningRequest):
    height, width = dem.shape
    cols = numpy.arange(width, dtype=numpy.float64)
    rows = numpy.arange(height, dtype=numpy.float64)
    xs = transform.c + (cols + 0.5) * transform.a
    ys = transform.f + (rows + 0.5) * transform.e
    x_grid, y_grid = numpy.meshgrid(xs, ys)
    layers = []
    for altitude_agl in payload.altitude_layers_m:
        altitude_amsl = dem + altitude_agl
        risk = numpy.zeros((height, width), dtype=numpy.float64)
        for threat in payload.threats:
            tx, ty = prepared.threat_xy[threat.id]
            distance = numpy.hypot(x_grid - tx, y_grid - ty)
            kill_radius = threat.kill_zone_radius_m if threat.kill_zone_radius_m is not None else min(threat.max_range_m, threat.max_range_m * 0.7)
            warning_radius = threat.warning_zone_radius_m if threat.warning_zone_radius_m is not None else threat.max_range_m
            in_range = (distance >= threat.min_range_m) & (distance <= warning_radius)
            in_altitude = (altitude_amsl >= threat.min_altitude_m) & (altitude_amsl <= threat.max_altitude_m)
            zone_risk = numpy.zeros_like(risk)
            zone_risk[distance <= kill_radius] = 1.0
            decay_mask = (distance > kill_radius) & (distance <= warning_radius)
            if warning_radius > kill_radius:
                zone_risk[decay_mask] = 1 - (distance[decay_mask] - kill_radius) / (warning_radius - kill_radius)
            risk += numpy.where(in_range & in_altitude, zone_risk * threat.threat_level, 0)
        layers.append(numpy.where(finite, risk, numpy.inf))
    return numpy.stack(layers, axis=0)


def _passable_layers(dem, finite, payload: AirCorridorPlanningRequest):
    layers = []
    for altitude_agl in payload.altitude_layers_m:
        passable = finite & (altitude_agl >= payload.aircraft.min_agl_m) & (altitude_agl <= payload.aircraft.max_agl_m)
        layers.append(passable)
    return numpy.stack(layers, axis=0)


def _shortest_corridor_path(risk_layers, passable, transform, start_rc, end_rc, start_layer, end_layer, payload: AirCorridorPlanningRequest):
    if not passable[start_layer, start_rc[0], start_rc[1]]:
        return CorridorPathResult(False, [], None, "Start altitude layer is not flyable.")
    if not passable[end_layer, end_rc[0], end_rc[1]]:
        return CorridorPathResult(False, [], None, "End altitude layer is not flyable.")
    distances = numpy.full(risk_layers.shape, numpy.inf, dtype=numpy.float64)
    start = (start_layer, start_rc[0], start_rc[1])
    end = (end_layer, end_rc[0], end_rc[1])
    distances[start] = 0
    previous: dict[tuple[int, int, int], tuple[int, int, int]] = {}
    heap = [(0.0, start)]
    while heap:
        cost, current = heapq.heappop(heap)
        if cost > distances[current]:
            continue
        if current == end:
            return CorridorPathResult(True, _reconstruct_path(previous, start, end), float(cost))
        for nxt, step_distance, altitude_delta in _neighbors(current, risk_layers.shape, transform, payload):
            if not passable[nxt]:
                continue
            next_cost = cost + _step_cost(risk_layers, current, nxt, step_distance, altitude_delta, payload)
            if next_cost < distances[nxt]:
                distances[nxt] = next_cost
                previous[nxt] = current
                heapq.heappush(heap, (next_cost, nxt))
    return CorridorPathResult(False, [], None, "No flyable low-risk corridor connects start and end.")


def _neighbors(current, shape, transform, payload: AirCorridorPlanningRequest):
    layer, row, col = current
    layer_count, height, width = shape
    cell = max(abs(float(transform.a)), abs(float(transform.e)))
    horizontal = [(-1, 0, cell), (1, 0, cell), (0, -1, cell), (0, 1, cell)]
    root2 = math.sqrt(2) * cell
    horizontal.extend([(-1, -1, root2), (-1, 1, root2), (1, -1, root2), (1, 1, root2)])
    for dr, dc, distance in horizontal:
        next_rc = (row + dr, col + dc)
        if 0 <= next_rc[0] < height and 0 <= next_rc[1] < width:
            yield (layer, next_rc[0], next_rc[1]), distance, 0.0
    if payload.planning.allow_altitude_change:
        for next_layer in (layer - 1, layer + 1):
            if 0 <= next_layer < layer_count:
                altitude_delta = abs(payload.altitude_layers_m[next_layer] - payload.altitude_layers_m[layer])
                yield (next_layer, row, col), max(cell, altitude_delta), altitude_delta


def _step_cost(risk_layers, current, nxt, step_distance: float, altitude_delta: float, payload: AirCorridorPlanningRequest) -> float:
    avg_risk = (float(risk_layers[current]) + float(risk_layers[nxt])) / 2
    speed_mps = payload.aircraft.cruise_speed_kph * 1000 / 3600
    time_cost = step_distance / max(speed_mps, 0.001)
    return (
        time_cost
        + payload.planning.distance_weight * (step_distance / 1000)
        + payload.planning.threat_weight * avg_risk
        + payload.planning.altitude_change_weight * (altitude_delta / 100)
    )


def _path_points_and_samples(path, dem, transform, risk_layers, prepared: PreparedAirCorridorDem, payload: AirCorridorPlanningRequest):
    points = []
    samples = []
    for index, (layer, row, col) in enumerate(path):
        x = transform.c + (float(col) + 0.5) * transform.a
        y = transform.f + (float(row) + 0.5) * transform.e
        ground = float(dem[row, col])
        altitude_agl = payload.altitude_layers_m[layer]
        altitude_amsl = ground + altitude_agl
        risk = float(risk_layers[layer, row, col])
        nearest = _nearest_threat_distance(x, y, prepared)
        points.append((x, y, altitude_amsl))
        samples.append(
            {
                "geometry": Point(x, y),
                "properties": {
                    "index": index,
                    "layer": layer,
                    "altitude_agl_m": altitude_agl,
                    "altitude_amsl_m": altitude_amsl,
                    "terrain_clearance_m": altitude_agl,
                    "risk": risk,
                    "nearest_threat_distance_m": nearest,
                },
            }
        )
    return points, samples


def _path_metrics(path, path_points, sample_features, total_cost: float, prepared: PreparedAirCorridorDem, payload: AirCorridorPlanningRequest):
    length = 0.0
    horizontal_length = 0.0
    altitude_changes = 0
    for index, (current, nxt) in enumerate(zip(path, path[1:])):
        if current[0] != nxt[0]:
            altitude_changes += 1
        p0 = path_points[index]
        p1 = path_points[index + 1]
        length += math.sqrt((p1[0] - p0[0]) ** 2 + (p1[1] - p0[1]) ** 2 + (p1[2] - p0[2]) ** 2)
        horizontal_length += math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    risks = [float(item["properties"]["risk"]) for item in sample_features]
    clearances = [float(item["properties"]["terrain_clearance_m"]) for item in sample_features]
    nearest_distances = [item["properties"]["nearest_threat_distance_m"] for item in sample_features if item["properties"]["nearest_threat_distance_m"] is not None]
    altitudes = [float(item["properties"]["altitude_agl_m"]) for item in sample_features]
    threat_intersections = sum(1 for value in risks if value > 0)
    estimated_time = length / max(payload.aircraft.cruise_speed_kph * 1000 / 3600, 0.001) if length > 0 else 0
    direct_distance = math.hypot(
        prepared.end_x - prepared.start_x,
        prepared.end_y - prepared.start_y,
    )
    return AirCorridorPlanningMetrics(
        route_found=True,
        risk_score=sum(risks) / len(risks) if risks else 0,
        max_segment_risk=max(risks) if risks else 0,
        mean_segment_risk=sum(risks) / len(risks) if risks else 0,
        corridor_length_m=length,
        estimated_time_seconds=estimated_time,
        min_terrain_clearance_m=min(clearances) if clearances else None,
        mean_terrain_clearance_m=sum(clearances) / len(clearances) if clearances else None,
        altitude_change_count=altitude_changes,
        min_altitude_m=min(altitudes) if altitudes else None,
        max_altitude_m=max(altitudes) if altitudes else None,
        threat_intersection_count=threat_intersections,
        nearest_threat_distance_m=min(nearest_distances) if nearest_distances else None,
        direct_distance_m=direct_distance,
        horizontal_detour_ratio=(
            horizontal_length / direct_distance if direct_distance > 0 else 0
        ),
        risk_sample_count=len(sample_features),
    )


def _cost_summary(risk_layers, passable, payload: AirCorridorPlanningRequest):
    layers = []
    for index, altitude in enumerate(payload.altitude_layers_m):
        values = risk_layers[index][numpy.isfinite(risk_layers[index]) & passable[index]]
        layers.append(
            {
                "layer": index,
                "altitude_agl_m": altitude,
                "passable_cell_count": int(passable[index].sum()),
                "mean_risk": float(values.mean()) if values.size else None,
                "max_risk": float(values.max()) if values.size else None,
            }
        )
    return {"layers": layers, "threat_count": len(payload.threats)}


def _nearest_layer(altitude_m: float, layers: list[float]) -> int:
    return min(range(len(layers)), key=lambda index: abs(layers[index] - altitude_m))


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
        raise AppError("AIR_CORRIDOR_NO_DATA", f"The {label} point falls on DEM nodata.", status_code=400)
    return value


def _threat_ground_elevations(
    dem,
    transform,
    nodata,
    prepared: PreparedAirCorridorDem,
    payload: AirCorridorPlanningRequest,
) -> dict[str, float | None]:
    values: dict[str, float | None] = {}
    for threat in payload.threats:
        rc = _xy_to_rc(transform, *prepared.threat_xy[threat.id])
        if not _is_inside(dem.shape, rc):
            values[threat.id] = None
            continue
        value = float(dem[rc])
        values[threat.id] = (
            None
            if not numpy.isfinite(value)
            or (nodata is not None and value == nodata)
            else value
        )
    return values


def _reconstruct_path(previous: dict[tuple[int, int, int], tuple[int, int, int]], start, end):
    path = [end]
    current = end
    while current != start:
        current = previous[current]
        path.append(current)
    path.reverse()
    return path


def _path_to_linestring(path_points):
    if len(path_points) < 2:
        return GeometryCollection()
    return LineString(path_points)


def _threat_zones_geometry(prepared: PreparedAirCorridorDem, payload: AirCorridorPlanningRequest):
    geometries = []
    for threat in payload.threats:
        tx, ty = prepared.threat_xy[threat.id]
        warning_radius = threat.warning_zone_radius_m if threat.warning_zone_radius_m is not None else threat.max_range_m
        geometries.append(Point(tx, ty).buffer(warning_radius, resolution=48))
    if not geometries:
        return GeometryCollection()
    return unary_union(geometries)


def _nearest_threat_distance(x: float, y: float, prepared: PreparedAirCorridorDem) -> float | None:
    if not prepared.threat_xy:
        return None
    return min(math.hypot(x - tx, y - ty) for tx, ty in prepared.threat_xy.values())


def _write_feature_collection(path: Path, geometry, properties: dict | None = None) -> None:
    features = []
    if geometry is not None and not geometry.is_empty:
        features.append({"type": "Feature", "properties": properties or {}, "geometry": mapping(geometry)})
    _write_json_atomic(path, {"type": "FeatureCollection", "features": features})


def _write_risk_samples(path: Path, sample_features: list[dict], transformer: Transformer) -> None:
    features = []
    for item in sample_features:
        geometry = project_geometry(item["geometry"], transformer)
        features.append({"type": "Feature", "properties": item["properties"], "geometry": mapping(geometry)})
    _write_json_atomic(path, {"type": "FeatureCollection", "features": features})


def _ensure_staged_outputs_exist(staging_dir: Path) -> None:
    missing = [
        kind
        for kind, filename in AIR_CORRIDOR_OUTPUT_FILENAMES.items()
        if not (staging_dir / filename).exists() or (staging_dir / filename).stat().st_size <= 0
    ]
    if missing:
        raise AppError("OUTPUT_INCOMPLETE", f"Air corridor task staged outputs are incomplete: {', '.join(missing)}.", status_code=500)


def _commit_staged_outputs(staging_dir: Path, output_dir: Path) -> None:
    if staging_dir.parent != output_dir.parent:
        raise AppError(
            "OUTPUT_STAGING_INVALID",
            "Air corridor staging directory must be a sibling of its output directory.",
            status_code=500,
        )
    if output_dir.exists():
        raise AppError(
            "OUTPUT_DIRECTORY_EXISTS",
            f"Air corridor output directory already exists: {output_dir.name}.",
            status_code=500,
        )
    staging_dir.replace(output_dir)
    _fsync_directory(output_dir.parent)


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
