import json
from unittest.mock import Mock

import numpy
from fastapi.testclient import TestClient

from app.api import radar
from app.core.config import settings
from app.main import create_app
from app.schemas.radar import MultiRadarRequest
from app.services.multi_radar_task_store import create_multi_task, mark_multi_completed


def _payload() -> dict:
    return {
        "dem_id": "dem_a",
        "radars": [
            {"radar_id": "north", "radar": {"lon": 79, "lat": 31.5, "height_m": 20}, "coverage": {"max_range_m": 1_000}},
            {"radar_id": "south", "radar": {"lon": 79.01, "lat": 31.5, "height_m": 20}, "coverage": {"max_range_m": 1_000}},
        ],
    }


def _cooperative_payload(count: int) -> dict:
    stations = _payload()["radars"]
    return {
        "dem_id": "dem_a",
        "presentation_mode": "cooperative_3d",
        "radars": [
            {
                **stations[index % len(stations)],
                "radar_id": f"station_{index}",
                "radar": {
                    **stations[index % len(stations)]["radar"],
                    "lon": 79 + index * 0.01,
                },
            }
            for index in range(count)
        ],
    }


def test_create_multi_radar_task_returns_accepted(tmp_path, monkeypatch) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    monkeypatch.setattr(radar, "read_dem_metadata", lambda *_: {})
    monkeypatch.setattr(radar, "find_dem_file", lambda *_: tmp_path / "dem.tif")
    monkeypatch.setattr(radar, "validate_coverage_extent", lambda *_: 1.0)
    monkeypatch.setattr(radar, "run_multi_radar_coverage_task", lambda *_: None)

    response = TestClient(create_app()).post("/api/radar/multi-coverage", json=_payload())

    assert response.status_code == 202
    assert response.json()["status"] == "pending"
    assert response.json()["task_id"].startswith("multi_task_")


def test_cooperative_task_requires_two_to_five_stations(tmp_path, monkeypatch) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    monkeypatch.setattr(radar, "read_dem_metadata", lambda *_: {})
    monkeypatch.setattr(radar, "find_dem_file", lambda *_: tmp_path / "dem.tif")
    monkeypatch.setattr(radar, "validate_coverage_extent", lambda *_: 1.0)

    response = TestClient(create_app()).post(
        "/api/radar/multi-coverage", json=_cooperative_payload(6)
    )

    assert response.status_code == 422
    assert "two to five" in response.json()["detail"][0]["msg"]


def test_cooperative_task_returns_presentation_mode(tmp_path, monkeypatch) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    monkeypatch.setattr(radar, "read_dem_metadata", lambda *_: {})
    monkeypatch.setattr(radar, "find_dem_file", lambda *_: tmp_path / "dem.tif")
    monkeypatch.setattr(radar, "validate_coverage_extent", lambda *_: 1.0)
    monkeypatch.setattr(radar, "run_multi_radar_coverage_task", lambda *_: None)

    response = TestClient(create_app()).post(
        "/api/radar/multi-coverage", json=_cooperative_payload(2)
    )

    assert response.status_code == 202
    assert response.json()["request"]["presentation_mode"] == "cooperative_3d"


def test_multi_target_evaluation_reports_any_detecting_contributor(tmp_path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    task = create_multi_task(MultiRadarRequest.model_validate(_payload()))
    output_dir = tmp_path / "outputs" / task.task_id
    output_dir.mkdir(parents=True)
    numpy.savez_compressed(
        output_dir / "station_masks.npz",
        north=numpy.array([[True, False], [False, False]]),
        south=numpy.zeros((2, 2), dtype=bool),
    )
    (output_dir / "grid.json").write_text(
        json.dumps({"target_epsg": 4326, "transform": [1, 0, 0, 0, -1, 2], "shape": [2, 2]}),
        encoding="utf-8",
    )
    mark_multi_completed(
        task.task_id,
        status="finished",
        metrics={},
        outputs={},
        stations=[
            {"radar_id": "north", "status": "finished"},
            {"radar_id": "south", "status": "finished"},
        ],
    )

    response = TestClient(create_app()).post(
        f"/api/radar/multi-coverage/{task.task_id}/evaluate-target",
        json={"x": 0.5, "y": 1.5, "z": 100},
    )

    assert response.status_code == 200
    assert response.json()["detected"] is True
    assert response.json()["contributors"] == [
        {"radar_id": "north", "detected": True},
        {"radar_id": "south", "detected": False},
    ]


def test_completed_multi_task_without_artifacts_is_unavailable(tmp_path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    task = create_multi_task(MultiRadarRequest.model_validate(_payload()))
    mark_multi_completed(task.task_id, status="finished", metrics={}, outputs={}, stations=[])
    client = TestClient(create_app())

    detail = client.get(f"/api/radar/multi-coverage/{task.task_id}")
    download = client.get(
        f"/api/radar/multi-coverage/{task.task_id}/outputs/visible_union_geojson"
    )
    rerun = client.post(f"/api/radar/multi-coverage/{task.task_id}/rerun")

    assert detail.status_code == 200
    assert detail.json()["result_state"] == "unavailable"
    assert download.status_code == 410
    assert rerun.status_code == 422


def test_multi_rerun_reuses_child_and_schedules_once(tmp_path, monkeypatch) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    task = create_multi_task(MultiRadarRequest.model_validate(_payload()))
    mark_multi_completed(task.task_id, status="finished", metrics={}, outputs={}, stations=[])
    scheduled = Mock()
    monkeypatch.setattr(radar, "read_dem_metadata", lambda *_: {})
    monkeypatch.setattr(radar, "find_dem_file", lambda *_: tmp_path / "dem.tif")
    monkeypatch.setattr(radar, "validate_coverage_extent", lambda *_: 1.0)
    monkeypatch.setattr(radar, "run_multi_radar_coverage_task", scheduled)
    client = TestClient(create_app())
    headers = {"Idempotency-Key": "multi-rerun-key"}

    first = client.post(f"/api/radar/multi-coverage/{task.task_id}/rerun", headers=headers)
    second = client.post(f"/api/radar/multi-coverage/{task.task_id}/rerun", headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["task_id"] == second.json()["task_id"]
    assert first.json()["rerun_of"] == task.task_id
    assert scheduled.call_count == 1
