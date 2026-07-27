from typing import TypeVar

from app.services.artifact_contracts import OutputContract
from app.services.artifact_store import ArtifactStore


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
    return task
