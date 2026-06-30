from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import FileResponse

from app.core.errors import AppError
from app.schemas.air_corridor import (
    AirCorridorOutputFile,
    AirCorridorOutputKind,
    AirCorridorPlanningMetrics,
    AirCorridorPlanningRequest,
    AirCorridorPlanningTaskDeleteResult,
    AirCorridorPlanningTaskStatus,
    AirCorridorPlanningTaskSummary,
)
from app.services.air_corridor_output_files import list_air_corridor_task_output_files, resolve_air_corridor_task_output_path
from app.services.air_corridor_task_store import (
    create_air_corridor_task,
    delete_air_corridor_task,
    get_air_corridor_task,
    list_air_corridor_tasks,
)
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
        background_tasks.add_task(run_air_corridor_task, task.task_id, payload)
        return task
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/planning/{task_id}", response_model=AirCorridorPlanningTaskStatus)
def read_planning_task(task_id: str) -> AirCorridorPlanningTaskStatus:
    try:
        return get_air_corridor_task(task_id)
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
        get_air_corridor_task(task_id)
        return list_air_corridor_task_output_files(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/planning/{task_id}/outputs/{kind}")
def download_planning_output(task_id: str, kind: AirCorridorOutputKind) -> FileResponse:
    try:
        task = get_air_corridor_task(task_id)
        if task.status != "finished":
            raise AppError("TASK_NOT_FINISHED", "Air corridor outputs are available only after the task is finished.", status_code=409)
        path = resolve_air_corridor_task_output_path(task_id, kind)
        if not path.exists():
            raise AppError("OUTPUT_NOT_FOUND", f"Output '{kind}' was not found.", status_code=404)
        info = next(item for item in list_air_corridor_task_output_files(task_id) if item.kind == kind)
        return FileResponse(path, media_type=info.media_type, filename=info.filename)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.delete("/planning/{task_id}", response_model=AirCorridorPlanningTaskDeleteResult)
def delete_planning_task(task_id: str) -> AirCorridorPlanningTaskDeleteResult:
    try:
        return delete_air_corridor_task(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc
