from typing import Annotated
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, status
from fastapi.responses import FileResponse

from app.core.errors import AppError
from app.schemas.recon_vehicle import (
    ReconVehicleCoverageMetrics,
    ReconVehicleCoverageRequest,
    ReconVehicleCoverageTaskDeleteResult,
    ReconVehicleCoverageTaskStatus,
    ReconVehicleCoverageTaskSummary,
    ReconVehicleOutputFile,
)
from app.services.artifact_contracts import get_output_contract
from app.services.artifact_store import get_artifact_store
from app.services.dem_store import find_dem_file, read_dem_metadata
from app.services.recon_vehicle_task_store import (
    create_recon_vehicle_rerun,
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


@router.post("/coverage/{task_id}/rerun", response_model=ReconVehicleCoverageTaskStatus, status_code=status.HTTP_202_ACCEPTED)
def rerun_coverage_task(task_id: str, background_tasks: BackgroundTasks, idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)]) -> ReconVehicleCoverageTaskStatus:
    try:
        original = get_recon_vehicle_task(task_id)
        if original.request is None:
            raise AppError("TASK_REQUEST_UNAVAILABLE", "Saved request is unavailable.", status_code=409)
        read_dem_metadata(original.request.dem_id)
        find_dem_file(original.request.dem_id)
        task, created = create_recon_vehicle_rerun(task_id, original.request, idempotency_key)
        if created:
            background_tasks.add_task(run_recon_vehicle_task, task.task_id, original.request)
        return task
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
        return get_recon_vehicle_task(task_id).output_files
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/coverage/{task_id}/outputs/{kind}")
def download_coverage_output(task_id: str, kind: str) -> FileResponse:
    try:
        task = get_recon_vehicle_task(task_id)
        path, info = get_artifact_store().resolve_download(
            task_id, kind, get_output_contract("recon_vehicle"), computation_status=task.status
        )
        return FileResponse(path, media_type=info.media_type, filename=info.filename)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.delete("/coverage/{task_id}", response_model=ReconVehicleCoverageTaskDeleteResult)
def delete_coverage_task(task_id: str) -> ReconVehicleCoverageTaskDeleteResult:
    try:
        return delete_recon_vehicle_task(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc
