import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_read_recon_vehicle_metrics_returns_json(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_recon_vehicle_task(
        tmp_path,
        "recon_vehicle_task_a",
        "finished",
        metrics={
            "theoretical_area_m2": 1000,
            "visible_area_m2": 650,
            "blocked_area_m2": 350,
            "blocked_ratio": 0.35,
            "max_range_m": 5000,
            "effective_view_angle_deg": 120,
            "coverage_point_count": 4,
            "route_length_m": 1200,
            "average_visible_area_m2": 300,
            "overlap_area_m2": 550,
            "vehicle_ground_elevation_m": 3200,
            "sensor_altitude_m": 3203,
        },
    )

    response = TestClient(app).get("/api/recon-vehicle/coverage/recon_vehicle_task_a/metrics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["theoretical_area_m2"] == 1000
    assert payload["visible_area_m2"] == 650
    assert payload["blocked_ratio"] == 0.35
    assert payload["coverage_point_count"] == 4
    assert payload["route_length_m"] == 1200


def test_read_recon_vehicle_metrics_requires_finished_task(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_recon_vehicle_task(tmp_path, "recon_vehicle_task_a", "running")

    response = TestClient(app).get("/api/recon-vehicle/coverage/recon_vehicle_task_a/metrics")

    assert response.status_code == 409


def write_recon_vehicle_task(root: Path, task_id: str, status: str, metrics: dict | None = None) -> None:
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
