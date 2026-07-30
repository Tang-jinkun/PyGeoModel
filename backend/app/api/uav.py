from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, status
from fastapi.responses import FileResponse

from app.core.errors import AppError
from app.schemas.uav import (
    UavOutputFile,
    UavReconMetrics,
    UavReconRequest,
    UavReconTaskDeleteResult,
    UavReconTaskStatus,
    UavReconTaskSummary,
)
from app.services.dem_store import find_dem_file, read_dem_metadata
from app.services.artifact_contracts import get_output_contract
from app.services.artifact_store import get_artifact_store
from app.services.uav_task_store import (
    create_uav_rerun,
    create_uav_task,
    delete_uav_task,
    get_uav_task,
    list_uav_tasks,
    mark_uav_failed,
)
from app.services.task_dispatch import enqueue_task
from app.services.task_scheduler import TaskScheduleSnapshot, get_task_scheduler
from app.workers.uav_recon_task import run_uav_recon_task

router = APIRouter()


@router.get("/recon", response_model=list[UavReconTaskSummary])
def list_recon_tasks() -> list[UavReconTaskSummary]:
    return list_uav_tasks()


@router.post("/recon", response_model=UavReconTaskStatus, status_code=status.HTTP_202_ACCEPTED)
def create_recon_task(payload: UavReconRequest, background_tasks: BackgroundTasks) -> UavReconTaskStatus:
    try:
        read_dem_metadata(payload.dem_id)
        find_dem_file(payload.dem_id)
        task = create_uav_task(payload)
        background_tasks.add_task(enqueue_task, task.task_id, "uav", run_uav_recon_task, payload, on_cancel=lambda: mark_uav_failed(task.task_id, "Task cancelled by user."))
        return task
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/recon/{task_id}", response_model=UavReconTaskStatus)
def read_recon_task(task_id: str) -> UavReconTaskStatus:
    try:
        return get_uav_task(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.post("/recon/{task_id}/rerun", response_model=UavReconTaskStatus, status_code=status.HTTP_202_ACCEPTED)
def rerun_recon_task(
    task_id: str,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> UavReconTaskStatus:
    try:
        original = get_uav_task(task_id)
        if original.request is None:
            raise AppError("TASK_REQUEST_UNAVAILABLE", "Saved request is unavailable.", status_code=409)
        read_dem_metadata(original.request.dem_id)
        find_dem_file(original.request.dem_id)
        task, created = create_uav_rerun(task_id, original.request, idempotency_key)
        if created:
            background_tasks.add_task(enqueue_task, task.task_id, "uav", run_uav_recon_task, original.request, on_cancel=lambda: mark_uav_failed(task.task_id, "Task cancelled by user."))
        return task
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/recon/{task_id}/metrics", response_model=UavReconMetrics)
def read_recon_metrics(task_id: str) -> UavReconMetrics:
    try:
        task = get_uav_task(task_id)
        if task.status != "finished" or task.metrics is None:
            raise AppError("TASK_METRICS_NOT_READY", "UAV metrics are available only after the task is finished.", status_code=409)
        return task.metrics
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/recon/{task_id}/outputs", response_model=list[UavOutputFile])
def list_recon_outputs(task_id: str) -> list[UavOutputFile]:
    try:
        return get_uav_task(task_id).output_files
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/recon/{task_id}/outputs/{kind}")
def download_recon_output(task_id: str, kind: str) -> FileResponse:
    try:
        task = get_uav_task(task_id)
        path, info = get_artifact_store().resolve_download(
            task_id, kind, get_output_contract("uav"), computation_status=task.status
        )
        return FileResponse(path, media_type=info.media_type, filename=info.filename)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.post("/recon/{task_id}/cancel", response_model=TaskScheduleSnapshot)
def cancel_recon_task(task_id: str) -> TaskScheduleSnapshot:
    snapshot = get_task_scheduler().snapshot(task_id)
    if snapshot is None:
        raise HTTPException(status_code=409, detail={"code": "TASK_NOT_ACTIVE", "message": "Task is not queued or running in this service."})
    get_task_scheduler().request_cancel(task_id)
    return get_task_scheduler().snapshot(task_id) or snapshot


@router.delete("/recon/{task_id}", response_model=UavReconTaskDeleteResult)
def delete_recon_task(task_id: str) -> UavReconTaskDeleteResult:
    try:
        return delete_uav_task(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc
