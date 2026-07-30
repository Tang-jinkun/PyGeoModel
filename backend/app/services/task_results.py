from typing import TypeVar

from app.services.artifact_contracts import OutputContract
from app.services.artifact_store import ArtifactStore
from app.services.task_scheduler import get_task_scheduler


TaskT = TypeVar("TaskT")


def apply_live_result(task: TaskT, contract: OutputContract, store: ArtifactStore) -> TaskT:
    availability = store.inspect(
        task.task_id,
        contract,
        computation_status=task.status,
    )
    task.result_state = availability.state
    task.result_reason_code = availability.reason_code
    task.output_files = store.list_descriptors(task.task_id, contract)
    schedule = get_task_scheduler().snapshot(task.task_id)
    if schedule is not None:
        task.execution_state = schedule.state
        task.queue_position = schedule.queue_position
        task.estimated_wait_seconds = schedule.estimated_wait_seconds
        task.estimated_run_seconds = schedule.estimated_run_seconds
        task.cancel_requested = schedule.cancel_requested
    return task
