from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.artifacts import ArtifactDescriptor
from app.schemas.radar import CoverageTaskStatus, MultiRadarRequest
from app.services import multi_radar_task_store
from app.services.multi_radar_task_store import (
    create_multi_task,
    get_multi_task,
    list_multi_tasks,
    mark_multi_completed,
    mark_multi_running,
)


def station(radar_id: str) -> dict:
    return {
        "radar_id": radar_id,
        "radar": {"lon": 79.0, "lat": 31.5, "height_m": 30},
        "coverage": {"max_range_m": 1_000},
    }


def test_multi_radar_request_rejects_duplicate_station_ids() -> None:
    with pytest.raises(ValidationError, match="radar_id"):
        MultiRadarRequest.model_validate(
            {"dem_id": "dem_a", "radars": [station("north"), station("north")]}
        )


def test_multi_task_round_trip_preserves_station_requests(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    payload = MultiRadarRequest.model_validate(
        {"dem_id": "dem_a", "radars": [station("north"), station("south")]}
    )

    task = create_multi_task(payload)
    stored = get_multi_task(task.task_id)

    assert task.task_id.startswith("multi_task_")
    assert stored.request is not None
    assert [item.radar_id for item in stored.request.radars] == ["north", "south"]


def test_multi_task_running_state_is_persisted_and_listed(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    payload = MultiRadarRequest.model_validate(
        {"dem_id": "dem_a", "radars": [station("north"), station("south")]}
    )
    task = create_multi_task(payload)

    mark_multi_running(task.task_id, "Computing station 1 of 2.", 45)

    assert get_multi_task(task.task_id).status == "running"
    assert list_multi_tasks()[0].message == "Computing station 1 of 2."


def test_multi_task_completion_persists_station_summaries_and_outputs(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    payload = MultiRadarRequest.model_validate(
        {"dem_id": "dem_a", "radars": [station("north"), station("south")]}
    )
    task = create_multi_task(payload)

    mark_multi_completed(
        task.task_id,
        status="partial",
        metrics={"visible_union_area_m2": 125.0},
        outputs={"visible_union_geojson": "/outputs/task/visible_union.geojson"},
        stations=[
            {"radar_id": "north", "status": "finished"},
            {"radar_id": "south", "status": "failed", "message": "outside DEM"},
        ],
    )

    stored = get_multi_task(task.task_id)

    assert stored.status == "partial"
    assert stored.metrics is not None
    assert stored.metrics.visible_union_area_m2 == 125.0
    assert stored.outputs is not None
    assert stored.outputs.visible_union_geojson.endswith("visible_union.geojson")
    assert [(station.radar_id, station.status) for station in stored.stations] == [
        ("north", "finished"),
        ("south", "failed"),
    ]


def test_multi_task_exposes_station_scene_assets(tmp_path: Path, monkeypatch) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    task = create_multi_task(MultiRadarRequest.model_validate(
        {"dem_id": "dem_a", "radars": [station("north"), station("south")]}
    ))
    scene_task = CoverageTaskStatus(
        task_id="coverage_north",
        dem_id="dem_a",
        status="finished",
        output_files=[
            ArtifactDescriptor(
                kind="scene_glb",
                label="Radar Maximum Detection Domain GLB",
                filename="radar_detection_domain.glb",
                media_type="model/gltf-binary",
                exists=True,
                download_path="/api/radar/coverage/coverage_north/outputs/scene_glb",
            ),
            ArtifactDescriptor(
                kind="radar_platform_glb",
                label="Radar Platform GLB",
                filename="radar_platform.glb",
                media_type="model/gltf-binary",
                exists=True,
                download_path="/api/radar/coverage/coverage_north/outputs/radar_platform_glb",
            ),
        ],
    )
    monkeypatch.setattr(multi_radar_task_store, "get_task", lambda _task_id: scene_task, raising=False)
    mark_multi_completed(
        task.task_id,
        status="finished",
        metrics={},
        outputs={},
        stations=[
            {"radar_id": "north", "status": "finished", "scene_task_id": "coverage_north", "scene_status": "finished"},
            {"radar_id": "south", "status": "finished", "scene_task_id": "coverage_south", "scene_status": "failed"},
        ],
    )

    stored = get_multi_task(task.task_id)

    assert [
        (asset.asset_id, asset.task_id, asset.radar_id, asset.kind, asset.render_tier, asset.file.download_path)
        for asset in stored.scene_assets
    ] == [
        ("coverage_north:scene_glb", "coverage_north", "north", "scene_glb", "world", "/api/radar/coverage/coverage_north/outputs/scene_glb"),
        ("coverage_north:radar_platform_glb", "coverage_north", "north", "radar_platform_glb", "equipment", "/api/radar/coverage/coverage_north/outputs/radar_platform_glb"),
    ]
