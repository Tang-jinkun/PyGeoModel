import json
import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable
from uuid import uuid4

import numpy
from pyproj import Transformer
from rasterio.transform import from_origin
from shapely.geometry import Point, mapping

from app.core.config import settings
from app.schemas.radar import CoverageMetrics, MultiRadarRequest
from app.services.coverage_range import effective_max_range
from app.services.dem_store import find_dem_file
from app.services.multi_radar_coverage import StationMask, accumulate_station_masks
from app.services.multi_radar_dem import SharedMultiRadarDem, prepare_shared_multi_radar_dem, station_coverage_request
from app.services.multi_radar_fusion_volume import (
    FusionHeightCounts,
    accumulate_fusion_height_counts,
    write_cooperative_intersection_glb,
    write_multi_radar_fusion_glb,
)
from app.services.multi_radar_task_store import mark_multi_completed, mark_multi_failed, mark_multi_running
from app.services.task_store import create_task, get_task
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
    scene_task_id: str | None = None
    scene_status: str | None = None
    scene_message: str = ""


StationEvaluator = Callable[[SharedMultiRadarDem, object], StationEvaluation]


def run_multi_radar_coverage_task(
    task_id: str,
    payload: MultiRadarRequest,
    *,
    evaluator: StationEvaluator | None = None,
) -> None:
    output_dir = settings.outputs_dir / task_id
    staging_dir = output_dir / f".staging-{uuid4().hex}"
    try:
        mark_multi_running(task_id, "Preparing shared DEM and projection.", 5)
        output_dir.mkdir(parents=True, exist_ok=True)
        staging_dir.mkdir(parents=True, exist_ok=False)
        shared = prepare_shared_multi_radar_dem(find_dem_file(payload.dem_id), staging_dir / "dem_projected.tif", payload)
        evaluate = evaluator or _evaluate_station
        completed: list[StationEvaluation] = []
        failures: dict[str, str] = {}
        workers = min(len(payload.radars), os.cpu_count() or 1, 8)
        mark_multi_running(task_id, f"Computing {len(payload.radars)} stations on one grid.", 15)
        with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            futures = {executor.submit(evaluate, shared, station): station for station in payload.radars}
            for index, future in enumerate(as_completed(futures), start=1):
                station = futures[future]
                try:
                    completed.append(future.result())
                except Exception as exc:
                    failures[station.radar_id] = str(exc)
                progress = 15 + int(70 * index / len(payload.radars))
                mark_multi_running(task_id, f"Computed {index} of {len(payload.radars)} stations.", progress)
        if not completed:
            mark_multi_completed(
                task_id, status="failed", metrics={}, outputs={},
                stations=_station_summaries(payload, completed, failures), message="All radar stations failed."
            )
            return
        aggregate = accumulate_station_masks(
            StationMask(item.radar_id, item.visible_mask, item.range_mask) for item in completed
        )
        if payload.presentation_mode == "cooperative_3d":
            completed = _generate_cooperative_scene_tasks(task_id, payload, completed)
        mark_multi_running(task_id, "Writing aggregate coverage outputs.", 90)
        fusion_masks = [item.fusion_masks for item in completed if item.fusion_masks is not None]
        fusion_path = None
        cooperative_intersection_path = None
        if fusion_masks:
            rows, columns, fusion_transform = fusion_grid_spec(shared)
            import rasterio
            with rasterio.open(shared.projected_dem) as source:
                terrain = source.read(1)[numpy.ix_(rows, columns)]
            fusion_counts = FusionHeightCounts(
                target_epsg=shared.target_epsg,
                transform=fusion_transform,
                heights_m=FUSION_HEIGHTS_M,
                coverage_count=accumulate_fusion_height_counts(fusion_masks),
                terrain_m=terrain,
            )
            if payload.presentation_mode == "cooperative_3d":
                candidate = staging_dir / "cooperative_intersection.glb"
                if write_cooperative_intersection_glb(candidate, task_id=task_id, counts=fusion_counts) is not None:
                    cooperative_intersection_path = candidate
            else:
                fusion_path = staging_dir / "fusion_scene.glb"
                write_multi_radar_fusion_glb(fusion_path, task_id=task_id, counts=fusion_counts)
        outputs = _write_aggregate_outputs(
            task_id,
            output_dir,
            staging_dir,
            shared,
            aggregate,
            payload,
            completed,
            fusion_path,
            cooperative_intersection_path,
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
        mark_multi_completed(
            task_id, status=status, metrics=metrics, outputs=outputs,
            stations=_station_summaries(payload, completed, failures),
            message="Finished with station failures." if failures else "finished",
        )
    except Exception as exc:
        mark_multi_failed(task_id, str(exc))
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
        metrics = _build_coverage_metrics(masks, local_transform, radar_equation_limited_area=0)
        return StationEvaluation(
            radar_id=station.radar_id, name=station.name, visible_mask=visible_mask,
            range_mask=range_mask, metrics=metrics.model_dump(), fusion_masks=fusion_masks,
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
    transform = from_origin(
        shared.transform.c,
        shared.transform.f,
        abs(shared.transform.a) * scale,
        abs(shared.transform.e) * scale,
    )
    return rows, columns, transform


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


def _generate_cooperative_scene_tasks(task_id: str, payload: MultiRadarRequest, completed: list[StationEvaluation]):
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
            mark_multi_running(task_id, f"Generating full scenes {index} of {len(completed)}.", 85 + int(4 * index / len(completed)))
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
    task_id,
    output_dir: Path,
    staging_dir: Path,
    shared,
    aggregate,
    payload,
    completed,
    fusion_path: Path | None = None,
    cooperative_intersection_path: Path | None = None,
) -> dict:
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
    if fusion_path is not None:
        fusion_path.replace(output_dir / fusion_path.name)
    if cooperative_intersection_path is not None:
        cooperative_intersection_path.replace(output_dir / cooperative_intersection_path.name)
    for path in staging_dir.glob("*.geojson"):
        path.replace(output_dir / path.name)
    (staging_dir / "station_summaries.json").replace(output_dir / "station_summaries.json")
    (staging_dir / "station_masks.npz").replace(output_dir / "station_masks.npz")
    (staging_dir / "grid.json").replace(output_dir / "grid.json")
    filenames = {
        "visible_union_geojson": "visible_union.geojson", "overlap_geojson": "overlap.geojson",
        "blind_geojson": "blind.geojson", "coverage_count_geojson": "coverage_count.geojson",
        "stations_geojson": "stations.geojson", "station_summaries_json": "station_summaries.json",
    }
    if fusion_path is not None:
        filenames["fusion_scene_glb"] = "fusion_scene.glb"
    if cooperative_intersection_path is not None:
        filenames["cooperative_intersection_glb"] = "cooperative_intersection.glb"
    return {name: f"/outputs/{task_id}/{filename}" for name, filename in filenames.items()}


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
