import json
from pathlib import Path

from app.core.config import settings
from app.schemas.radar import CoverageMetrics, CoverageOutputs, CoverageRequest
import pytest

from app.core.errors import AppError
from app.services.task_store import (
    create_task,
    delete_task,
    get_task,
    list_tasks,
    mark_finished,
    mark_running,
    recover_interrupted_tasks,
)


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
    assert not list((tmp_path / "tasks").glob("*.tmp"))


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


def test_list_tasks_quarantines_corrupt_records(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()

    write_legacy_task(tmp_path, "task_good", "dem_good", "2026-01-02T00:00:00+00:00")
    corrupt_path = tmp_path / "tasks" / "task_bad.json"
    corrupt_path.write_text("{", encoding="utf-8")

    tasks = list_tasks()

    assert [task.task_id for task in tasks] == ["task_good"]
    assert not corrupt_path.exists()
    assert list((tmp_path / "tasks").glob("task_bad.json*.corrupt"))


def test_list_tasks_ignores_temp_files(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()

    write_legacy_task(tmp_path, "task_good", "dem_good", "2026-01-02T00:00:00+00:00")
    temp_path = tmp_path / "tasks" / ".task_good.json.partial.tmp"
    temp_path.write_text("{", encoding="utf-8")

    tasks = list_tasks()

    assert [task.task_id for task in tasks] == ["task_good"]
    assert temp_path.exists()


def test_list_tasks_quarantines_invalid_shape(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    bad_path = tmp_path / "tasks" / "task_bad.json"
    bad_path.write_text("[]", encoding="utf-8")

    assert list_tasks() == []
    assert not bad_path.exists()
    assert list((tmp_path / "tasks").glob("task_bad.json*.corrupt"))


def test_list_tasks_quarantines_invalid_schema(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    bad_path = tmp_path / "tasks" / "task_bad.json"
    bad_path.write_text(json.dumps({"task": {"task_id": "task_bad"}}), encoding="utf-8")

    assert list_tasks() == []
    assert not bad_path.exists()
    assert list((tmp_path / "tasks").glob("task_bad.json*.corrupt"))


def test_get_task_quarantines_corrupt_record(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    corrupt_path = tmp_path / "tasks" / "task_bad.json"
    corrupt_path.write_text("{", encoding="utf-8")

    with pytest.raises(AppError) as exc_info:
        get_task("task_bad")

    assert exc_info.value.code == "TASK_RECORD_CORRUPT"
    assert not corrupt_path.exists()
    assert list((tmp_path / "tasks").glob("task_bad.json*.corrupt"))


def test_get_task_missing_raises_not_found(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()

    with pytest.raises(AppError) as exc_info:
        get_task("task_missing")

    assert exc_info.value.code == "TASK_NOT_FOUND"


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


def test_recover_interrupted_tasks_marks_active_tasks_failed(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()

    pending = create_task(make_request("dem_pending"))
    running = create_task(make_request("dem_running"))
    finished = create_task(make_request("dem_finished"))
    mark_running(running.task_id, "running", 40)
    mark_finished(finished.task_id, metrics=CoverageMetrics(), outputs=CoverageOutputs())

    recovered = recover_interrupted_tasks()

    assert recovered == 2
    assert get_task(pending.task_id).status == "failed"
    assert get_task(pending.task_id).progress == 100
    assert "interrupted" in get_task(pending.task_id).message
    assert get_task(running.task_id).status == "failed"
    assert get_task(finished.task_id).status == "finished"


def test_recover_interrupted_tasks_skips_corrupt_records(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()

    pending = create_task(make_request("dem_pending"))
    corrupt_path = tmp_path / "tasks" / "task_bad.json"
    corrupt_path.write_text("{", encoding="utf-8")

    recovered = recover_interrupted_tasks()

    assert recovered == 1
    assert get_task(pending.task_id).status == "failed"
    assert not corrupt_path.exists()
    assert list((tmp_path / "tasks").glob("task_bad.json*.corrupt"))


def test_delete_task_removes_record_and_outputs(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()

    task = create_task(make_request("dem_a"))
    mark_finished(task.task_id, metrics=CoverageMetrics(), outputs=CoverageOutputs())
    output_dir = tmp_path / "outputs" / task.task_id
    output_dir.mkdir(parents=True)
    (output_dir / "visible.geojson").write_text("{}", encoding="utf-8")
    (output_dir / "dem_projected.tif").write_bytes(b"intermediate")
    dem_dir = tmp_path / "dem" / "dem_a"
    dem_dir.mkdir(parents=True)
    (dem_dir / "metadata.json").write_text("{}", encoding="utf-8")

    result = delete_task(task.task_id)

    assert result.deleted_task_record is True
    assert result.deleted_output_dir is True
    assert not (tmp_path / "tasks" / f"{task.task_id}.json").exists()
    assert not output_dir.exists()
    assert dem_dir.exists()


def test_delete_task_without_output_dir_reports_record_only(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()

    task = create_task(make_request("dem_a"))
    mark_finished(task.task_id, metrics=CoverageMetrics(), outputs=CoverageOutputs())

    result = delete_task(task.task_id)

    assert result.deleted_task_record is True
    assert result.deleted_output_dir is False


def test_delete_task_rejects_running_task(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()

    task = create_task(make_request("dem_a"))
    mark_running(task.task_id, "running")

    with pytest.raises(AppError) as exc_info:
        delete_task(task.task_id)

    assert exc_info.value.code == "TASK_ACTIVE"


def test_delete_task_rejects_pending_task(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()

    task = create_task(make_request("dem_a"))

    with pytest.raises(AppError) as exc_info:
        delete_task(task.task_id)

    assert exc_info.value.code == "TASK_ACTIVE"


def test_get_task_rejects_invalid_task_id(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()

    with pytest.raises(AppError) as exc_info:
        get_task("../task_a")

    assert exc_info.value.code == "INVALID_TASK_ID"


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
