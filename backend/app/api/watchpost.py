from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import FileResponse

from app.core.errors import AppError
from app.schemas.watchpost import (
    WatchpostDetectionMetrics,
    WatchpostDetectionRequest,
    WatchpostDetectionTaskDeleteResult,
    WatchpostDetectionTaskStatus,
    WatchpostDetectionTaskSummary,
    WatchpostOutputFile,
    WatchpostOutputKind,
)
from app.services.dem_store import find_dem_file, read_dem_metadata
from app.services.watchpost_output_files import list_watchpost_task_output_files, resolve_watchpost_task_output_path
from app.services.watchpost_task_store import (
    create_watchpost_task,
    delete_watchpost_task,
    get_watchpost_task,
    list_watchpost_tasks,
)
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
        background_tasks.add_task(run_watchpost_task, task.task_id, payload)
        return task
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/detection/{task_id}", response_model=WatchpostDetectionTaskStatus)
def read_detection_task(task_id: str) -> WatchpostDetectionTaskStatus:
    try:
        return get_watchpost_task(task_id)
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
        get_watchpost_task(task_id)
        return list_watchpost_task_output_files(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/detection/{task_id}/outputs/{kind}")
def download_detection_output(task_id: str, kind: WatchpostOutputKind) -> FileResponse:
    try:
        task = get_watchpost_task(task_id)
        if task.status != "finished":
            raise AppError("TASK_NOT_FINISHED", "Watchpost outputs are available only after the task is finished.", status_code=409)
        path = resolve_watchpost_task_output_path(task_id, kind)
        if not path.exists():
            raise AppError("OUTPUT_NOT_FOUND", f"Output '{kind}' was not found.", status_code=404)
        info = next(item for item in list_watchpost_task_output_files(task_id) if item.kind == kind)
        return FileResponse(path, media_type=info.media_type, filename=info.filename)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.delete("/detection/{task_id}", response_model=WatchpostDetectionTaskDeleteResult)
def delete_detection_task(task_id: str) -> WatchpostDetectionTaskDeleteResult:
    try:
        return delete_watchpost_task(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc
