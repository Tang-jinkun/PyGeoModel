import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_read_watchpost_metrics_returns_json(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_watchpost_task(
        tmp_path,
        "watchpost_task_a",
        "finished",
        metrics={
            "theoretical_area_m2": 1000,
            "visible_area_m2": 750,
            "blocked_area_m2": 250,
            "blocked_ratio": 0.25,
            "max_range_m": 5000,
            "effective_view_angle_deg": 120,
            "observer_ground_elevation_m": 3200,
            "observer_altitude_m": 3208,
        },
    )

    response = TestClient(app).get("/api/watchpost/detection/watchpost_task_a/metrics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["theoretical_area_m2"] == 1000
    assert payload["visible_area_m2"] == 750
    assert payload["blocked_ratio"] == 0.25
    assert payload["effective_view_angle_deg"] == 120


def test_read_watchpost_metrics_requires_finished_task(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_watchpost_task(tmp_path, "watchpost_task_a", "running")

    response = TestClient(app).get("/api/watchpost/detection/watchpost_task_a/metrics")

    assert response.status_code == 409


def write_watchpost_task(root: Path, task_id: str, status: str, metrics: dict | None = None) -> None:
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
