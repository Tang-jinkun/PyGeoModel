import json
import os
import re
import shutil
from contextlib import contextmanager
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from threading import RLock
from uuid import uuid4

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.mobility import (
    MobilityAccessibilityMetrics,
    MobilityAccessibilityOutputs,
    MobilityAccessibilityRequest,
    MobilityAccessibilityTaskDeleteResult,
    MobilityAccessibilityTaskStatus,
    MobilityAccessibilityTaskSummary,
    MobilityModelMetadata,
    MobilityOutputFile,
)

MOBILITY_TASK_ID_PATTERN = re.compile(r"^mobility_task_[A-Za-z0-9_-]+$")
_TASK_LOCKS: dict[str, RLock] = {}
_TASK_LOCKS_LOCK = RLock()


def validate_mobility_task_id(task_id: str) -> None:
    if not MOBILITY_TASK_ID_PATTERN.fullmatch(task_id):
        raise AppError("INVALID_TASK_ID", "Mobility task id contains unsupported characters.", status_code=400)


def create_mobility_task(payload: MobilityAccessibilityRequest) -> MobilityAccessibilityTaskStatus:
    now = utc_now()
    task_id = f"mobility_task_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    task = MobilityAccessibilityTaskStatus(
        task_id=task_id,
        dem_id=payload.dem_id,
        status="pending",
        progress=0,
        message="queued",
        created_at=now,
        updated_at=now,
        request=payload,
    )
    save_mobility_task(task, payload)
    return task


def save_mobility_task(task: MobilityAccessibilityTaskStatus, payload: MobilityAccessibilityRequest | None = None) -> None:
    with _task_lock(task.task_id):
        _save_task_unlocked(task, payload)


def get_mobility_task(task_id: str) -> MobilityAccessibilityTaskStatus:
    with _task_lock(task_id):
        path = _task_path(task_id)
        if not path.exists():
            raise AppError("TASK_NOT_FOUND", f"Mobility task '{task_id}' was not found.", status_code=404)
        data = _read_task_data(path)
        task, payload = _parse_task_record(data, detail=True)
        task.request = parse_mobility_request(payload) or task.request
        if task.dem_id is None and task.request:
            task.dem_id = task.request.dem_id
        return task


def list_mobility_tasks() -> list[MobilityAccessibilityTaskSummary]:
    tasks: list[MobilityAccessibilityTaskSummary] = []
    for path in settings.tasks_dir.glob("mobility_task_*.json"):
        try:
            data = _read_task_data(path)
            task, payload = _parse_task_record(data, detail=False)
        except AppError:
            continue
        if task.dem_id is None and isinstance(payload, dict):
            task.dem_id = payload.get("dem_id")
        tasks.append(task)
    return sorted(tasks, key=lambda item: item.created_at or item.task_id, reverse=True)


def mark_mobility_running(task_id: str, message: str, progress: int = 10) -> None:
    with _task_lock(task_id):
        task = get_mobility_task(task_id)
        task.status = "running"
        task.progress = progress
        task.message = message
        _save_task_unlocked(task)


def mark_mobility_finished(
    task_id: str,
    metrics: MobilityAccessibilityMetrics,
    outputs: MobilityAccessibilityOutputs,
    output_files: list[MobilityOutputFile],
    model: MobilityModelMetadata,
    warnings: list[str] | None = None,
) -> None:
    with _task_lock(task_id):
        task = get_mobility_task(task_id)
        task.status = "finished"
        task.progress = 100
        task.message = "finished"
        task.metrics = metrics
        task.outputs = outputs
        task.output_files = output_files
        task.model = model
        task.warnings = warnings or []
        _save_task_unlocked(task)


def mark_mobility_failed(task_id: str, message: str) -> None:
    with _task_lock(task_id):
        task = get_mobility_task(task_id)
        task.status = "failed"
        task.progress = 100
        task.message = message
        _save_task_unlocked(task)


def delete_mobility_task(task_id: str) -> MobilityAccessibilityTaskDeleteResult:
    with _task_lock(task_id):
        task = get_mobility_task(task_id)
        if task.status in {"pending", "running"}:
            raise AppError("TASK_ACTIVE", "Pending or running mobility tasks cannot be deleted.", status_code=409)
        task_path = _task_path(task_id)
        output_dir = _task_output_dir(task_id)
        deleted_task_record = False
        deleted_output_dir = False
        if task_path.exists():
            task_path.unlink()
            deleted_task_record = True
        if output_dir.exists():
            shutil.rmtree(output_dir)
            deleted_output_dir = True
        return MobilityAccessibilityTaskDeleteResult(
            task_id=task_id,
            deleted_task_record=deleted_task_record,
            deleted_output_dir=deleted_output_dir,
        )


def recover_interrupted_mobility_tasks() -> int:
    recovered = 0
    for path in settings.tasks_dir.glob("mobility_task_*.json"):
        with _task_lock(path.stem):
            try:
                data = _read_task_data(path)
                task, payload = _parse_task_record(data, detail=True)
            except AppError:
                continue
            if task.status not in {"pending", "running"}:
                continue
            task.status = "failed"
            task.progress = 100
            task.message = "Task was interrupted before completion and marked failed on service startup."
            _save_task_unlocked(task, parse_mobility_request(payload))
            recovered += 1
    return recovered


def parse_mobility_request(payload) -> MobilityAccessibilityRequest | None:
    if not payload:
        return None
    try:
        return MobilityAccessibilityRequest.model_validate(payload)
    except Exception:
        return None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_task_unlocked(task: MobilityAccessibilityTaskStatus, payload: MobilityAccessibilityRequest | None = None) -> None:
    if task.created_at is None:
        task.created_at = utc_now()
    task.updated_at = utc_now()
    if payload is not None:
        task.request = payload
    data = {"task": task.model_dump(exclude={"request"})}
    if payload is not None:
        data["payload"] = payload.model_dump()
    elif task.request is not None:
        data["payload"] = task.request.model_dump()
    _write_task_data(_task_path(task.task_id), data)


def _task_path(task_id: str) -> Path:
    validate_mobility_task_id(task_id)
    path = (settings.tasks_dir / f"{task_id}.json").resolve()
    tasks_dir = settings.tasks_dir.resolve()
    if tasks_dir not in path.parents:
        raise AppError("INVALID_TASK_PATH", "Resolved task path escapes task directory.", status_code=400)
    return path


def _task_output_dir(task_id: str) -> Path:
    validate_mobility_task_id(task_id)
    path = (settings.outputs_dir / task_id).resolve()
    outputs_dir = settings.outputs_dir.resolve()
    if path != outputs_dir and outputs_dir not in path.parents:
        raise AppError("INVALID_OUTPUT_PATH", "Resolved output path escapes output directory.", status_code=400)
    return path


def _read_task_data(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        raise AppError("TASK_RECORD_CORRUPT", f"Task record '{path.name}' is not readable.", status_code=500) from exc
    except OSError as exc:
        raise AppError("TASK_RECORD_UNREADABLE", f"Task record '{path.name}' is temporarily unreadable.", status_code=500) from exc
    if not isinstance(data, dict):
        raise AppError("TASK_RECORD_CORRUPT", f"Task record '{path.name}' has an invalid shape.", status_code=500)
    return data


def _parse_task_record(data: dict, detail: bool) -> tuple[MobilityAccessibilityTaskStatus | MobilityAccessibilityTaskSummary, dict | None]:
    task_data = data.get("task")
    if not isinstance(task_data, dict):
        raise AppError("TASK_RECORD_CORRUPT", "Mobility task data is invalid.", status_code=500)
    task = MobilityAccessibilityTaskStatus.model_validate(task_data) if detail else MobilityAccessibilityTaskSummary.model_validate(task_data)
    payload = data.get("payload")
    return task, payload if isinstance(payload, dict) else None


def _write_task_data(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        temp_path.replace(path)
        _fsync_directory(path.parent)
    finally:
        if temp_path.exists():
            temp_path.unlink()


@contextmanager
def _task_lock(task_id: str):
    with _TASK_LOCKS_LOCK:
        lock = _TASK_LOCKS.setdefault(task_id, RLock())
    with lock:
        yield


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
