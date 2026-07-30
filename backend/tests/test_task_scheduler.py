from threading import Event

from app.services.task_scheduler import TaskScheduler


def test_scheduler_runs_one_job_at_a_time_and_reports_queue_position() -> None:
    scheduler = TaskScheduler(max_concurrent_tasks=1)
    first_started = Event()
    release_first = Event()
    second_started = Event()

    scheduler.enqueue("first", "radar", lambda: (first_started.set(), release_first.wait(2)))
    scheduler.enqueue("second", "uav", second_started.set)

    assert first_started.wait(1)
    assert scheduler.snapshot("second").queue_position == 1
    assert not second_started.is_set()

    release_first.set()
    assert second_started.wait(1)
    scheduler.shutdown(wait=True)


def test_scheduler_cancels_a_queued_job_without_running_it() -> None:
    scheduler = TaskScheduler(max_concurrent_tasks=1)
    first_started = Event()
    release_first = Event()
    cancelled = Event()
    second_started = Event()

    scheduler.enqueue("first", "radar", lambda: (first_started.set(), release_first.wait(2)))
    scheduler.enqueue("second", "uav", second_started.set, on_cancel=cancelled.set)

    assert first_started.wait(1)
    assert scheduler.request_cancel("second") == "cancelled"
    assert cancelled.wait(1)
    assert scheduler.snapshot("second").state == "cancelled"

    release_first.set()
    assert not second_started.wait(0.2)
    scheduler.shutdown(wait=True)
