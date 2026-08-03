import json
import math
import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

import numpy
from pyproj import Transformer
from rasterio.transform import from_origin
from shapely.geometry import Point, mapping

from app.schemas.radar import CoverageMetrics, MultiRadarOutputs, MultiRadarRequest
from app.services.artifact_contracts import get_output_contract
from app.services.artifact_store import get_artifact_store
from app.services.coverage_range import effective_max_range
from app.services.dem_store import find_dem_file
from app.services.multi_radar_coverage import StationMask, accumulate_station_masks
from app.services.multi_radar_dem import SharedMultiRadarDem, prepare_shared_multi_radar_dem, station_coverage_request
from app.services.multi_radar_fusion_volume import (
    FusionHeightEnvelope,
    FusionHeightCounts,
    accumulate_fusion_height_counts,
    intersect_fusion_envelopes,
    write_cooperative_intersection_glb,
    write_multi_radar_fusion_glb,
)
from app.services.multi_radar_task_store import mark_multi_completed, mark_multi_failed, mark_multi_running
from app.services.task_store import create_task, get_task
from app.services.task_scheduler import TaskCancelled
from app.workers.coverage_task import _build_coverage_metrics, _coverage_masks, _mask_area, _mask_to_geometry, _run_gdal_viewshed, run_coverage_task


FUSION_HEIGHTS_M = numpy.asarray([0, 100, 300, 600, 1200, 2200, 3000], dtype=numpy.float32)
FUSION_MAX_GRID_DIMENSION = 192


@dataclass(frozen=True)
class StationEvaluation:
    radar_id: str
    name: str | None
    visible_mask: numpy.ndarray
    range_mask: numpy.ndarray
    metrics: dict
    diagnostics: dict | None = None
    fusion_masks: numpy.ndarray | None = None
    fusion_envelope: FusionHeightEnvelope | None = None
    scene_task_id: str | None = None
    scene_status: str | None = None
    scene_message: str = ""


StationEvaluator = Callable[[SharedMultiRadarDem, object], StationEvaluation]


@dataclass(frozen=True)
class MultiRadarArtifactResult:
    status: str
    metrics: dict
    outputs: MultiRadarOutputs
    stations: list[dict]
    message: str


def run_multi_radar_coverage_task(
    task_id: str,
    payload: MultiRadarRequest,
    *,
    evaluator: StationEvaluator | None = None,
) -> None:
    try:
        result = build_multi_radar_artifacts(
            task_id,
            payload,
            lambda message, value: mark_multi_running(task_id, message, value),
            evaluator=evaluator,
        )
        mark_multi_completed(
            task_id,
            status=result.status,
            metrics=result.metrics,
            outputs=result.outputs,
            stations=result.stations,
            message=result.message,
        )
    except TaskCancelled:
        mark_multi_failed(task_id, "Task cancelled by user.")
    except Exception as exc:
        mark_multi_failed(task_id, str(exc))


def build_multi_radar_artifacts(
    task_id: str,
    payload: MultiRadarRequest,
    progress: Callable[[str, int], None],
    *,
    evaluator: StationEvaluator | None = None,
) -> MultiRadarArtifactResult:
    store = get_artifact_store()
    contract = get_output_contract("multi_radar")
    staging_dir = store.create_staging_dir(task_id)
    try:
        progress("Preparing shared DEM and projection.", 5)
        shared = prepare_shared_multi_radar_dem(
            find_dem_file(payload.dem_id), staging_dir / "dem_projected.tif", payload
        )
        evaluate = evaluator or _evaluate_station
        completed: list[StationEvaluation] = []
        failures: dict[str, str] = {}
        workers = min(len(payload.radars), os.cpu_count() or 1, 8)
        progress(f"Computing {len(payload.radars)} stations on one grid.", 15)
        with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            futures = {executor.submit(evaluate, shared, station): station for station in payload.radars}
            for index, future in enumerate(as_completed(futures), start=1):
                station = futures[future]
                try:
                    completed.append(future.result())
                except Exception as exc:
                    failures[station.radar_id] = str(exc)
                progress(
                    f"Computed {index} of {len(payload.radars)} stations.",
                    15 + int(70 * index / len(payload.radars)),
                )
        stations = _station_summaries(payload, completed, failures)
        if not completed:
            return MultiRadarArtifactResult(
                status="failed",
                metrics={},
                outputs=MultiRadarOutputs(),
                stations=stations,
                message="All radar stations failed.",
            )

        aggregate = accumulate_station_masks(
            StationMask(item.radar_id, item.visible_mask, item.range_mask) for item in completed
        )
        if payload.presentation_mode == "cooperative_3d":
            completed = _generate_cooperative_scene_tasks(task_id, payload, completed, progress)
        progress("Writing aggregate coverage outputs.", 90)
        fusion_masks = [item.fusion_masks for item in completed if item.fusion_masks is not None]
        fusion_envelopes = [item.fusion_envelope for item in completed if item.fusion_envelope is not None]
        fusion_path = None
        cooperative_intersection_path = None
        if payload.presentation_mode == "cooperative_3d":
            # A strict cooperative volume is meaningful only when every requested
            # station contributed an analytic envelope. Never fall back to the
            # legacy height-count mesh for this presentation mode.
            all_station_envelopes = (
                not failures
                and len(completed) == len(payload.radars)
                and len(fusion_envelopes) == len(payload.radars)
            )
            if all_station_envelopes:
                intersection = intersect_fusion_envelopes(fusion_envelopes)
                if intersection is not None:
                    candidate = staging_dir / "cooperative_intersection.glb"
                    if write_cooperative_intersection_glb(
                        candidate,
                        task_id=task_id,
                        envelope=intersection,
                        station_count=len(fusion_envelopes),
                    ) is not None:
                        cooperative_intersection_path = candidate
        elif fusion_masks:
            rows, columns, fusion_transform = fusion_grid_spec(shared)
            terrain = _read_fusion_terrain(shared.projected_dem, rows, columns)
            fusion_counts = FusionHeightCounts(
                target_epsg=shared.target_epsg,
                transform=fusion_transform,
                heights_m=FUSION_HEIGHTS_M,
                coverage_count=accumulate_fusion_height_counts(fusion_masks),
                terrain_m=terrain,
            )
            fusion_path = staging_dir / "fusion_scene.glb"
            write_multi_radar_fusion_glb(fusion_path, task_id=task_id, counts=fusion_counts)

        _write_aggregate_outputs(
            staging_dir,
            shared,
            aggregate,
            payload,
            completed,
            fusion_path,
            cooperative_intersection_path,
        )
        if shared.projected_dem.parent == staging_dir:
            shared.projected_dem.unlink(missing_ok=True)
        store.publish(task_id, contract, staging_dir)
        descriptors = store.list_descriptors(task_id, contract)
        paths = {item.kind: item.download_path for item in descriptors}
        outputs = MultiRadarOutputs(
            **{field: paths.get(field) for field in MultiRadarOutputs.model_fields}
        )
        cell_area = abs(float(shared.transform.a) * float(shared.transform.e))
        metrics = {
            "visible_union_area_m2": float(aggregate.visible_union.sum()) * cell_area,
            "overlap_area_m2": float(aggregate.overlap.sum()) * cell_area,
            "blind_area_m2": float(aggregate.blind.sum()) * cell_area,
            "theoretical_union_area_m2": float((aggregate.visible_union | aggregate.blind).sum()) * cell_area,
            "successful_station_count": len(completed),
            "failed_station_count": len(failures),
        }
        status = "partial" if failures else "finished"
        return MultiRadarArtifactResult(
            status=status,
            metrics=metrics,
            outputs=outputs,
            stations=_station_summaries(payload, completed, failures),
            message="Finished with station failures." if failures else "finished",
        )
    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)


def _evaluate_station(shared: SharedMultiRadarDem, station) -> StationEvaluation:
    import rasterio

    request = station_coverage_request("", station)
    radar_x, radar_y = shared.station_points[station.radar_id]
    with rasterio.open(shared.projected_dem) as source:
        row, column = source.index(radar_x, radar_y)
        if not (0 <= row < source.height and 0 <= column < source.width) or source.read_masks(1)[row, column] == 0:
            raise ValueError("Radar point is outside the valid shared DEM.")
    output = shared.projected_dem.with_name(f"viewshed_{station.radar_id}.tif")
    _run_gdal_viewshed(shared.projected_dem, output, radar_x, radar_y, request, mode="GROUND")
    try:
        with rasterio.open(output) as source:
            data = source.read(1)
            local_transform = source.transform
            local_domain = shared_analysis_domain_window(shared, local_transform, data.shape)
            masks = _coverage_masks(
                data, local_transform, radar_x, radar_y, request, station.target.height_m,
                effective_max_range(request)[0], local_domain,
            )
        visible_mask, range_mask = station_masks_to_shared_grid(
            shared, local_transform, masks["visible"], masks["theoretical"]
        )
        fusion_masks = _station_fusion_masks(
            shared, data, local_transform, local_domain, radar_x, radar_y, request
        )
        fusion_envelope = _station_fusion_envelope(
            shared, data, local_transform, local_domain, radar_x, radar_y, request
        )
        metrics = _build_coverage_metrics(masks, local_transform, radar_equation_limited_area=0)
        return StationEvaluation(
            radar_id=station.radar_id, name=station.name, visible_mask=visible_mask,
            range_mask=range_mask, metrics=metrics.model_dump(), fusion_masks=fusion_masks,
            fusion_envelope=fusion_envelope,
        )
    finally:
        output.unlink(missing_ok=True)


def station_masks_to_shared_grid(shared, local_transform, visible_mask, theoretical_mask):
    row, column = shared_grid_offset(shared, local_transform)
    height, width = visible_mask.shape
    if theoretical_mask.shape != (height, width):
        raise ValueError("Station visibility and theoretical masks must share one shape.")
    if row < 0 or column < 0 or row + height > shared.analysis_domain.shape[0] or column + width > shared.analysis_domain.shape[1]:
        raise ValueError("Station viewshed window is outside the shared DEM grid.")
    visible = numpy.zeros_like(shared.analysis_domain, dtype=bool)
    theoretical = numpy.zeros_like(shared.analysis_domain, dtype=bool)
    visible[row:row + height, column:column + width] = visible_mask
    theoretical[row:row + height, column:column + width] = theoretical_mask
    return visible, theoretical


def shared_analysis_domain_window(shared, local_transform, shape):
    row, column = shared_grid_offset(shared, local_transform)
    height, width = shape
    if row < 0 or column < 0 or row + height > shared.analysis_domain.shape[0] or column + width > shared.analysis_domain.shape[1]:
        raise ValueError("Station viewshed window is outside the shared DEM grid.")
    return shared.analysis_domain[row:row + height, column:column + width]


def shared_grid_offset(shared, local_transform) -> tuple[int, int]:
    shared_transform = shared.transform
    if not numpy.isclose(local_transform.a, shared_transform.a) or not numpy.isclose(local_transform.e, shared_transform.e):
        raise ValueError("Station viewshed resolution does not match the shared DEM grid.")
    column_float = (local_transform.c - shared_transform.c) / shared_transform.a
    row_float = (local_transform.f - shared_transform.f) / shared_transform.e
    row, column = round(row_float), round(column_float)
    if not numpy.isclose(row_float, row) or not numpy.isclose(column_float, column):
        raise ValueError("Station viewshed window is not aligned to the shared DEM grid.")
    return int(row), int(column)


def fusion_grid_spec(shared):
    height, width = shared.analysis_domain.shape
    scale = max(1, int(numpy.ceil(max(height, width) / FUSION_MAX_GRID_DIMENSION)))
    rows = numpy.arange(0, height, scale, dtype=numpy.int32)
    columns = numpy.arange(0, width, scale, dtype=numpy.int32)
    source_x_size = abs(float(shared.transform.a))
    source_y_size = abs(float(shared.transform.e))
    # The downsampled arrays contain source pixels at indices 0, scale, 2*scale,
    # ...; align their output-cell centers with those source-pixel centers.
    transform = from_origin(
        float(shared.transform.c) - 0.5 * (scale - 1) * source_x_size,
        float(shared.transform.f) + 0.5 * (scale - 1) * source_y_size,
        source_x_size * scale,
        source_y_size * scale,
    )
    return rows, columns, transform


def _read_fusion_terrain(
    projected_dem: Path,
    rows: numpy.ndarray,
    columns: numpy.ndarray,
) -> numpy.ma.MaskedArray:
    import rasterio

    with rasterio.open(projected_dem) as source:
        terrain = source.read(1, masked=True)
    return terrain[rows][:, columns]


def _station_fusion_masks(shared, data, local_transform, local_domain, radar_x, radar_y, request):
    rows, columns, _transform = fusion_grid_spec(shared)
    sampled_masks = []
    for height_m in FUSION_HEIGHTS_M:
        masks = _coverage_masks(
            data, local_transform, radar_x, radar_y, request, float(height_m),
            effective_max_range(request)[0], local_domain,
        )
        visible, _theoretical = station_masks_to_shared_grid(
            shared, local_transform, masks["visible"], masks["theoretical"]
        )
        sampled_masks.append(visible[numpy.ix_(rows, columns)])
    return numpy.asarray(sampled_masks, dtype=bool)


def _station_fusion_envelope(
    shared,
    data,
    local_transform,
    local_domain,
    radar_x,
    radar_y,
    request,
) -> FusionHeightEnvelope:
    rows, columns, transform = fusion_grid_spec(shared)
    row, column = shared_grid_offset(shared, local_transform)
    threshold_shared = numpy.full(shared.analysis_domain.shape, numpy.nan, dtype=numpy.float64)
    height, width = data.shape
    threshold_shared[row:row + height, column:column + width] = numpy.asarray(data, dtype=numpy.float64)
    threshold = threshold_shared[numpy.ix_(rows, columns)]
    local_domain = numpy.asarray(local_domain, dtype=bool)
    if local_domain.shape != data.shape:
        raise ValueError("Station viewshed domain does not match the viewshed raster.")
    domain_shared = numpy.zeros_like(shared.analysis_domain, dtype=bool)
    domain_shared[row:row + height, column:column + width] = local_domain
    domain = domain_shared[numpy.ix_(rows, columns)] & numpy.asarray(
        shared.analysis_domain[numpy.ix_(rows, columns)], dtype=bool
    )
    terrain_masked = _read_fusion_terrain(shared.projected_dem, rows, columns)
    terrain = numpy.asarray(terrain_masked.data, dtype=numpy.float64)
    terrain_valid = ~numpy.ma.getmaskarray(terrain_masked) & numpy.isfinite(terrain)
    threshold_valid = numpy.isfinite(threshold) & (threshold >= 0)

    radar_ground = _sample_shared_terrain(shared, radar_x, radar_y)
    radar_z = radar_ground + float(request.radar.height_m)
    effective_range = effective_max_range(request)[0]
    x = transform.c + (numpy.arange(len(columns), dtype=numpy.float64) + 0.5) * transform.a
    y = transform.f + (numpy.arange(len(rows), dtype=numpy.float64) + 0.5) * transform.e
    x_grid, y_grid = numpy.meshgrid(x, y)
    dx = x_grid - radar_x
    dy = y_grid - radar_y
    distance = numpy.hypot(dx, dy)
    distance_squared = distance * distance
    sector = _fusion_sector_mask(dx, dy, request)

    lower = terrain + threshold
    lower = numpy.maximum(
        lower,
        radar_z + distance * math.tan(math.radians(request.advanced.min_elevation_deg)),
    )
    upper = radar_z + numpy.sqrt(numpy.maximum(0.0, effective_range**2 - distance_squared))
    if request.advanced.max_elevation_deg < 90:
        upper = numpy.minimum(
            upper,
            radar_z + distance * math.tan(math.radians(request.advanced.max_elevation_deg)),
        )
    valid = (
        domain
        & terrain_valid
        & threshold_valid
        & (distance_squared <= effective_range**2)
        & sector
        & numpy.isfinite(lower)
        & numpy.isfinite(upper)
        & (lower <= upper)
    )
    return FusionHeightEnvelope(
        target_epsg=shared.target_epsg,
        transform=transform,
        lower_m=numpy.where(valid, lower, 0.0),
        upper_m=numpy.where(valid, upper, 0.0),
        valid=valid,
    )


def _sample_shared_terrain(shared, x: float, y: float) -> float:
    import rasterio

    with rasterio.open(shared.projected_dem) as source:
        row, column = source.index(x, y)
        sample = source.read(1, window=((row, row + 1), (column, column + 1)), masked=True)
    value = sample[0, 0]
    if numpy.ma.is_masked(value) or not numpy.isfinite(float(value)):
        raise ValueError("Radar point is outside the valid shared DEM.")
    return float(value)


def _fusion_sector_mask(dx, dy, request):
    if request.coverage.scan_mode != "sector" or request.coverage.beam_width_deg >= 360:
        return numpy.ones(dx.shape, dtype=bool)
    azimuth = (numpy.degrees(numpy.arctan2(dx, dy)) + 360) % 360
    delta = numpy.abs((azimuth - request.coverage.azimuth_deg + 180) % 360 - 180)
    return delta <= request.coverage.beam_width_deg / 2


def _generate_cooperative_scene_tasks(
    task_id: str,
    payload: MultiRadarRequest,
    completed: list[StationEvaluation],
    progress: Callable[[str, int], None],
):
    stations = {station.radar_id: station for station in payload.radars}

    def generate(item: StationEvaluation) -> StationEvaluation:
        task = create_task(station_coverage_request(payload.dem_id, stations[item.radar_id]))
        if task.request is None:
            raise ValueError("Cooperative station scene task is missing its request.")
        run_coverage_task(task.task_id, task.request)
        finished = get_task(task.task_id)
        return replace(
            item,
            scene_task_id=finished.task_id,
            scene_status=finished.status,
            scene_message=finished.message,
        )

    results: dict[str, StationEvaluation] = {}
    workers = min(len(completed), 3)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {executor.submit(generate, item): item for item in completed}
        for index, future in enumerate(as_completed(futures), start=1):
            original = futures[future]
            try:
                results[original.radar_id] = future.result()
            except Exception as exc:
                results[original.radar_id] = replace(original, scene_message=str(exc))
            progress(
                f"Generating full scenes {index} of {len(completed)}.",
                85 + int(4 * index / len(completed)),
            )
    return [results[item.radar_id] for item in completed]


def _station_summaries(payload, completed: list[StationEvaluation], failures: dict[str, str]) -> list[dict]:
    complete = {item.radar_id: item for item in completed}
    summaries = []
    for station in payload.radars:
        result = complete.get(station.radar_id)
        summaries.append({
            "radar_id": station.radar_id, "name": station.name,
            "status": "finished" if result else "failed" if station.radar_id in failures else "pending",
            "message": failures.get(station.radar_id, ""),
            "metrics": result.metrics if result else None,
            "diagnostics": result.diagnostics if result else None,
            "scene_task_id": result.scene_task_id if result else None,
            "scene_status": result.scene_status if result else None,
            "scene_message": result.scene_message if result else "",
        })
    return summaries


def _write_aggregate_outputs(
    staging_dir: Path,
    shared,
    aggregate,
    payload,
    completed,
    fusion_path: Path | None = None,
    cooperative_intersection_path: Path | None = None,
) -> None:
    transformer = Transformer.from_crs(f"EPSG:{shared.target_epsg}", "EPSG:4326", always_xy=True)
    _write_mask_geojson(staging_dir / "visible_union.geojson", aggregate.visible_union, shared.transform, transformer, {"kind": "visible_union"})
    _write_mask_geojson(staging_dir / "overlap.geojson", aggregate.overlap, shared.transform, transformer, {"kind": "overlap"})
    _write_mask_geojson(staging_dir / "blind.geojson", aggregate.blind, shared.transform, transformer, {"kind": "blind"})
    _write_count_geojson(staging_dir / "coverage_count.geojson", aggregate.coverage_count, shared.transform, transformer)
    _write_stations_geojson(staging_dir / "stations.geojson", payload, completed)
    (staging_dir / "station_summaries.json").write_text(json.dumps(_station_summaries(payload, completed, {}), ensure_ascii=False), encoding="utf-8")
    numpy.savez_compressed(
        staging_dir / "station_masks.npz",
        **{item.radar_id: item.visible_mask for item in completed},
    )
    (staging_dir / "grid.json").write_text(json.dumps({
        "target_epsg": shared.target_epsg,
        "transform": list(shared.transform)[:6],
        "shape": list(aggregate.coverage_count.shape),
    }), encoding="utf-8")


def _write_mask_geojson(path, mask, transform, transformer, properties):
    geometry = _mask_to_geometry(mask, transform)
    features = []
    if not geometry.is_empty:
        from app.services.geometry import project_geometry
        features.append({"type": "Feature", "properties": properties, "geometry": mapping(project_geometry(geometry, transformer))})
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")


def _write_count_geojson(path, count, transform, transformer):
    from rasterio.features import shapes
    from shapely.geometry import shape
    from app.services.geometry import project_geometry
    features = []
    for geometry, value in shapes(count.astype(numpy.uint16), mask=count > 0, transform=transform):
        features.append({"type": "Feature", "properties": {"coverage_count": int(value)}, "geometry": mapping(project_geometry(shape(geometry), transformer))})
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")


def _write_stations_geojson(path, payload, completed):
    result_ids = {item.radar_id for item in completed}
    features = [{
        "type": "Feature", "properties": {"radar_id": station.radar_id, "name": station.name, "status": "finished" if station.radar_id in result_ids else "failed"},
        "geometry": mapping(Point(station.radar.lon, station.radar.lat)),
    } for station in payload.radars]
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
