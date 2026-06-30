from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import FileResponse

from app.core.errors import AppError
from app.schemas.uav import (
    UavOutputFile,
    UavOutputKind,
    UavReconMetrics,
    UavReconRequest,
    UavReconTaskDeleteResult,
    UavReconTaskStatus,
    UavReconTaskSummary,
)
from app.services.dem_store import find_dem_file, read_dem_metadata
from app.services.uav_output_files import list_uav_task_output_files, resolve_uav_task_output_path
from app.services.uav_task_store import (
    create_uav_task,
    delete_uav_task,
    get_uav_task,
    list_uav_tasks,
)
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
        background_tasks.add_task(run_uav_recon_task, task.task_id, payload)
        return task
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/recon/{task_id}", response_model=UavReconTaskStatus)
def read_recon_task(task_id: str) -> UavReconTaskStatus:
    try:
        return get_uav_task(task_id)
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
        get_uav_task(task_id)
        return list_uav_task_output_files(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/recon/{task_id}/outputs/{kind}")
def download_recon_output(task_id: str, kind: UavOutputKind) -> FileResponse:
    try:
        task = get_uav_task(task_id)
        if task.status != "finished":
            raise AppError("TASK_NOT_FINISHED", "UAV outputs are available only after the task is finished.", status_code=409)

        path = resolve_uav_task_output_path(task_id, kind)
        if not path.exists():
            raise AppError("OUTPUT_NOT_FOUND", f"Output '{kind}' was not found.", status_code=404)

        info = next(item for item in list_uav_task_output_files(task_id) if item.kind == kind)
        return FileResponse(path, media_type=info.media_type, filename=info.filename)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.delete("/recon/{task_id}", response_model=UavReconTaskDeleteResult)
def delete_recon_task(task_id: str) -> UavReconTaskDeleteResult:
    try:
        return delete_uav_task(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc
