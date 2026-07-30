from typing import Annotated
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, status
from fastapi.responses import FileResponse

from app.core.errors import AppError
from app.schemas.watchpost import (
    WatchpostDetectionMetrics,
    WatchpostDetectionRequest,
    WatchpostDetectionTaskDeleteResult,
    WatchpostDetectionTaskStatus,
    WatchpostDetectionTaskSummary,
    WatchpostOutputFile,
)
from app.services.artifact_contracts import get_output_contract
from app.services.artifact_store import get_artifact_store
from app.services.dem_store import find_dem_file, read_dem_metadata
from app.services.watchpost_task_store import (
    create_watchpost_rerun,
    create_watchpost_task,
    delete_watchpost_task,
    get_watchpost_task,
    list_watchpost_tasks,
    mark_watchpost_failed,
)
from app.services.task_dispatch import enqueue_task
from app.services.task_scheduler import TaskScheduleSnapshot, get_task_scheduler
from app.workers.watchpost_task import run_watchpost_task

router = APIRouter()


@router.get("/detection", response_model=list[WatchpostDetectionTaskSummary])
def list_detection_tasks() -> list[WatchpostDetectionTaskSummary]:
    return list_watchpost_tasks()


@router.post("/detection", response_model=WatchpostDetectionTaskStatus, status_code=status.HTTP_202_ACCEPTED)
def create_detection_task(payload: WatchpostDetectionRequest, background_tasks: BackgroundTasks) -> WatchpostDetectionTaskStatus:
    try:
        read_dem_metadata(payload.dem_id)
        find_dem_file(payload.dem_id)
        task = create_watchpost_task(payload)
        background_tasks.add_task(enqueue_task, task.task_id, "watchpost", run_watchpost_task, payload, on_cancel=lambda: mark_watchpost_failed(task.task_id, "Task cancelled by user."))
        return task
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/detection/{task_id}", response_model=WatchpostDetectionTaskStatus)
def read_detection_task(task_id: str) -> WatchpostDetectionTaskStatus:
    try:
        return get_watchpost_task(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.post("/detection/{task_id}/rerun", response_model=WatchpostDetectionTaskStatus, status_code=status.HTTP_202_ACCEPTED)
def rerun_detection_task(task_id: str, background_tasks: BackgroundTasks, idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)]) -> WatchpostDetectionTaskStatus:
    try:
        original = get_watchpost_task(task_id)
        if original.request is None:
            raise AppError("TASK_REQUEST_UNAVAILABLE", "Saved request is unavailable.", status_code=409)
        read_dem_metadata(original.request.dem_id)
        find_dem_file(original.request.dem_id)
        task, created = create_watchpost_rerun(task_id, original.request, idempotency_key)
        if created:
            background_tasks.add_task(enqueue_task, task.task_id, "watchpost", run_watchpost_task, original.request, on_cancel=lambda: mark_watchpost_failed(task.task_id, "Task cancelled by user."))
        return task
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/detection/{task_id}/metrics", response_model=WatchpostDetectionMetrics)
def read_detection_metrics(task_id: str) -> WatchpostDetectionMetrics:
    try:
        task = get_watchpost_task(task_id)
        if task.status != "finished" or task.metrics is None:
            raise AppError("TASK_METRICS_NOT_READY", "Watchpost metrics are available only after the task is finished.", status_code=409)
        return task.metrics
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/detection/{task_id}/outputs", response_model=list[WatchpostOutputFile])
def list_detection_outputs(task_id: str) -> list[WatchpostOutputFile]:
    try:
        return get_watchpost_task(task_id).output_files
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/detection/{task_id}/outputs/{kind}")
def download_detection_output(task_id: str, kind: str) -> FileResponse:
    try:
        task = get_watchpost_task(task_id)
        path, info = get_artifact_store().resolve_download(
            task_id, kind, get_output_contract("watchpost"), computation_status=task.status
        )
        return FileResponse(path, media_type=info.media_type, filename=info.filename)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.post("/detection/{task_id}/cancel", response_model=TaskScheduleSnapshot)
def cancel_detection_task(task_id: str) -> TaskScheduleSnapshot:
    snapshot = get_task_scheduler().snapshot(task_id)
    if snapshot is None:
        raise HTTPException(status_code=409, detail={"code": "TASK_NOT_ACTIVE", "message": "Task is not queued or running in this service."})
    get_task_scheduler().request_cancel(task_id)
    return get_task_scheduler().snapshot(task_id) or snapshot


@router.delete("/detection/{task_id}", response_model=WatchpostDetectionTaskDeleteResult)
def delete_detection_task(task_id: str) -> WatchpostDetectionTaskDeleteResult:
    try:
        return delete_watchpost_task(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc
