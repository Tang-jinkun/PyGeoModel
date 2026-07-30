from collections.abc import Callable

from app.services.task_scheduler import get_task_scheduler


def enqueue_task(
    task_id: str,
    model_id: str,
    worker: Callable[..., None],
    *args: object,
    on_cancel: Callable[[], None] | None = None,
) -> None:
    get_task_scheduler().enqueue(
        task_id,
        model_id,
        lambda: worker(task_id, *args),
        on_cancel=on_cancel,
    )
