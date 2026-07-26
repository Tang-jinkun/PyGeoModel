from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import FileResponse

from app.core.errors import AppError
from app.schemas.radar import (
    CoverageMetrics,
    CoverageOutputFile,
    CoverageOutputKind,
    CoverageProfileResult,
    CoverageRequest,
    CoverageTaskDeleteResult,
    CoverageTaskStatus,
    CoverageTaskSummary,
    FusionRequest,
    FusionResult,
    MultiRadarRequest,
    MultiRadarStation,
    MultiRadarTaskStatus,
    TargetEvaluationRequest,
    TargetEvaluationResult,
)
from app.services.output_files import list_task_output_files, resolve_task_output_path
from app.services.coverage_model import validate_coverage_extent
from app.services.dem_store import find_dem_file, read_dem_metadata
from app.services.fusion_analysis import analyze_fusion
from app.services.profile_analysis import analyze_coverage_profile
from app.services.task_store import create_task, delete_task, get_task, list_tasks
from app.services.multi_radar_dem import station_coverage_request
from app.services.multi_radar_task_store import create_multi_task, get_multi_task, list_multi_tasks
from app.services.multi_radar_target_evaluation import evaluate_multi_radar_target
from app.services.target_evaluation import evaluate_coverage_target
from app.workers.coverage_task import run_coverage_task
from app.workers.multi_radar_coverage_task import run_multi_radar_coverage_task

router = APIRouter()


@router.get("/multi-coverage", response_model=list[MultiRadarTaskStatus])
def list_multi_coverage_tasks() -> list[MultiRadarTaskStatus]:
    return list_multi_tasks()


@router.post("/multi-coverage", response_model=MultiRadarTaskStatus, status_code=status.HTTP_202_ACCEPTED)
def create_multi_coverage_task(payload: MultiRadarRequest, background_tasks: BackgroundTasks) -> MultiRadarTaskStatus:
    try:
        read_dem_metadata(payload.dem_id)
        source = find_dem_file(payload.dem_id)
        for station in payload.radars:
            validate_coverage_extent(source, station_coverage_request(payload.dem_id, station))
        task = create_multi_task(payload)
        background_tasks.add_task(run_multi_radar_coverage_task, task.task_id, payload)
        return task
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/multi-coverage/{task_id}", response_model=MultiRadarTaskStatus)
def read_multi_coverage_task(task_id: str) -> MultiRadarTaskStatus:
    try:
        return get_multi_task(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/multi-coverage/{task_id}/radars")
def list_multi_coverage_stations(task_id: str) -> list:
    try:
        return get_multi_task(task_id).stations
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/multi-coverage/{task_id}/radars/{radar_id}")
def read_multi_coverage_station(task_id: str, radar_id: str):
    try:
        for station in get_multi_task(task_id).stations:
            if station.radar_id == radar_id:
                return station
        raise AppError("MULTI_RADAR_NOT_FOUND", f"Radar '{radar_id}' was not found.", status_code=404)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.post("/multi-coverage/{task_id}/evaluate-target")
def evaluate_multi_target(task_id: str, payload: TargetEvaluationRequest) -> dict:
    try:
        return evaluate_multi_radar_target(task_id, payload)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.post("/multi-coverage/{task_id}/radars/{radar_id}/detail", response_model=CoverageTaskStatus, status_code=status.HTTP_202_ACCEPTED)
def create_multi_station_detail(task_id: str, radar_id: str, background_tasks: BackgroundTasks) -> CoverageTaskStatus:
    try:
        multi_task = get_multi_task(task_id)
        if multi_task.request is None:
            raise AppError("TASK_WITHOUT_REQUEST", "Multi-radar task request is unavailable.", status_code=409)
        station = next((item for item in multi_task.request.radars if item.radar_id == radar_id), None)
        if station is None:
            raise AppError("MULTI_RADAR_NOT_FOUND", f"Radar '{radar_id}' was not found.", status_code=404)
        task = create_task(station_coverage_request(multi_task.dem_id, station))
        background_tasks.add_task(run_coverage_task, task.task_id, task.request)
        return task
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


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


@router.post("/fusion", response_model=FusionResult)
def create_fusion_analysis(payload: FusionRequest) -> FusionResult:
    try:
        return analyze_fusion(payload)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/coverage/{task_id}", response_model=CoverageTaskStatus)
def read_coverage_task(task_id: str) -> CoverageTaskStatus:
    try:
        return get_task(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/coverage/{task_id}/metrics", response_model=CoverageMetrics)
def read_coverage_metrics(task_id: str) -> CoverageMetrics:
    try:
        task = get_task(task_id)
        if task.status != "finished" or task.metrics is None:
            raise AppError("TASK_METRICS_NOT_READY", "Coverage metrics are available only after the task is finished.", status_code=409)
        return task.metrics
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/coverage/{task_id}/profile", response_model=CoverageProfileResult)
def read_coverage_profile(task_id: str, lon: float, lat: float, samples: int = 160) -> CoverageProfileResult:
    try:
        return analyze_coverage_profile(task_id, lon, lat, samples=samples)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.post(
    "/coverage/{task_id}/evaluate-target",
    response_model=TargetEvaluationResult,
)
def evaluate_target(
    task_id: str,
    payload: TargetEvaluationRequest,
) -> TargetEvaluationResult:
    try:
        return evaluate_coverage_target(task_id, payload)
    except AppError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.as_detail(),
        ) from exc


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
