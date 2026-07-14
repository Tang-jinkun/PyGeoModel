import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_read_air_corridor_metrics_returns_json(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_air_corridor_task(
        tmp_path,
        "air_corridor_task_a",
        "finished",
        metrics={
            "route_found": True,
            "risk_score": 0.2,
            "max_segment_risk": 0.5,
            "mean_segment_risk": 0.2,
            "corridor_length_m": 10000,
            "estimated_time_seconds": 200,
            "min_terrain_clearance_m": 300,
            "mean_terrain_clearance_m": 600,
            "altitude_change_count": 1,
            "min_altitude_m": 300,
            "max_altitude_m": 900,
            "threat_intersection_count": 2,
            "nearest_threat_distance_m": 1500,
        },
    )

    response = TestClient(app).get("/api/air-corridor/planning/air_corridor_task_a/metrics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["route_found"] is True
    assert payload["risk_score"] == 0.2
    assert payload["corridor_length_m"] == 10000


def test_read_air_corridor_metrics_requires_finished_task(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_air_corridor_task(tmp_path, "air_corridor_task_a", "running")

    response = TestClient(app).get("/api/air-corridor/planning/air_corridor_task_a/metrics")

    assert response.status_code == 409


def test_download_air_corridor_scene_glb(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_air_corridor_task(tmp_path, "air_corridor_task_a", "finished")
    output_dir = tmp_path / "outputs" / "air_corridor_task_a"
    output_dir.mkdir(parents=True)
    (output_dir / "air_corridor_result.glb").write_bytes(b"glTF-test")

    response = TestClient(app).get(
        "/api/air-corridor/planning/air_corridor_task_a/outputs/scene_glb"
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "model/gltf-binary"
    assert response.content == b"glTF-test"


def write_air_corridor_task(root: Path, task_id: str, status: str, metrics: dict | None = None) -> None:
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
