import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_read_mobility_metrics_returns_json(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_mobility_task(
        tmp_path,
        "mobility_task_a",
        "finished",
        metrics={
            "winner": "tracked",
            "time_saving_seconds": 120,
            "time_saving_ratio": 0.2,
            "wheeled": {
                "reachable": True,
                "travel_time_seconds": 600,
                "travel_distance_m": 3000,
                "average_speed_kph": 18,
                "road_distance_m": 1000,
                "offroad_distance_m": 2000,
            },
            "tracked": {
                "reachable": True,
                "travel_time_seconds": 480,
                "travel_distance_m": 3000,
                "average_speed_kph": 22.5,
                "road_distance_m": 1000,
                "offroad_distance_m": 2000,
            },
        },
    )

    response = TestClient(app).get("/api/mobility/accessibility/mobility_task_a/metrics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["winner"] == "tracked"
    assert payload["tracked"]["travel_time_seconds"] == 480
    assert payload["wheeled"]["reachable"] is True


def test_read_mobility_metrics_requires_finished_task(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_mobility_task(tmp_path, "mobility_task_a", "running")

    response = TestClient(app).get("/api/mobility/accessibility/mobility_task_a/metrics")

    assert response.status_code == 409


def write_mobility_task(root: Path, task_id: str, status: str, metrics: dict | None = None) -> None:
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
