from pathlib import Path
from types import SimpleNamespace

import numpy
import rasterio
from rasterio.transform import from_origin

from app.core.config import settings
from app.schemas.radar import MultiRadarRequest
from app.services.multi_radar_task_store import create_multi_task, get_multi_task
from app.workers import multi_radar_coverage_task
from app.workers.multi_radar_coverage_task import station_masks_to_shared_grid


def _payload() -> MultiRadarRequest:
    return MultiRadarRequest.model_validate(
        {
            "dem_id": "dem_a",
            "radars": [
                {
                    "radar_id": "good",
                    "name": "North Ridge",
                    "radar": {"lon": 79, "lat": 31.5, "height_m": 20},
                    "coverage": {"max_range_m": 1_000},
                },
                {
                    "radar_id": "bad",
                    "radar": {"lon": 79.1, "lat": 31.5, "height_m": 20},
                    "coverage": {"max_range_m": 1_000},
                },
            ],
        }
    )


def _cooperative_payload() -> MultiRadarRequest:
    return MultiRadarRequest.model_validate(
        {
            "dem_id": "dem_a",
            "presentation_mode": "cooperative_3d",
            "radars": [
                {
                    "radar_id": radar_id,
                    "radar": {"lon": lon, "lat": 31.5, "height_m": 20},
                    "coverage": {"max_range_m": 1_000},
                }
                for radar_id, lon in (("north", 79.0), ("south", 79.01), ("east", 79.02))
            ],
        }
    )


def test_multi_worker_keeps_successful_station_when_a_sibling_fails(tmp_path: Path, monkeypatch) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    payload = _payload()
    task = create_multi_task(payload)
    prepared = multi_radar_coverage_task.SharedMultiRadarDem(
        projected_dem=tmp_path / "projected.tif",
        target_epsg=32644,
        transform=from_origin(0, 2, 1, 1),
        analysis_domain=numpy.ones((2, 2), dtype=bool),
        station_points={"good": (0.5, 1.5), "bad": (1.5, 1.5)},
    )

    def evaluate(shared, station):
        if station.radar_id == "bad":
            raise RuntimeError("outside DEM")
        return multi_radar_coverage_task.StationEvaluation(
            radar_id="good",
            name="North Ridge",
            visible_mask=numpy.array([[True, False], [False, False]]),
            range_mask=numpy.ones((2, 2), dtype=bool),
            metrics={"visible_area_m2": 1},
        )

    monkeypatch.setattr(multi_radar_coverage_task, "find_dem_file", lambda _: tmp_path / "source.tif")
    monkeypatch.setattr(multi_radar_coverage_task, "prepare_shared_multi_radar_dem", lambda *_: prepared)

    multi_radar_coverage_task.run_multi_radar_coverage_task(task.task_id, payload, evaluator=evaluate)

    stored = get_multi_task(task.task_id)
    assert stored.status == "partial"
    assert stored.result_state == "ready"
    assert stored.metrics is not None
    assert stored.metrics.visible_union_area_m2 == 1
    assert stored.outputs is not None
    assert (tmp_path / "outputs" / task.task_id / "visible_union.geojson").exists()
    assert (tmp_path / "outputs" / task.task_id / "artifact-manifest.json").exists()
    public_kinds = {item.kind for item in stored.output_files}
    assert "visible_union_geojson" in public_kinds
    assert "station_masks_npz" not in public_kinds
    assert "grid_json" not in public_kinds
    assert [(station.radar_id, station.status) for station in stored.stations] == [
        ("good", "finished"),
        ("bad", "failed"),
    ]


def test_station_masks_are_placed_back_on_the_shared_grid(tmp_path: Path) -> None:
    shared = multi_radar_coverage_task.SharedMultiRadarDem(
        projected_dem=tmp_path / "projected.tif",
        target_epsg=32644,
        transform=from_origin(0, 4, 1, 1),
        analysis_domain=numpy.ones((4, 4), dtype=bool),
        station_points={"north": (1.5, 2.5)},
    )

    visible, theoretical = station_masks_to_shared_grid(
        shared,
        from_origin(1, 3, 1, 1),
        numpy.array([[True, False], [False, True]]),
        numpy.ones((2, 2), dtype=bool),
    )

    assert visible.tolist() == [
        [False, False, False, False],
        [False, True, False, False],
        [False, False, True, False],
        [False, False, False, False],
    ]
    assert theoretical.sum() == 4


def test_cooperative_worker_records_a_complete_scene_task_for_each_station(tmp_path: Path, monkeypatch) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    payload = _cooperative_payload()
    task = create_multi_task(payload)
    prepared = multi_radar_coverage_task.SharedMultiRadarDem(
        projected_dem=tmp_path / "projected.tif",
        target_epsg=32644,
        transform=from_origin(0, 2, 1, 1),
        analysis_domain=numpy.ones((2, 2), dtype=bool),
        station_points={"north": (0.5, 1.5), "south": (1.0, 1.5), "east": (1.5, 1.5)},
    )

    def evaluate(_shared, station):
        return multi_radar_coverage_task.StationEvaluation(
            radar_id=station.radar_id,
            name=station.name,
            visible_mask=numpy.array([[True, False], [False, False]]),
            range_mask=numpy.ones((2, 2), dtype=bool),
            metrics={"visible_area_m2": 1},
        )

    monkeypatch.setattr(multi_radar_coverage_task, "find_dem_file", lambda _: tmp_path / "source.tif")
    monkeypatch.setattr(multi_radar_coverage_task, "prepare_shared_multi_radar_dem", lambda *_: prepared)
    monkeypatch.setattr(
        multi_radar_coverage_task,
        "create_task",
        lambda request: SimpleNamespace(task_id=f"scene-{request.radar.lon}", request=request),
        raising=False,
    )
    monkeypatch.setattr(multi_radar_coverage_task, "run_coverage_task", lambda *_: None, raising=False)
    monkeypatch.setattr(
        multi_radar_coverage_task,
        "get_task",
        lambda task_id: SimpleNamespace(task_id=task_id, status="finished", message="finished"),
        raising=False,
    )

    multi_radar_coverage_task.run_multi_radar_coverage_task(task.task_id, payload, evaluator=evaluate)

    stored = get_multi_task(task.task_id)
    assert stored.status == "finished"
    assert {station.radar_id: station.scene_task_id for station in stored.stations} == {
        "north": "scene-79.0",
        "south": "scene-79.01",
        "east": "scene-79.02",
    }
    assert {station.scene_status for station in stored.stations} == {"finished"}


def test_cooperative_worker_writes_only_the_common_detection_glb(tmp_path: Path, monkeypatch) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    payload = _cooperative_payload()
    task = create_multi_task(payload)
    projected_dem = tmp_path / "projected.tif"
    with rasterio.open(
        projected_dem,
        "w",
        driver="GTiff",
        width=2,
        height=2,
        count=1,
        dtype="float32",
        crs="EPSG:32644",
        transform=from_origin(0, 2, 1, 1),
        nodata=-9999,
    ) as source:
        source.write(numpy.zeros((2, 2), dtype=numpy.float32), 1)
    prepared = multi_radar_coverage_task.SharedMultiRadarDem(
        projected_dem=projected_dem,
        target_epsg=32644,
        transform=from_origin(0, 2, 1, 1),
        analysis_domain=numpy.ones((2, 2), dtype=bool),
        station_points={"north": (0.5, 1.5), "south": (1.0, 1.5), "east": (1.5, 1.5)},
    )

    def evaluate(_shared, station):
        return multi_radar_coverage_task.StationEvaluation(
            radar_id=station.radar_id,
            name=station.name,
            visible_mask=numpy.ones((2, 2), dtype=bool),
            range_mask=numpy.ones((2, 2), dtype=bool),
            metrics={"visible_area_m2": 4},
            fusion_masks=numpy.ones((len(multi_radar_coverage_task.FUSION_HEIGHTS_M), 2, 2), dtype=bool),
        )

    monkeypatch.setattr(multi_radar_coverage_task, "find_dem_file", lambda _: tmp_path / "source.tif")
    monkeypatch.setattr(multi_radar_coverage_task, "prepare_shared_multi_radar_dem", lambda *_: prepared)
    monkeypatch.setattr(
        multi_radar_coverage_task,
        "create_task",
        lambda request: SimpleNamespace(task_id=f"scene-{request.radar.lon}", request=request),
    )
    monkeypatch.setattr(multi_radar_coverage_task, "run_coverage_task", lambda *_: None)
    monkeypatch.setattr(
        multi_radar_coverage_task,
        "get_task",
        lambda task_id: SimpleNamespace(task_id=task_id, status="finished", message="finished"),
    )

    multi_radar_coverage_task.run_multi_radar_coverage_task(task.task_id, payload, evaluator=evaluate)

    stored = get_multi_task(task.task_id)
    assert stored.outputs is not None
    assert stored.outputs.cooperative_intersection_glb.endswith(
        "/outputs/cooperative_intersection_glb"
    )
    assert stored.outputs.fusion_scene_glb is None
    assert (tmp_path / "outputs" / task.task_id / "cooperative_intersection.glb").exists()
