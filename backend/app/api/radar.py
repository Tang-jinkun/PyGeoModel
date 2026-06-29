from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import FileResponse

from app.core.errors import AppError
from app.schemas.radar import (
    CoverageOutputFile,
    CoverageOutputKind,
    CoverageProfileResult,
    CoverageRequest,
    CoverageTaskDeleteResult,
    CoverageTaskStatus,
    CoverageTaskSummary,
)
from app.services.output_files import list_task_output_files, resolve_task_output_path
from app.services.coverage_model import validate_coverage_extent
from app.services.dem_store import find_dem_file, read_dem_metadata
from app.services.profile_analysis import analyze_coverage_profile
from app.services.task_store import create_task, delete_task, get_task, list_tasks
from app.workers.coverage_task import run_coverage_task

router = APIRouter()


@router.get("/coverage", response_model=list[CoverageTaskSummary])
def list_coverage_tasks() -> list[CoverageTaskSummary]:
    return list_tasks()


@router.post("/coverage", response_model=CoverageTaskStatus, status_code=status.HTTP_202_ACCEPTED)
def create_coverage_task(payload: CoverageRequest, background_tasks: BackgroundTasks) -> CoverageTaskStatus:
    try:
        read_dem_metadata(payload.dem_id)
        validate_coverage_extent(find_dem_file(payload.dem_id), payload)
        task = create_task(payload)
        background_tasks.add_task(run_coverage_task, task.task_id, payload)
        return task
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/coverage/{task_id}", response_model=CoverageTaskStatus)
def read_coverage_task(task_id: str) -> CoverageTaskStatus:
    try:
        return get_task(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/coverage/{task_id}/profile", response_model=CoverageProfileResult)
def read_coverage_profile(task_id: str, lon: float, lat: float, samples: int = 160) -> CoverageProfileResult:
    try:
        return analyze_coverage_profile(task_id, lon, lat, samples=samples)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.delete("/coverage/{task_id}", response_model=CoverageTaskDeleteResult)
def delete_coverage_task(task_id: str) -> CoverageTaskDeleteResult:
    try:
        return delete_task(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/coverage/{task_id}/outputs", response_model=list[CoverageOutputFile])
def list_coverage_outputs(task_id: str) -> list[CoverageOutputFile]:
    try:
        get_task(task_id)
        return list_task_output_files(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/coverage/{task_id}/outputs/{kind}")
def download_coverage_output(task_id: str, kind: CoverageOutputKind) -> FileResponse:
    try:
        task = get_task(task_id)
        if task.status != "finished":
            raise AppError("TASK_NOT_FINISHED", "Task outputs are available only after the task is finished.", status_code=409)

        path = resolve_task_output_path(task_id, kind)
        if not path.exists():
            raise AppError("OUTPUT_NOT_FOUND", f"Output '{kind}' was not found.", status_code=404)

        info = next(item for item in list_task_output_files(task_id) if item.kind == kind)
        return FileResponse(path, media_type=info.media_type, filename=info.filename)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc
