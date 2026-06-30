import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_read_artillery_metrics_returns_json(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_artillery_task(
        tmp_path,
        "artillery_task_a",
        "finished",
        metrics={
            "theoretical_area_m2": 1000,
            "reachable_area_m2": 700,
            "terrain_masked_area_m2": 300,
            "terrain_masked_ratio": 0.3,
            "lethal_area_m2": 120,
            "effective_area_m2": 500,
            "min_range_m": 1000,
            "max_range_m": 15000,
            "effective_traverse_deg": 120,
            "lethal_radius_m": 50,
            "effective_radius_m": 120,
            "sample_point_count": 20,
            "reachable_sample_count": 14,
            "masked_sample_count": 6,
            "min_clearance_m": -40,
            "mean_clearance_m": 25,
            "battery_ground_elevation_m": 3200,
            "battery_altitude_m": 3200,
        },
    )

    response = TestClient(app).get("/api/artillery/coverage/artillery_task_a/metrics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["theoretical_area_m2"] == 1000
    assert payload["reachable_area_m2"] == 700
    assert payload["terrain_masked_ratio"] == 0.3
    assert payload["sample_point_count"] == 20


def test_read_artillery_metrics_requires_finished_task(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_artillery_task(tmp_path, "artillery_task_a", "running")

    response = TestClient(app).get("/api/artillery/coverage/artillery_task_a/metrics")

    assert response.status_code == 409


def write_artillery_task(root: Path, task_id: str, status: str, metrics: dict | None = None) -> None:
    task_dir = root / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    task = {
        "task_id": task_id,
        "dem_id": "dem_a",
        "status": status,
        "progress": 100 if status == "finished" else 50,
        "message": status,
        "warnings": [],
    }
    if metrics is not None:
        task["metrics"] = metrics
    (task_dir / f"{task_id}.json").write_text(json.dumps({"task": task}), encoding="utf-8")
