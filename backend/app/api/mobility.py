from typing import Annotated
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, status
from fastapi.responses import FileResponse

from app.core.errors import AppError
from app.schemas.mobility import (
    MobilityAccessibilityMetrics,
    MobilityAccessibilityRequest,
    MobilityAccessibilityTaskDeleteResult,
    MobilityAccessibilityTaskStatus,
    MobilityAccessibilityTaskSummary,
    MobilityOutputFile,
)
from app.services.artifact_contracts import get_output_contract
from app.services.artifact_store import get_artifact_store
from app.services.dem_store import find_dem_file, read_dem_metadata
from app.services.mobility_task_store import (
    create_mobility_rerun,
    create_mobility_task,
    delete_mobility_task,
    get_mobility_task,
    list_mobility_tasks,
)
from app.workers.mobility_task import run_mobility_task

router = APIRouter()


@router.get("/accessibility", response_model=list[MobilityAccessibilityTaskSummary])
def list_accessibility_tasks() -> list[MobilityAccessibilityTaskSummary]:
    return list_mobility_tasks()


@router.post("/accessibility", response_model=MobilityAccessibilityTaskStatus, status_code=status.HTTP_202_ACCEPTED)
def create_accessibility_task(payload: MobilityAccessibilityRequest, background_tasks: BackgroundTasks) -> MobilityAccessibilityTaskStatus:
    try:
        read_dem_metadata(payload.dem_id)
        find_dem_file(payload.dem_id)
        task = create_mobility_task(payload)
        background_tasks.add_task(run_mobility_task, task.task_id, payload)
        return task
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/accessibility/{task_id}", response_model=MobilityAccessibilityTaskStatus)
def read_accessibility_task(task_id: str) -> MobilityAccessibilityTaskStatus:
    try:
        return get_mobility_task(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.post("/accessibility/{task_id}/rerun", response_model=MobilityAccessibilityTaskStatus, status_code=status.HTTP_202_ACCEPTED)
def rerun_accessibility_task(task_id: str, background_tasks: BackgroundTasks, idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)]) -> MobilityAccessibilityTaskStatus:
    try:
        original = get_mobility_task(task_id)
        if original.request is None:
            raise AppError("TASK_REQUEST_UNAVAILABLE", "Saved request is unavailable.", status_code=409)
        read_dem_metadata(original.request.dem_id)
        find_dem_file(original.request.dem_id)
        task, created = create_mobility_rerun(task_id, original.request, idempotency_key)
        if created:
            background_tasks.add_task(run_mobility_task, task.task_id, original.request)
        return task
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/accessibility/{task_id}/metrics", response_model=MobilityAccessibilityMetrics)
def read_accessibility_metrics(task_id: str) -> MobilityAccessibilityMetrics:
    try:
        task = get_mobility_task(task_id)
        if task.status != "finished" or task.metrics is None:
            raise AppError(
                "TASK_METRICS_NOT_READY",
                "Mobility metrics are available only after the task is finished.",
                status_code=409,
            )
        return task.metrics
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/accessibility/{task_id}/outputs", response_model=list[MobilityOutputFile])
def list_accessibility_outputs(task_id: str) -> list[MobilityOutputFile]:
    try:
        return get_mobility_task(task_id).output_files
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/accessibility/{task_id}/outputs/{kind}")
def download_accessibility_output(task_id: str, kind: str) -> FileResponse:
    try:
        task = get_mobility_task(task_id)
        path, info = get_artifact_store().resolve_download(
            task_id, kind, get_output_contract("mobility"), computation_status=task.status
        )
        return FileResponse(path, media_type=info.media_type, filename=info.filename)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.delete("/accessibility/{task_id}", response_model=MobilityAccessibilityTaskDeleteResult)
def delete_accessibility_task(task_id: str) -> MobilityAccessibilityTaskDeleteResult:
    try:
        return delete_mobility_task(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc
