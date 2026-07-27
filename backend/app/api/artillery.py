from typing import Annotated
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, status
from fastapi.responses import FileResponse

from app.core.errors import AppError
from app.schemas.artillery import (
    ArtilleryCoverageMetrics,
    ArtilleryCoverageRequest,
    ArtilleryCoverageTaskDeleteResult,
    ArtilleryCoverageTaskStatus,
    ArtilleryCoverageTaskSummary,
    ArtilleryOutputFile,
)
from app.services.artifact_contracts import get_output_contract
from app.services.artifact_store import get_artifact_store
from app.services.artillery_task_store import (
    create_artillery_rerun,
    create_artillery_task,
    delete_artillery_task,
    get_artillery_task,
    list_artillery_tasks,
)
from app.services.dem_store import find_dem_file, read_dem_metadata
from app.workers.artillery_task import run_artillery_task

router = APIRouter()


@router.get("/coverage", response_model=list[ArtilleryCoverageTaskSummary])
def list_coverage_tasks() -> list[ArtilleryCoverageTaskSummary]:
    return list_artillery_tasks()


@router.post("/coverage", response_model=ArtilleryCoverageTaskStatus, status_code=status.HTTP_202_ACCEPTED)
def create_coverage_task(payload: ArtilleryCoverageRequest, background_tasks: BackgroundTasks) -> ArtilleryCoverageTaskStatus:
    try:
        read_dem_metadata(payload.dem_id)
        find_dem_file(payload.dem_id)
        task = create_artillery_task(payload)
        background_tasks.add_task(run_artillery_task, task.task_id, payload)
        return task
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/coverage/{task_id}", response_model=ArtilleryCoverageTaskStatus)
def read_coverage_task(task_id: str) -> ArtilleryCoverageTaskStatus:
    try:
        return get_artillery_task(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.post("/coverage/{task_id}/rerun", response_model=ArtilleryCoverageTaskStatus, status_code=status.HTTP_202_ACCEPTED)
def rerun_coverage_task(task_id: str, background_tasks: BackgroundTasks, idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)]) -> ArtilleryCoverageTaskStatus:
    try:
        original = get_artillery_task(task_id)
        if original.request is None:
            raise AppError("TASK_REQUEST_UNAVAILABLE", "Saved request is unavailable.", status_code=409)
        read_dem_metadata(original.request.dem_id)
        find_dem_file(original.request.dem_id)
        task, created = create_artillery_rerun(task_id, original.request, idempotency_key)
        if created:
            background_tasks.add_task(run_artillery_task, task.task_id, original.request)
        return task
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/coverage/{task_id}/metrics", response_model=ArtilleryCoverageMetrics)
def read_coverage_metrics(task_id: str) -> ArtilleryCoverageMetrics:
    try:
        task = get_artillery_task(task_id)
        if task.status != "finished" or task.metrics is None:
            raise AppError(
                "TASK_METRICS_NOT_READY",
                "Artillery metrics are available only after the task is finished.",
                status_code=409,
            )
        return task.metrics
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/coverage/{task_id}/outputs", response_model=list[ArtilleryOutputFile])
def list_coverage_outputs(task_id: str) -> list[ArtilleryOutputFile]:
    try:
        return get_artillery_task(task_id).output_files
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/coverage/{task_id}/outputs/{kind}")
def download_coverage_output(task_id: str, kind: str) -> FileResponse:
    try:
        task = get_artillery_task(task_id)
        path, info = get_artifact_store().resolve_download(
            task_id, kind, get_output_contract("artillery"), computation_status=task.status
        )
        return FileResponse(path, media_type=info.media_type, filename=info.filename)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.delete("/coverage/{task_id}", response_model=ArtilleryCoverageTaskDeleteResult)
def delete_coverage_task(task_id: str) -> ArtilleryCoverageTaskDeleteResult:
    try:
        return delete_artillery_task(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc
