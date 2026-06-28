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


def test_read_coverage_task_includes_request(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_task_with_payload(tmp_path, "task_a", "finished")

    response = TestClient(app).get("/api/radar/coverage/task_a")

    assert response.status_code == 200
    payload = response.json()
    assert payload["request"]["dem_id"] == "dem_a"
    assert payload["request"]["radar"]["lon"] == 105


def test_list_coverage_tasks_omits_request(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_task_with_payload(tmp_path, "task_a", "finished")

    response = TestClient(app).get("/api/radar/coverage")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["task_id"] == "task_a"
    assert "request" not in payload[0]


def test_delete_coverage_task_api(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_task(tmp_path, "task_a", "finished")
    output_dir = tmp_path / "outputs" / "task_a"
    output_dir.mkdir(parents=True)
    (output_dir / "visible.geojson").write_text("{}", encoding="utf-8")

    response = TestClient(app).delete("/api/radar/coverage/task_a")

    assert response.status_code == 200
    payload = response.json()
    assert payload["deleted_task_record"] is True
    assert payload["deleted_output_dir"] is True
    assert not output_dir.exists()


def test_delete_coverage_task_api_rejects_running(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_task(tmp_path, "task_a", "running")

    response = TestClient(app).delete("/api/radar/coverage/task_a")

    assert response.status_code == 409


def test_delete_coverage_task_api_rejects_invalid_id(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()

    response = TestClient(app).delete("/api/radar/coverage/..%5Ctask_a")

    assert response.status_code == 400


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


def write_task_with_payload(root: Path, task_id: str, status: str) -> None:
    task_dir = root / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / f"{task_id}.json").write_text(
        json.dumps(
            {
                "task": {
                    "task_id": task_id,
                    "dem_id": "dem_a",
                    "status": status,
                    "progress": 100,
                    "message": status,
                    "warnings": [],
                },
                "payload": {
                    "dem_id": "dem_a",
                    "radar": {"lon": 105, "lat": 35, "height_m": 10},
                    "target": {"height_m": 0},
                    "coverage": {
                        "max_range_m": 1000,
                        "scan_mode": "omni",
                        "azimuth_deg": 0,
                        "beam_width_deg": 360,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
