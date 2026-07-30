from typing import Annotated
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, status
from fastapi.responses import FileResponse

from app.core.errors import AppError
from app.schemas.air_corridor import (
    AirCorridorOutputFile,
    AirCorridorPlanningMetrics,
    AirCorridorPlanningRequest,
    AirCorridorPlanningTaskDeleteResult,
    AirCorridorPlanningTaskStatus,
    AirCorridorPlanningTaskSummary,
)
from app.services.artifact_contracts import get_output_contract
from app.services.artifact_store import get_artifact_store
from app.services.air_corridor_task_store import (
    create_air_corridor_rerun,
    create_air_corridor_task,
    delete_air_corridor_task,
    get_air_corridor_task,
    list_air_corridor_tasks,
    mark_air_corridor_failed,
)
from app.services.task_dispatch import enqueue_task
from app.services.task_scheduler import TaskScheduleSnapshot, get_task_scheduler
from app.services.dem_store import find_dem_file, read_dem_metadata
from app.workers.air_corridor_task import run_air_corridor_task

router = APIRouter()


@router.get("/planning", response_model=list[AirCorridorPlanningTaskSummary])
def list_planning_tasks() -> list[AirCorridorPlanningTaskSummary]:
    return list_air_corridor_tasks()


@router.post("/planning", response_model=AirCorridorPlanningTaskStatus, status_code=status.HTTP_202_ACCEPTED)
def create_planning_task(payload: AirCorridorPlanningRequest, background_tasks: BackgroundTasks) -> AirCorridorPlanningTaskStatus:
    try:
        read_dem_metadata(payload.dem_id)
        find_dem_file(payload.dem_id)
        task = create_air_corridor_task(payload)
        background_tasks.add_task(enqueue_task, task.task_id, "air_corridor", run_air_corridor_task, payload, on_cancel=lambda: mark_air_corridor_failed(task.task_id, "Task cancelled by user."))
        return task
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/planning/{task_id}", response_model=AirCorridorPlanningTaskStatus)
def read_planning_task(task_id: str) -> AirCorridorPlanningTaskStatus:
    try:
        return get_air_corridor_task(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.post("/planning/{task_id}/rerun", response_model=AirCorridorPlanningTaskStatus, status_code=status.HTTP_202_ACCEPTED)
def rerun_planning_task(task_id: str, background_tasks: BackgroundTasks, idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)]) -> AirCorridorPlanningTaskStatus:
    try:
        original = get_air_corridor_task(task_id)
        if original.request is None:
            raise AppError("TASK_REQUEST_UNAVAILABLE", "Saved request is unavailable.", status_code=409)
        read_dem_metadata(original.request.dem_id)
        find_dem_file(original.request.dem_id)
        task, created = create_air_corridor_rerun(task_id, original.request, idempotency_key)
        if created:
            background_tasks.add_task(enqueue_task, task.task_id, "air_corridor", run_air_corridor_task, original.request, on_cancel=lambda: mark_air_corridor_failed(task.task_id, "Task cancelled by user."))
        return task
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/planning/{task_id}/metrics", response_model=AirCorridorPlanningMetrics)
def read_planning_metrics(task_id: str) -> AirCorridorPlanningMetrics:
    try:
        task = get_air_corridor_task(task_id)
        if task.status != "finished" or task.metrics is None:
            raise AppError(
                "TASK_METRICS_NOT_READY",
                "Air corridor metrics are available only after the task is finished.",
                status_code=409,
            )
        return task.metrics
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/planning/{task_id}/outputs", response_model=list[AirCorridorOutputFile])
def list_planning_outputs(task_id: str) -> list[AirCorridorOutputFile]:
    try:
        return get_air_corridor_task(task_id).output_files
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/planning/{task_id}/outputs/{kind}")
def download_planning_output(task_id: str, kind: str) -> FileResponse:
    try:
        task = get_air_corridor_task(task_id)
        path, info = get_artifact_store().resolve_download(
            task_id, kind, get_output_contract("air_corridor"), computation_status=task.status
        )
        return FileResponse(path, media_type=info.media_type, filename=info.filename)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.post("/planning/{task_id}/cancel", response_model=TaskScheduleSnapshot)
def cancel_planning_task(task_id: str) -> TaskScheduleSnapshot:
    snapshot = get_task_scheduler().snapshot(task_id)
    if snapshot is None:
        raise HTTPException(status_code=409, detail={"code": "TASK_NOT_ACTIVE", "message": "Task is not queued or running in this service."})
    get_task_scheduler().request_cancel(task_id)
    return get_task_scheduler().snapshot(task_id) or snapshot


@router.delete("/planning/{task_id}", response_model=AirCorridorPlanningTaskDeleteResult)
def delete_planning_task(task_id: str) -> AirCorridorPlanningTaskDeleteResult:
    try:
        return delete_air_corridor_task(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc
