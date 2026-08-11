from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.api import radar
from app.core.config import settings
from app.main import create_app
from app.schemas.radar import CoverageRequest, MultiRadarRequest
from app.services.multi_radar_task_store import create_multi_task
from app.services.multi_radar_task_store import mark_multi_completed
from app.services.task_store import create_task


def _single_payload() -> dict:
    return {
        "task_type": "single",
        "dem_id": "dem_a",
        "radar": {"lon": 79, "lat": 31.5, "height_m": 20},
        "coverage": {"max_range_m": 1_000},
    }


def _multi_payload() -> dict:
    return {
        "task_type": "multi",
        "dem_id": "dem_a",
        "radars": [
            {"radar_id": "north", "radar": {"lon": 79, "lat": 31.5, "height_m": 20}, "coverage": {"max_range_m": 1_000}},
            {"radar_id": "south", "radar": {"lon": 79.01, "lat": 31.5, "height_m": 20}, "coverage": {"max_range_m": 1_000}},
        ],
    }


def test_unified_create_dispatches_single_and_multi_tasks(tmp_path, monkeypatch) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    monkeypatch.setattr(radar, "read_dem_metadata", lambda *_: {})
    monkeypatch.setattr(radar, "find_dem_file", lambda *_: tmp_path / "dem.tif")
    monkeypatch.setattr(radar, "validate_coverage_extent", lambda *_: 1.0)
    monkeypatch.setattr(radar, "run_coverage_task", Mock())
    monkeypatch.setattr(radar, "run_multi_radar_coverage_task", Mock())
    client = TestClient(create_app())

    single = client.post("/api/radar/tasks", json=_single_payload())
    multi = client.post("/api/radar/tasks", json=_multi_payload())

    assert single.status_code == 202
    assert single.json()["task_type"] == "single"
    assert single.json()["task_id"].startswith("task_")
    assert multi.status_code == 202
    assert multi.json()["task_type"] == "multi"
    assert multi.json()["task_id"].startswith("multi_task_")


def test_unified_list_merges_tasks_and_supports_variant_filter(tmp_path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    create_task(CoverageRequest.model_validate(_single_payload()))
    create_multi_task(MultiRadarRequest.model_validate(_multi_payload()))
    client = TestClient(create_app())

    merged = client.get("/api/radar/tasks")
    singles = client.get("/api/radar/tasks?task_type=single")
    multis = client.get("/api/radar/tasks?task_type=multi")

    assert merged.status_code == 200
    assert {item["task_type"] for item in merged.json()} == {"single", "multi"}
    assert all(item["task_type"] == "single" for item in singles.json())
    assert all(item["task_type"] == "multi" for item in multis.json())


def test_unified_multi_detail_preserves_variant_metrics_and_outputs(tmp_path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    task = create_multi_task(MultiRadarRequest.model_validate(_multi_payload()))
    mark_multi_completed(
        task.task_id,
        status="finished",
        metrics={"visible_union_area_m2": 123},
        outputs={"visible_union_geojson": "visible_union.geojson"},
        stations=[],
    )

    response = TestClient(create_app()).get(f"/api/radar/tasks/{task.task_id}")

    assert response.status_code == 200
    assert response.json()["task_type"] == "multi"
    assert response.json()["metrics"]["visible_union_area_m2"] == 123
    assert response.json()["outputs"]["visible_union_geojson"] == "visible_union.geojson"


def test_unified_target_endpoint_wraps_single_and_multi_results(tmp_path, monkeypatch) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    monkeypatch.setattr(
        radar,
        "evaluate_coverage_target",
        lambda task_id, payload: {
            "task_id": task_id,
            "detectable": True,
            "reason": "detectable",
            "projected_crs": "EPSG:32648",
            "input_x": payload.x,
            "input_y": payload.y,
            "input_z": payload.z,
            "projected_x": 0,
            "projected_y": 0,
            "distance_m": 10,
            "slant_range_m": 10,
            "azimuth_deg": 0,
            "elevation_deg": 0,
            "radar_altitude_m": 10,
            "maximum_detectable_altitude_m": 100,
            "within_range": True,
            "within_beam": True,
            "within_elevation": True,
            "within_dem": True,
            "terrain_blocked": False,
        },
    )
    monkeypatch.setattr(
        radar,
        "evaluate_multi_radar_target",
        lambda task_id, payload: {
            "task_id": task_id,
            "detected": False,
            "contributors": [{"radar_id": "north", "detected": False}],
        },
    )
    client = TestClient(create_app())

    single = client.post(
        "/api/radar/tasks/task_target/evaluate-target",
        json={"x": 79, "y": 31.5, "z": 100},
    )
    multi = client.post(
        "/api/radar/tasks/multi_task_target/evaluate-target",
        json={"x": 79, "y": 31.5, "z": 100},
    )

    assert single.status_code == 200
    assert single.json()["task_type"] == "single"
    assert single.json()["detected"] is True
    assert single.json()["detail"]["detectable"] is True
    assert multi.status_code == 200
    assert multi.json() == {
        "task_id": "multi_task_target",
        "task_type": "multi",
        "detected": False,
        "detail": None,
        "contributors": [{"radar_id": "north", "detected": False}],
    }


def test_unified_batch_target_endpoint_wraps_multi_results(tmp_path, monkeypatch) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    received_targets = []

    def evaluate_multi(task_id, payload):
        received_targets.append(payload)
        return {
            "task_id": task_id,
            "detected": True,
            "contributors": [{"radar_id": "north", "detected": True}],
        }

    monkeypatch.setattr(
        radar,
        "evaluate_multi_radar_target",
        evaluate_multi,
    )
    client = TestClient(create_app())

    response = client.post(
        "/api/radar/tasks/multi_task_target/evaluate-targets",
        json={
            "targets": [
                {
                    "target_id": "target-1",
                    "x": 79,
                    "y": 31.5,
                    "altitude_reference": "agl",
                    "altitude_m": 100,
                }
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["detected_count"] == 1
    assert received_targets[0].z == 100
    assert payload["results"][0]["evaluation"] == {
        "task_id": "multi_task_target",
        "task_type": "multi",
        "detected": True,
        "detail": None,
        "contributors": [{"radar_id": "north", "detected": True}],
    }


def test_legacy_task_paths_are_not_supported(tmp_path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    client = TestClient(create_app())

    assert client.get("/api/radar/coverage").status_code == 404
    assert client.get("/api/radar/multi-coverage").status_code == 404
    assert client.post(
        "/api/radar/coverage/task_target/evaluate-targets",
        json={"targets": []},
    ).status_code == 404
    assert client.post(
        "/api/radar/multi-coverage/multi_task_target/evaluate-targets",
        json={"targets": []},
    ).status_code == 404


def test_unified_batch_target_endpoint_rejects_invalid_task_id(tmp_path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(
        "/api/radar/tasks/invalid/evaluate-targets",
        json={
            "targets": [
                {
                    "target_id": "target-1",
                    "x": 79,
                    "y": 31.5,
                    "altitude_reference": "amsl",
                    "altitude_m": 100,
                }
            ]
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_TASK_ID"
