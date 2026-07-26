import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.radar import MultiRadarRequest, MultiRadarTaskStatus


def create_multi_task(payload: MultiRadarRequest) -> MultiRadarTaskStatus:
    now = _utc_now()
    task = MultiRadarTaskStatus(
        task_id=f"multi_task_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}",
        dem_id=payload.dem_id,
        status="pending",
        message="queued",
        created_at=now,
        updated_at=now,
        request=payload,
    )
    _save(task)
    return task


def get_multi_task(task_id: str) -> MultiRadarTaskStatus:
    path = _task_path(task_id)
    if not path.exists():
        raise AppError("MULTI_TASK_NOT_FOUND", f"Task '{task_id}' was not found.", status_code=404)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        task = MultiRadarTaskStatus.model_validate(record["task"])
        task.request = MultiRadarRequest.model_validate(record["payload"])
        return task
    except (KeyError, TypeError, ValueError) as exc:
        raise AppError("MULTI_TASK_RECORD_CORRUPT", f"Task '{task_id}' is invalid.", status_code=500) from exc


def list_multi_tasks() -> list[MultiRadarTaskStatus]:
    tasks = [get_multi_task(path.stem) for path in settings.tasks_dir.glob("multi_task_*.json")]
    return sorted(tasks, key=lambda task: task.created_at or task.task_id, reverse=True)


def mark_multi_running(task_id: str, message: str, progress: int) -> None:
    task = get_multi_task(task_id)
    task.status = "running"
    task.progress = progress
    task.message = message
    _save(task)


def _save(task: MultiRadarTaskStatus) -> None:
    path = _task_path(task.task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = task.request
    if payload is None:
        raise ValueError("Multi-radar task requires a request payload")
    task.updated_at = _utc_now()
    path.write_text(
        json.dumps(
            {"task": task.model_dump(exclude={"request"}), "payload": payload.model_dump()},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _task_path(task_id: str) -> Path:
    if not task_id.startswith("multi_task_"):
        raise AppError("INVALID_MULTI_TASK_ID", "Unsupported task id.", status_code=400)
    return settings.tasks_dir / f"{task_id}.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
