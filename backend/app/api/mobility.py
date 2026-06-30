from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import FileResponse

from app.core.errors import AppError
from app.schemas.mobility import (
    MobilityAccessibilityMetrics,
    MobilityAccessibilityRequest,
    MobilityAccessibilityTaskDeleteResult,
    MobilityAccessibilityTaskStatus,
    MobilityAccessibilityTaskSummary,
    MobilityOutputFile,
    MobilityOutputKind,
)
from app.services.dem_store import find_dem_file, read_dem_metadata
from app.services.mobility_output_files import list_mobility_task_output_files, resolve_mobility_task_output_path
from app.services.mobility_task_store import (
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
        get_mobility_task(task_id)
        return list_mobility_task_output_files(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/accessibility/{task_id}/outputs/{kind}")
def download_accessibility_output(task_id: str, kind: MobilityOutputKind) -> FileResponse:
    try:
        task = get_mobility_task(task_id)
        if task.status != "finished":
            raise AppError("TASK_NOT_FINISHED", "Mobility outputs are available only after the task is finished.", status_code=409)
        path = resolve_mobility_task_output_path(task_id, kind)
        if not path.exists():
            raise AppError("OUTPUT_NOT_FOUND", f"Output '{kind}' was not found.", status_code=404)
        info = next(item for item in list_mobility_task_output_files(task_id) if item.kind == kind)
        return FileResponse(path, media_type=info.media_type, filename=info.filename)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.delete("/accessibility/{task_id}", response_model=MobilityAccessibilityTaskDeleteResult)
def delete_accessibility_task(task_id: str) -> MobilityAccessibilityTaskDeleteResult:
    try:
        return delete_mobility_task(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc
