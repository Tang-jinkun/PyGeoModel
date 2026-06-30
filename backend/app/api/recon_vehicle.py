from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import FileResponse

from app.core.errors import AppError
from app.schemas.recon_vehicle import (
    ReconVehicleCoverageMetrics,
    ReconVehicleCoverageRequest,
    ReconVehicleCoverageTaskDeleteResult,
    ReconVehicleCoverageTaskStatus,
    ReconVehicleCoverageTaskSummary,
    ReconVehicleOutputFile,
    ReconVehicleOutputKind,
)
from app.services.dem_store import find_dem_file, read_dem_metadata
from app.services.recon_vehicle_output_files import list_recon_vehicle_task_output_files, resolve_recon_vehicle_task_output_path
from app.services.recon_vehicle_task_store import (
    create_recon_vehicle_task,
    delete_recon_vehicle_task,
    get_recon_vehicle_task,
    list_recon_vehicle_tasks,
)
from app.workers.recon_vehicle_task import run_recon_vehicle_task

router = APIRouter()


@router.get("/coverage", response_model=list[ReconVehicleCoverageTaskSummary])
def list_coverage_tasks() -> list[ReconVehicleCoverageTaskSummary]:
    return list_recon_vehicle_tasks()


@router.post("/coverage", response_model=ReconVehicleCoverageTaskStatus, status_code=status.HTTP_202_ACCEPTED)
def create_coverage_task(payload: ReconVehicleCoverageRequest, background_tasks: BackgroundTasks) -> ReconVehicleCoverageTaskStatus:
    try:
        read_dem_metadata(payload.dem_id)
        find_dem_file(payload.dem_id)
        task = create_recon_vehicle_task(payload)
        background_tasks.add_task(run_recon_vehicle_task, task.task_id, payload)
        return task
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/coverage/{task_id}", response_model=ReconVehicleCoverageTaskStatus)
def read_coverage_task(task_id: str) -> ReconVehicleCoverageTaskStatus:
    try:
        return get_recon_vehicle_task(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/coverage/{task_id}/metrics", response_model=ReconVehicleCoverageMetrics)
def read_coverage_metrics(task_id: str) -> ReconVehicleCoverageMetrics:
    try:
        task = get_recon_vehicle_task(task_id)
        if task.status != "finished" or task.metrics is None:
            raise AppError(
                "TASK_METRICS_NOT_READY",
                "Recon vehicle metrics are available only after the task is finished.",
                status_code=409,
            )
        return task.metrics
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/coverage/{task_id}/outputs", response_model=list[ReconVehicleOutputFile])
def list_coverage_outputs(task_id: str) -> list[ReconVehicleOutputFile]:
    try:
        get_recon_vehicle_task(task_id)
        return list_recon_vehicle_task_output_files(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/coverage/{task_id}/outputs/{kind}")
def download_coverage_output(task_id: str, kind: ReconVehicleOutputKind) -> FileResponse:
    try:
        task = get_recon_vehicle_task(task_id)
        if task.status != "finished":
            raise AppError("TASK_NOT_FINISHED", "Recon vehicle outputs are available only after the task is finished.", status_code=409)
        path = resolve_recon_vehicle_task_output_path(task_id, kind)
        if not path.exists():
            raise AppError("OUTPUT_NOT_FOUND", f"Output '{kind}' was not found.", status_code=404)
        info = next(item for item in list_recon_vehicle_task_output_files(task_id) if item.kind == kind)
        return FileResponse(path, media_type=info.media_type, filename=info.filename)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.delete("/coverage/{task_id}", response_model=ReconVehicleCoverageTaskDeleteResult)
def delete_coverage_task(task_id: str) -> ReconVehicleCoverageTaskDeleteResult:
    try:
        return delete_recon_vehicle_task(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc
