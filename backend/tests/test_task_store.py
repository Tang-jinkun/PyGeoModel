import json
from pathlib import Path

from app.core.config import settings
from app.schemas.radar import CoverageRequest
from app.services.task_store import create_task, get_task, list_tasks, mark_running


def test_create_task_stores_runtime_fields(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()

    task = create_task(make_request("dem_a"))
    stored = get_task(task.task_id)

    assert stored.dem_id == "dem_a"
    assert stored.created_at is not None
    assert stored.updated_at is not None
    assert stored.request is not None
    assert stored.request.dem_id == "dem_a"

    task_file = next((tmp_path / "tasks").glob("task_*.json"))
    payload = json.loads(task_file.read_text(encoding="utf-8"))
    assert "payload" in payload
    assert "request" not in payload["task"]


def test_list_tasks_sorted_and_infers_legacy_dem_id(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()

    write_legacy_task(tmp_path, "task_old", "dem_old", "2026-01-01T00:00:00+00:00")
    write_legacy_task(tmp_path, "task_new", "dem_new", "2026-01-02T00:00:00+00:00")

    tasks = list_tasks()

    assert [task.task_id for task in tasks] == ["task_new", "task_old"]
    assert tasks[0].dem_id == "dem_new"
    assert not hasattr(tasks[0], "request")

    detail = get_task("task_new")
    assert detail.request is not None
    assert detail.request.dem_id == "dem_new"


def test_mark_running_updates_timestamp(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()

    task = create_task(make_request("dem_a"))
    before = get_task(task.task_id).updated_at
    mark_running(task.task_id, "running", 33)
    after = get_task(task.task_id)

    assert after.status == "running"
    assert after.progress == 33
    assert after.updated_at is not None
    assert after.updated_at != before


def make_request(dem_id: str) -> CoverageRequest:
    return CoverageRequest.model_validate(
        {
            "dem_id": dem_id,
            "radar": {"lon": 105, "lat": 35, "height_m": 10},
            "target": {"height_m": 0},
            "coverage": {
                "max_range_m": 1000,
                "scan_mode": "omni",
                "azimuth_deg": 0,
                "beam_width_deg": 360,
            },
        }
    )


def write_legacy_task(root: Path, task_id: str, dem_id: str, created_at: str) -> None:
    path = root / "tasks" / f"{task_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "task": {
                    "task_id": task_id,
                    "status": "finished",
                    "progress": 100,
                    "message": "finished",
                    "created_at": created_at,
                    "updated_at": created_at,
                    "warnings": [],
                },
                "payload": {
                    "dem_id": dem_id,
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
