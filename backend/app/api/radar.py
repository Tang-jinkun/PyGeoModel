from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.core.errors import AppError
from app.schemas.radar import (
    CoverageMetrics,
    CoverageOutputFile,
    CoverageProfileBatchRequest,
    CoverageProfileBatchResult,
    CoverageProfileResult,
    CoverageRequest,
    CoverageTaskStatus,
    FusionRequest,
    FusionResult,
    MultiRadarRequest,
    MultiRadarTaskStatus,
    RadarTaskCreateRequest,
    RadarTaskDeleteResult,
    RadarTaskStatus,
    RadarTaskSummary,
    RadarTaskTargetEvaluation,
    SingleRadarTaskRequest,
    TargetEvaluationRequest,
    TargetEvaluationResult,
)
from app.services.artifact_contracts import get_output_contract
from app.services.artifact_store import get_artifact_store
from app.services.coverage_model import validate_coverage_extent
from app.services.dem_store import find_dem_file, read_dem_metadata
from app.services.fusion_analysis import analyze_fusion
from app.services.multi_radar_dem import station_coverage_request
from app.services.multi_radar_target_evaluation import evaluate_multi_radar_target
from app.services.multi_radar_task_store import (
    create_multi_rerun,
    create_multi_task,
    delete_multi_task,
    get_multi_task,
    list_multi_tasks,
    mark_multi_failed,
)
from app.services.profile_analysis import analyze_coverage_profile, analyze_coverage_profiles
from app.services.task_dispatch import enqueue_task
from app.services.task_scheduler import TaskScheduleSnapshot, get_task_scheduler
from app.services.task_store import create_rerun, create_task, delete_task, get_task, list_tasks, mark_failed
from app.services.target_evaluation import evaluate_coverage_target
from app.workers.coverage_task import run_coverage_task
from app.workers.multi_radar_coverage_task import run_multi_radar_coverage_task

router = APIRouter()
RadarTaskKind = Literal["single", "multi"]


def _task_kind(task_id: str) -> RadarTaskKind:
    if task_id.startswith("multi_task_"):
        return "multi"
    if task_id.startswith("task_"):
        return "single"
    raise AppError("INVALID_TASK_ID", "Task id contains unsupported characters.", status_code=400)


def _read_task(task_id: str) -> tuple[RadarTaskKind, CoverageTaskStatus | MultiRadarTaskStatus]:
    kind = _task_kind(task_id)
    if kind == "single":
        return kind, get_task(task_id)
    return kind, get_multi_task(task_id)


def _unified_task(
    kind: RadarTaskKind,
    task: CoverageTaskStatus | MultiRadarTaskStatus,
) -> RadarTaskStatus:
    return RadarTaskStatus.model_validate({"task_type": kind, **task.model_dump()})


def _unified_summary(
    kind: RadarTaskKind,
    task: CoverageTaskStatus | MultiRadarTaskStatus,
) -> RadarTaskSummary:
    data = task.model_dump(exclude={"request"})
    return RadarTaskSummary.model_validate({"task_type": kind, **data})


def _to_single_request(payload: SingleRadarTaskRequest) -> CoverageRequest:
    return CoverageRequest.model_validate(payload.model_dump(exclude={"task_type"}))


def _validate_single_request(payload: CoverageRequest) -> None:
    read_dem_metadata(payload.dem_id)
    validate_coverage_extent(find_dem_file(payload.dem_id), payload)


def _validate_multi_request(payload: MultiRadarRequest) -> None:
    read_dem_metadata(payload.dem_id)
    source = find_dem_file(payload.dem_id)
    for station in payload.radars:
        validate_coverage_extent(source, station_coverage_request(payload.dem_id, station))


def _http_error(exc: AppError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.as_detail())


@router.get("/tasks", response_model=list[RadarTaskSummary])
def list_radar_tasks(
    task_type: Annotated[RadarTaskKind | None, Query()] = None,
) -> list[RadarTaskSummary]:
    tasks: list[RadarTaskSummary] = []
    if task_type in (None, "single"):
        tasks.extend(_unified_summary("single", task) for task in list_tasks())
    if task_type in (None, "multi"):
        tasks.extend(_unified_summary("multi", task) for task in list_multi_tasks())
    return sorted(tasks, key=lambda item: item.created_at or item.task_id, reverse=True)


@router.post("/tasks", response_model=RadarTaskStatus, status_code=status.HTTP_202_ACCEPTED)
def create_radar_task(payload: RadarTaskCreateRequest, background_tasks: BackgroundTasks) -> RadarTaskStatus:
    try:
        if isinstance(payload, SingleRadarTaskRequest):
            request = _to_single_request(payload)
            _validate_single_request(request)
            task = create_task(request)
            background_tasks.add_task(
                enqueue_task,
                task.task_id,
                "radar",
                run_coverage_task,
                request,
                on_cancel=lambda: mark_failed(task.task_id, "Task cancelled by user."),
            )
            return _unified_task("single", task)

        request = MultiRadarRequest.model_validate(payload.model_dump(exclude={"task_type"}))
        _validate_multi_request(request)
        task = create_multi_task(request)
        background_tasks.add_task(
            enqueue_task,
            task.task_id,
            "multi_radar",
            run_multi_radar_coverage_task,
            request,
            on_cancel=lambda: mark_multi_failed(task.task_id, "Task cancelled by user."),
        )
        return _unified_task("multi", task)
    except AppError as exc:
        raise _http_error(exc) from exc


@router.get("/tasks/{task_id}", response_model=RadarTaskStatus)
def read_radar_task(task_id: str) -> RadarTaskStatus:
    try:
        kind, task = _read_task(task_id)
        return _unified_task(kind, task)
    except AppError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/tasks/{task_id}/rerun",
    response_model=RadarTaskStatus,
    status_code=status.HTTP_202_ACCEPTED,
)
def rerun_radar_task(
    task_id: str,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> RadarTaskStatus:
    try:
        kind, original = _read_task(task_id)
        if original.request is None:
            raise AppError("TASK_REQUEST_UNAVAILABLE", "Saved request is unavailable.", status_code=409)
        if kind == "single":
            request = original.request
            read_dem_metadata(request.dem_id)
            task, created = create_rerun(task_id, request, idempotency_key)
            if created:
                background_tasks.add_task(
                    enqueue_task,
                    task.task_id,
                    "radar",
                    run_coverage_task,
                    request,
                    on_cancel=lambda: mark_failed(task.task_id, "Task cancelled by user."),
                )
        else:
            request = original.request
            _validate_multi_request(request)
            task, created = create_multi_rerun(task_id, request, idempotency_key)
            if created:
                background_tasks.add_task(
                    enqueue_task,
                    task.task_id,
                    "multi_radar",
                    run_multi_radar_coverage_task,
                    request,
                    on_cancel=lambda: mark_multi_failed(task.task_id, "Task cancelled by user."),
                )
        return _unified_task(kind, task)
    except AppError as exc:
        raise _http_error(exc) from exc


@router.delete("/tasks/{task_id}", response_model=RadarTaskDeleteResult)
def delete_radar_task(task_id: str) -> RadarTaskDeleteResult:
    try:
        if _task_kind(task_id) == "single":
            result = delete_task(task_id)
            return RadarTaskDeleteResult.model_validate(result.model_dump())
        deleted_record, deleted_outputs, errors = delete_multi_task(task_id)
        return RadarTaskDeleteResult(
            task_id=task_id,
            deleted_task_record=deleted_record,
            deleted_output_dir=deleted_outputs,
            errors=errors,
        )
    except AppError as exc:
        raise _http_error(exc) from exc


@router.get("/tasks/{task_id}/outputs", response_model=list[CoverageOutputFile])
def list_radar_task_outputs(task_id: str) -> list:
    try:
        _, task = _read_task(task_id)
        return task.output_files
    except AppError as exc:
        raise _http_error(exc) from exc


@router.get("/tasks/{task_id}/outputs/{kind}")
def download_radar_task_output(task_id: str, kind: str) -> FileResponse:
    try:
        task_kind, task = _read_task(task_id)
        path, info = get_artifact_store().resolve_download(
            task_id,
            kind,
            get_output_contract("radar" if task_kind == "single" else "multi_radar"),
            computation_status=task.status,
        )
        return FileResponse(path, media_type=info.media_type, filename=info.filename)
    except AppError as exc:
        raise _http_error(exc) from exc


@router.post("/tasks/{task_id}/evaluate-target", response_model=RadarTaskTargetEvaluation)
def evaluate_radar_task_target(
    task_id: str,
    payload: TargetEvaluationRequest,
) -> RadarTaskTargetEvaluation:
    try:
        task_kind = _task_kind(task_id)
        if task_kind == "single":
            detail = TargetEvaluationResult.model_validate(evaluate_coverage_target(task_id, payload))
            return RadarTaskTargetEvaluation(
                task_id=task_id,
                task_type="single",
                detected=detail.detectable,
                detail=detail,
            )
        result = evaluate_multi_radar_target(task_id, payload)
        return RadarTaskTargetEvaluation.model_validate({"task_type": "multi", **result})
    except AppError as exc:
        raise _http_error(exc) from exc


@router.post("/tasks/{task_id}/cancel", response_model=TaskScheduleSnapshot)
def cancel_radar_task(task_id: str) -> TaskScheduleSnapshot:
    try:
        _task_kind(task_id)
    except AppError as exc:
        raise _http_error(exc) from exc
    snapshot = get_task_scheduler().snapshot(task_id)
    if snapshot is None:
        raise HTTPException(
            status_code=409,
            detail={"code": "TASK_NOT_ACTIVE", "message": "Task is not queued or running in this service."},
        )
    get_task_scheduler().request_cancel(task_id)
    return get_task_scheduler().snapshot(task_id) or snapshot


@router.get("/tasks/{task_id}/metrics", response_model=CoverageMetrics)
def read_radar_task_metrics(task_id: str) -> CoverageMetrics:
    try:
        kind, task = _read_task(task_id)
        if kind != "single":
            raise AppError("TASK_VARIANT_UNSUPPORTED", "Metrics are only available for single-radar tasks.", status_code=409)
        if task.status != "finished" or task.metrics is None:
            raise AppError("TASK_METRICS_NOT_READY", "Coverage metrics are available only after the task is finished.", status_code=409)
        return task.metrics
    except AppError as exc:
        raise _http_error(exc) from exc


@router.get("/tasks/{task_id}/profile", response_model=CoverageProfileResult)
def read_radar_task_profile(task_id: str, lon: float, lat: float, samples: int = 160) -> CoverageProfileResult:
    try:
        if _task_kind(task_id) != "single":
            raise AppError("TASK_VARIANT_UNSUPPORTED", "Profiles are only available for single-radar tasks.", status_code=409)
        return analyze_coverage_profile(task_id, lon, lat, samples=samples)
    except AppError as exc:
        raise _http_error(exc) from exc


@router.post("/tasks/{task_id}/profiles", response_model=CoverageProfileBatchResult)
def read_radar_task_profiles(task_id: str, payload: CoverageProfileBatchRequest) -> CoverageProfileBatchResult:
    try:
        if _task_kind(task_id) != "single":
            raise AppError("TASK_VARIANT_UNSUPPORTED", "Profiles are only available for single-radar tasks.", status_code=409)
        return analyze_coverage_profiles(task_id, payload)
    except AppError as exc:
        raise _http_error(exc) from exc


@router.get("/tasks/{task_id}/radars")
def list_radar_task_stations(task_id: str) -> list:
    try:
        kind, task = _read_task(task_id)
        if kind != "multi":
            raise AppError("TASK_VARIANT_UNSUPPORTED", "Station details are only available for multi-radar tasks.", status_code=409)
        return task.stations
    except AppError as exc:
        raise _http_error(exc) from exc


@router.get("/tasks/{task_id}/radars/{radar_id}")
def read_radar_task_station(task_id: str, radar_id: str):
    try:
        kind, task = _read_task(task_id)
        if kind != "multi":
            raise AppError("TASK_VARIANT_UNSUPPORTED", "Station details are only available for multi-radar tasks.", status_code=409)
        for station in task.stations:
            if station.radar_id == radar_id:
                return station
        raise AppError("MULTI_RADAR_NOT_FOUND", f"Radar '{radar_id}' was not found.", status_code=404)
    except AppError as exc:
        raise _http_error(exc) from exc


@router.post("/tasks/{task_id}/radars/{radar_id}/detail", response_model=RadarTaskStatus, status_code=status.HTTP_202_ACCEPTED)
def create_radar_station_detail(task_id: str, radar_id: str, background_tasks: BackgroundTasks) -> RadarTaskStatus:
    try:
        kind, multi_task = _read_task(task_id)
        if kind != "multi":
            raise AppError("TASK_VARIANT_UNSUPPORTED", "Station details are only available for multi-radar tasks.", status_code=409)
        if multi_task.request is None:
            raise AppError("TASK_WITHOUT_REQUEST", "Multi-radar task request is unavailable.", status_code=409)
        station = next((item for item in multi_task.request.radars if item.radar_id == radar_id), None)
        if station is None:
            raise AppError("MULTI_RADAR_NOT_FOUND", f"Radar '{radar_id}' was not found.", status_code=404)
        request = station_coverage_request(multi_task.dem_id, station)
        task = create_task(request)
        background_tasks.add_task(
            enqueue_task,
            task.task_id,
            "radar",
            run_coverage_task,
            request,
            on_cancel=lambda: mark_failed(task.task_id, "Task cancelled by user."),
        )
        return _unified_task("single", task)
    except AppError as exc:
        raise _http_error(exc) from exc


@router.post("/fusion", response_model=FusionResult)
def create_fusion_analysis(payload: FusionRequest) -> FusionResult:
    try:
        return analyze_fusion(payload)
    except AppError as exc:
        raise _http_error(exc) from exc
