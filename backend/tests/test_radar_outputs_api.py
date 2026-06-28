import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_list_coverage_outputs(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_task(tmp_path, "task_a", "finished")
    output_dir = tmp_path / "outputs" / "task_a"
    output_dir.mkdir(parents=True)
    (output_dir / "visible.geojson").write_text("{}", encoding="utf-8")

    response = TestClient(app).get("/api/radar/coverage/task_a/outputs")

    assert response.status_code == 200
    payload = response.json()
    visible = next(item for item in payload if item["kind"] == "visible_geojson")
    assert visible["exists"] is True
    assert visible["download_url"] == "/api/radar/coverage/task_a/outputs/visible_geojson"


def test_download_coverage_output(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_task(tmp_path, "task_a", "finished")
    output_dir = tmp_path / "outputs" / "task_a"
    output_dir.mkdir(parents=True)
    (output_dir / "model_metadata.json").write_text('{"ok": true}', encoding="utf-8")

    response = TestClient(app).get("/api/radar/coverage/task_a/outputs/model_metadata_json")

    assert response.status_code == 200
    assert response.content == b'{"ok": true}'
    assert response.headers["content-type"].startswith("application/json")
    assert "model_metadata.json" in response.headers["content-disposition"]


def test_download_coverage_output_requires_finished_task(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_task(tmp_path, "task_a", "running")

    response = TestClient(app).get("/api/radar/coverage/task_a/outputs/model_metadata_json")

    assert response.status_code == 409


def test_download_coverage_output_missing_file(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_task(tmp_path, "task_a", "finished")

    response = TestClient(app).get("/api/radar/coverage/task_a/outputs/model_metadata_json")

    assert response.status_code == 404


def write_task(root: Path, task_id: str, status: str) -> None:
    task_dir = root / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / f"{task_id}.json").write_text(
        json.dumps(
            {
                "task": {
                    "task_id": task_id,
                    "dem_id": "dem_a",
                    "status": status,
                    "progress": 100 if status == "finished" else 50,
                    "message": status,
                    "warnings": [],
                }
            }
        ),
        encoding="utf-8",
    )
