import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.radar import (
    MultiRadarMetrics,
    MultiRadarOutputs,
    MultiRadarRequest,
    MultiRadarSceneAsset,
    MultiRadarStationSummary,
    MultiRadarTaskStatus,
)
from app.services.single_task_store import (
    create_idempotent_rerun,
    delete_task_resources,
    hydrate_task,
    preserve_rerun_metadata,
)
from app.services.task_store import get_task


_TASK_LOCK = RLock()
MULTI_TASK_ID_PATTERN = re.compile(r"^multi_task_[A-Za-z0-9_-]+$")


def create_multi_task(payload: MultiRadarRequest) -> MultiRadarTaskStatus:
    with _TASK_LOCK:
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


def create_multi_rerun(
    original_task_id: str,
    payload: MultiRadarRequest,
    idempotency_key: str,
) -> tuple[MultiRadarTaskStatus, bool]:
    with _TASK_LOCK:
        if not _task_path(original_task_id).exists():
            raise AppError("MULTI_TASK_NOT_FOUND", f"Task '{original_task_id}' was not found.", status_code=404)
        return create_idempotent_rerun(
            original_task_id=original_task_id,
            payload=payload,
            idempotency_key=idempotency_key,
            task_id_prefix="multi_task_",
            record_paths=list(settings.tasks_dir.glob("multi_task_*.json")),
            task_type=MultiRadarTaskStatus,
            task_path=_task_path,
            read_record=_read_record,
            write_record=_write_record,
            get_task=get_multi_task,
        )


def get_multi_task(task_id: str) -> MultiRadarTaskStatus:
    with _TASK_LOCK:
        path = _task_path(task_id)
        if not path.exists():
            raise AppError("MULTI_TASK_NOT_FOUND", f"Task '{task_id}' was not found.", status_code=404)
        try:
            record = _read_record(path)
            task = MultiRadarTaskStatus.model_validate(record["task"])
            task.request = MultiRadarRequest.model_validate(record["payload"])
            task = hydrate_task(task, "multi_radar")
            task.scene_assets = _scene_assets(task)
            return task
        except (KeyError, TypeError, ValueError) as exc:
            raise AppError("MULTI_TASK_RECORD_CORRUPT", f"Task '{task_id}' is invalid.", status_code=500) from exc


def list_multi_tasks() -> list[MultiRadarTaskStatus]:
    tasks = [get_multi_task(path.stem) for path in settings.tasks_dir.glob("multi_task_*.json")]
    return sorted(tasks, key=lambda task: task.created_at or task.task_id, reverse=True)


def mark_multi_running(task_id: str, message: str, progress: int) -> None:
    from app.services.task_scheduler import get_task_scheduler

    get_task_scheduler().raise_if_cancel_requested(task_id)
    with _TASK_LOCK:
        task = get_multi_task(task_id)
        task.status = "running"
        task.progress = progress
        task.message = message
        _save(task)


def mark_multi_completed(
    task_id: str,
    *,
    status: str,
    metrics: dict | MultiRadarMetrics,
    outputs: dict | MultiRadarOutputs,
    stations: list[dict | MultiRadarStationSummary],
    message: str | None = None,
) -> None:
    if status not in {"finished", "partial", "failed"}:
        raise ValueError("Multi-radar task completion status must be finished, partial, or failed")
    with _TASK_LOCK:
        task = get_multi_task(task_id)
        task.status = status
        task.progress = 100
        task.message = message or ("finished" if status == "finished" else status)
        task.metrics = MultiRadarMetrics.model_validate(metrics)
        task.outputs = MultiRadarOutputs.model_validate(outputs)
        task.stations = [MultiRadarStationSummary.model_validate(station) for station in stations]
        task = hydrate_task(task, "multi_radar")
        _save(task)


def mark_multi_failed(task_id: str, message: str) -> None:
    with _TASK_LOCK:
        task = get_multi_task(task_id)
        task.status = "failed"
        task.progress = 100
        task.message = message
        _save(task)


def delete_multi_task(task_id: str) -> tuple[bool, bool, list[str]]:
    with _TASK_LOCK:
        path = _task_path(task_id)
        if path.exists():
            task = get_multi_task(task_id)
            if task.status in {"pending", "running"}:
                raise AppError("TASK_ACTIVE", "Pending or running multi-radar tasks cannot be deleted.", status_code=409)
        return delete_task_resources(task_id, path)


def _save(task: MultiRadarTaskStatus) -> None:
    path = _task_path(task.task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = task.request
    if payload is None:
        raise ValueError("Multi-radar task requires a request payload")
    task.updated_at = _utc_now()
    data = {"task": task.model_dump(exclude={"request"}), "payload": payload.model_dump()}
    preserve_rerun_metadata(data, path, _read_record)
    _write_record(path, data)


def _scene_assets(task: MultiRadarTaskStatus) -> list[MultiRadarSceneAsset]:
    assets: list[MultiRadarSceneAsset] = []
    for station in task.stations:
        if station.scene_status != "finished" or not station.scene_task_id:
            continue
        try:
            scene_task = get_task(station.scene_task_id)
        except AppError:
            continue
        station_label = station.name or station.radar_id
        for kind, render_tier in (
            ("scene_glb", "world"),
            ("radar_platform_glb", "equipment"),
        ):
            file = next((item for item in scene_task.output_files if item.kind == kind and item.exists), None)
            if file is None:
                continue
            assets.append(MultiRadarSceneAsset(
                asset_id=f"{scene_task.task_id}:{kind}",
                task_id=scene_task.task_id,
                radar_id=station.radar_id,
                kind=kind,
                label=f"{station_label} - {file.label}",
                render_tier=render_tier,
                file=file,
            ))
    intersection = next((item for item in task.output_files if item.kind == "cooperative_intersection_glb" and item.exists), None)
    if intersection is not None:
        scene_task_id = f"{task.task_id}--intersection"
        assets.append(MultiRadarSceneAsset(
            asset_id=f"{scene_task_id}:scene_glb",
            task_id=scene_task_id,
            kind="scene_glb",
            label="Cooperative Intersection GLB",
            render_tier="emphasis",
            file=intersection.model_copy(update={"kind": "scene_glb"}),
        ))
    return assets


def _read_record(path: Path) -> dict:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AppError("MULTI_TASK_RECORD_CORRUPT", f"Task '{path.stem}' is invalid.", status_code=500) from exc
    if not isinstance(record, dict):
        raise AppError("MULTI_TASK_RECORD_CORRUPT", f"Task '{path.stem}' is invalid.", status_code=500)
    return record


def _write_record(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
        temporary.replace(path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _task_path(task_id: str) -> Path:
    if not MULTI_TASK_ID_PATTERN.fullmatch(task_id):
        raise AppError("INVALID_MULTI_TASK_ID", "Unsupported task id.", status_code=400)
    tasks_dir = settings.tasks_dir.resolve()
    path = (settings.tasks_dir / f"{task_id}.json").resolve()
    if tasks_dir not in path.parents:
        raise AppError("INVALID_MULTI_TASK_ID", "Unsupported task id.", status_code=400)
    return path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
