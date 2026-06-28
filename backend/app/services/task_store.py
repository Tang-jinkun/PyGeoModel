import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.radar import (
    CoverageMetrics,
    CoverageModelMetadata,
    CoverageOutputFile,
    CoverageOutputs,
    CoverageRequest,
    CoverageTaskSummary,
    CoverageTaskStatus,
)


def _task_path(task_id: str) -> Path:
    return settings.tasks_dir / f"{task_id}.json"


def create_task(payload: CoverageRequest) -> CoverageTaskStatus:
    now = utc_now()
    task_id = f"task_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    task = CoverageTaskStatus(
        task_id=task_id,
        dem_id=payload.dem_id,
        status="pending",
        progress=0,
        message="queued",
        created_at=now,
        updated_at=now,
        request=payload,
    )
    save_task(task, payload)
    return task


def save_task(task: CoverageTaskStatus, payload: CoverageRequest | None = None) -> None:
    if task.created_at is None:
        task.created_at = utc_now()
    task.updated_at = utc_now()
    if payload is not None:
        task.request = payload
    data = {"task": task.model_dump(exclude={"request"})}
    if payload is not None:
        data["payload"] = payload.model_dump()
    existing_payload = None
    path = _task_path(task.task_id)
    if payload is None and path.exists():
        existing_payload = json.loads(path.read_text(encoding="utf-8")).get("payload")
    if existing_payload is not None:
        data["payload"] = existing_payload
    elif task.request is not None:
        data["payload"] = task.request.model_dump()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_task(task_id: str) -> CoverageTaskStatus:
    path = _task_path(task_id)
    if not path.exists():
        raise AppError("TASK_NOT_FOUND", f"Task '{task_id}' was not found.", status_code=404)
    data = json.loads(path.read_text(encoding="utf-8"))
    task_data = data["task"]
    task = CoverageTaskStatus.model_validate(task_data)
    payload = data.get("payload")
    if task.dem_id is None and payload:
        task.dem_id = payload.get("dem_id")
    request = parse_request(payload) or task.request
    task.request = request
    return task


def list_tasks() -> list[CoverageTaskSummary]:
    tasks: list[CoverageTaskSummary] = []
    for path in settings.tasks_dir.glob("task_*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        task = CoverageTaskSummary.model_validate(data["task"])
        payload = data.get("payload")
        if task.dem_id is None and payload:
            task.dem_id = payload.get("dem_id")
        tasks.append(task)
    return sorted(tasks, key=lambda item: item.created_at or item.task_id, reverse=True)


def mark_running(task_id: str, message: str, progress: int = 10) -> None:
    task = get_task(task_id)
    task.status = "running"
    task.progress = progress
    task.message = message
    save_task(task)


def mark_finished(
    task_id: str,
    metrics: CoverageMetrics,
    outputs: CoverageOutputs,
    output_files: list[CoverageOutputFile] | None = None,
    model: CoverageModelMetadata | None = None,
    warnings: list[str] | None = None,
) -> None:
    task = get_task(task_id)
    task.status = "finished"
    task.progress = 100
    task.message = "finished"
    task.metrics = metrics
    task.outputs = outputs
    task.output_files = output_files or []
    task.model = model
    task.warnings = warnings or []
    save_task(task)


def mark_failed(task_id: str, message: str) -> None:
    task = get_task(task_id)
    task.status = "failed"
    task.progress = 100
    task.message = message
    save_task(task)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_request(payload) -> CoverageRequest | None:
    if not payload:
        return None
    try:
        return CoverageRequest.model_validate(payload)
    except Exception:
        return None
