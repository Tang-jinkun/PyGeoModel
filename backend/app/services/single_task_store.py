from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TypeVar
from uuid import uuid4

from pydantic import BaseModel

from app.core.errors import AppError
from app.services.artifact_contracts import get_output_contract
from app.services.artifact_store import get_artifact_store
from app.services.task_results import apply_live_result


TaskT = TypeVar("TaskT", bound=BaseModel)


def create_idempotent_rerun(
    *,
    original_task_id: str,
    payload: BaseModel,
    idempotency_key: str,
    task_id_prefix: str,
    record_paths: list[Path],
    task_type: type[TaskT],
    task_path: Callable[[str], Path],
    read_record: Callable[[Path], dict],
    write_record: Callable[[Path, dict], None],
    get_task: Callable[[str], TaskT],
) -> tuple[TaskT, bool]:
    for path in record_paths:
        try:
            data = read_record(path)
        except AppError:
            continue
        rerun = data.get("rerun")
        if isinstance(rerun, dict) and rerun.get("of") == original_task_id and rerun.get(
            "idempotency_key"
        ) == idempotency_key:
            return get_task(path.stem), False

    now = datetime.now(timezone.utc).isoformat()
    task_id = (
        f"{task_id_prefix}{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_"
        f"{uuid4().hex[:8]}"
    )
    task = task_type(
        task_id=task_id,
        dem_id=getattr(payload, "dem_id"),
        status="pending",
        progress=0,
        message="queued",
        created_at=now,
        updated_at=now,
        request=payload,
        rerun_of=original_task_id,
    )
    write_record(
        task_path(task_id),
        {
            "task": task.model_dump(exclude={"request"}),
            "payload": payload.model_dump(),
            "rerun": {"of": original_task_id, "idempotency_key": idempotency_key},
        },
    )
    return task, True


def preserve_rerun_metadata(
    data: dict,
    path: Path,
    read_record: Callable[[Path], dict],
) -> None:
    if not path.exists():
        return
    rerun = read_record(path).get("rerun")
    if rerun is not None:
        data["rerun"] = rerun


def hydrate_task(task: TaskT, model_id: str) -> TaskT:
    return apply_live_result(task, get_output_contract(model_id), get_artifact_store())


def delete_task_resources(task_id: str, task_path: Path) -> tuple[bool, bool, list[str]]:
    deleted_task_record = False
    deleted_output_dir = False
    errors: list[str] = []
    try:
        if task_path.exists():
            task_path.unlink()
            deleted_task_record = True
    except OSError as exc:
        errors.append(f"task_record: {exc}")
    try:
        deleted_output_dir = get_artifact_store().delete(task_id)
    except OSError as exc:
        errors.append(f"artifact_directory: {exc}")
    return deleted_task_record, deleted_output_dir, errors
