import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.radar import CoverageMetrics, CoverageOutputs, CoverageRequest, CoverageTaskStatus


def _task_path(task_id: str) -> Path:
    return settings.tasks_dir / f"{task_id}.json"


def create_task(payload: CoverageRequest) -> CoverageTaskStatus:
    task_id = f"task_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    task = CoverageTaskStatus(task_id=task_id, status="pending", progress=0, message="queued")
    save_task(task, payload)
    return task


def save_task(task: CoverageTaskStatus, payload: CoverageRequest | None = None) -> None:
    data = {"task": task.model_dump()}
    if payload is not None:
        data["payload"] = payload.model_dump()
    existing_payload = None
    path = _task_path(task.task_id)
    if payload is None and path.exists():
        existing_payload = json.loads(path.read_text(encoding="utf-8")).get("payload")
    if existing_payload is not None:
        data["payload"] = existing_payload
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_task(task_id: str) -> CoverageTaskStatus:
    path = _task_path(task_id)
    if not path.exists():
        raise AppError("TASK_NOT_FOUND", f"Task '{task_id}' was not found.", status_code=404)
    data = json.loads(path.read_text(encoding="utf-8"))
    return CoverageTaskStatus.model_validate(data["task"])


def mark_running(task_id: str, message: str, progress: int = 10) -> None:
    task = get_task(task_id)
    task.status = "running"
    task.progress = progress
    task.message = message
    save_task(task)


def mark_finished(task_id: str, metrics: CoverageMetrics, outputs: CoverageOutputs) -> None:
    task = get_task(task_id)
    task.status = "finished"
    task.progress = 100
    task.message = "finished"
    task.metrics = metrics
    task.outputs = outputs
    save_task(task)


def mark_failed(task_id: str, message: str) -> None:
    task = get_task(task_id)
    task.status = "failed"
    task.progress = 100
    task.message = message
    save_task(task)
