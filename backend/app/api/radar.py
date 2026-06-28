from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.core.errors import AppError
from app.schemas.radar import CoverageRequest, CoverageTaskStatus
from app.services.task_store import create_task, get_task
from app.workers.coverage_task import run_coverage_task

router = APIRouter()


@router.post("/coverage", response_model=CoverageTaskStatus, status_code=status.HTTP_202_ACCEPTED)
def create_coverage_task(payload: CoverageRequest, background_tasks: BackgroundTasks) -> CoverageTaskStatus:
    try:
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
