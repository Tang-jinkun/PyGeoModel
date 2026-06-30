from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import FileResponse

from app.core.errors import AppError
from app.schemas.artillery import (
    ArtilleryCoverageMetrics,
    ArtilleryCoverageRequest,
    ArtilleryCoverageTaskDeleteResult,
    ArtilleryCoverageTaskStatus,
    ArtilleryCoverageTaskSummary,
    ArtilleryOutputFile,
    ArtilleryOutputKind,
)
from app.services.artillery_output_files import list_artillery_task_output_files, resolve_artillery_task_output_path
from app.services.artillery_task_store import (
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
        get_artillery_task(task_id)
        return list_artillery_task_output_files(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/coverage/{task_id}/outputs/{kind}")
def download_coverage_output(task_id: str, kind: ArtilleryOutputKind) -> FileResponse:
    try:
        task = get_artillery_task(task_id)
        if task.status != "finished":
            raise AppError("TASK_NOT_FINISHED", "Artillery outputs are available only after the task is finished.", status_code=409)
        path = resolve_artillery_task_output_path(task_id, kind)
        if not path.exists():
            raise AppError("OUTPUT_NOT_FOUND", f"Output '{kind}' was not found.", status_code=404)
        info = next(item for item in list_artillery_task_output_files(task_id) if item.kind == kind)
        return FileResponse(path, media_type=info.media_type, filename=info.filename)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.delete("/coverage/{task_id}", response_model=ArtilleryCoverageTaskDeleteResult)
def delete_coverage_task(task_id: str) -> ArtilleryCoverageTaskDeleteResult:
    try:
        return delete_artillery_task(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc
