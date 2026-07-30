from __future__ import annotations

from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from threading import RLock
from time import monotonic
from typing import Callable, Literal

from app.core.config import settings


ScheduleState = Literal["queued", "running", "cancelling", "cancelled", "finished", "failed"]


class TaskCancelled(Exception):
    pass


@dataclass(frozen=True)
class TaskScheduleSnapshot:
    task_id: str
    model_id: str
    state: ScheduleState
    queue_position: int | None
    estimated_wait_seconds: int | None
    estimated_run_seconds: int | None
    cancel_requested: bool


@dataclass
class _ScheduledJob:
    task_id: str
    model_id: str
    run: Callable[[], None]
    on_cancel: Callable[[], None] | None
    state: ScheduleState = "queued"
    cancel_requested: bool = False
    enqueued_at: float = 0.0
    started_at: float | None = None


class TaskScheduler:
    """A bounded, process-local executor for persisted model task records."""

    def __init__(self, *, max_concurrent_tasks: int = 1) -> None:
        if max_concurrent_tasks < 1:
            raise ValueError("max_concurrent_tasks must be at least one")
        self._max_concurrent_tasks = max_concurrent_tasks
        self._executor = ThreadPoolExecutor(max_workers=max_concurrent_tasks, thread_name_prefix="pygeomodel-task")
        self._lock = RLock()
        self._jobs: dict[str, _ScheduledJob] = {}
        self._queue: deque[str] = deque()
        self._active: dict[str, Future[None]] = {}
        self._model_durations: dict[str, list[float]] = {}
        self._closed = False

    def enqueue(
        self,
        task_id: str,
        model_id: str,
        run: Callable[[], None],
        *,
        on_cancel: Callable[[], None] | None = None,
    ) -> TaskScheduleSnapshot:
        with self._lock:
            if self._closed:
                raise RuntimeError("Task scheduler is shut down")
            existing = self._jobs.get(task_id)
            if existing is not None:
                return self._snapshot_locked(existing)
            job = _ScheduledJob(
                task_id=task_id,
                model_id=model_id,
                run=run,
                on_cancel=on_cancel,
                enqueued_at=monotonic(),
            )
            self._jobs[task_id] = job
            self._queue.append(task_id)
            self._dispatch_locked()
            return self._snapshot_locked(job)

    def request_cancel(self, task_id: str) -> ScheduleState | None:
        callback: Callable[[], None] | None = None
        with self._lock:
            job = self._jobs.get(task_id)
            if job is None or job.state in {"finished", "failed", "cancelled"}:
                return None
            job.cancel_requested = True
            if job.state == "queued":
                job.state = "cancelled"
                callback = job.on_cancel
            elif job.state == "running":
                job.state = "cancelling"
            return_state = job.state
        if callback is not None:
            callback()
        return return_state

    def snapshot(self, task_id: str) -> TaskScheduleSnapshot | None:
        with self._lock:
            job = self._jobs.get(task_id)
            return self._snapshot_locked(job) if job else None

    def is_cancel_requested(self, task_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(task_id)
            return bool(job and job.cancel_requested)

    def raise_if_cancel_requested(self, task_id: str) -> None:
        if self.is_cancel_requested(task_id):
            raise TaskCancelled("Task cancellation was requested by the user.")

    def shutdown(self, *, wait: bool = True) -> None:
        with self._lock:
            self._closed = True
        self._executor.shutdown(wait=wait, cancel_futures=False)

    def _dispatch_locked(self) -> None:
        while not self._closed and len(self._active) < self._max_concurrent_tasks and self._queue:
            task_id = self._queue.popleft()
            job = self._jobs.get(task_id)
            if job is None or job.state != "queued":
                continue
            job.state = "running"
            job.started_at = monotonic()
            self._active[task_id] = self._executor.submit(self._run_job, job)

    def _run_job(self, job: _ScheduledJob) -> None:
        failed = False
        try:
            job.run()
        except Exception:
            failed = True
            raise
        finally:
            with self._lock:
                duration = max(0.0, monotonic() - (job.started_at or monotonic()))
                durations = self._model_durations.setdefault(job.model_id, [])
                durations.append(duration)
                del durations[:-12]
                if job.cancel_requested:
                    job.state = "cancelled"
                elif failed:
                    job.state = "failed"
                else:
                    job.state = "finished"
                self._active.pop(job.task_id, None)
                self._dispatch_locked()

    def _snapshot_locked(self, job: _ScheduledJob) -> TaskScheduleSnapshot:
        queue_position = None
        if job.state == "queued":
            queue_position = sum(
                1 for task_id in self._queue
                if (candidate := self._jobs.get(task_id)) is not None and candidate.state == "queued" and task_id != job.task_id
            ) + 1
        estimate = self._estimated_run_seconds(job.model_id)
        wait = None
        if queue_position is not None and estimate is not None:
            wait = estimate * (len(self._active) + queue_position - 1)
        return TaskScheduleSnapshot(
            task_id=job.task_id,
            model_id=job.model_id,
            state=job.state,
            queue_position=queue_position,
            estimated_wait_seconds=wait,
            estimated_run_seconds=estimate,
            cancel_requested=job.cancel_requested,
        )

    def _estimated_run_seconds(self, model_id: str) -> int | None:
        durations = self._model_durations.get(model_id, [])
        if not durations:
            return None
        return max(1, round(sum(durations) / len(durations)))


_scheduler: TaskScheduler | None = None
_scheduler_lock = RLock()


def get_task_scheduler() -> TaskScheduler:
    """Return a live scheduler, recreating it after an application shutdown."""
    global _scheduler
    with _scheduler_lock:
        if _scheduler is None or _scheduler._closed:
            _scheduler = TaskScheduler(max_concurrent_tasks=settings.max_concurrent_tasks)
        return _scheduler
