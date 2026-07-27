from pathlib import Path

from app.core.config import settings
from app.schemas.air_corridor import AirCorridorPlanningRequest
from app.services.air_corridor_task_store import (
    create_air_corridor_task,
    get_air_corridor_task,
    mark_air_corridor_failed,
    recover_interrupted_air_corridor_tasks,
)


def test_recovery_removes_only_interrupted_task_staging_directories(
    tmp_path: Path,
) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    interrupted = create_air_corridor_task(request())
    other = create_air_corridor_task(request())
    mark_air_corridor_failed(other.task_id, "already failed")

    first_stage = stage_dir(tmp_path, interrupted.task_id, "first")
    second_stage = stage_dir(tmp_path, interrupted.task_id, "second")
    other_stage = stage_dir(tmp_path, other.task_id, "other")
    unrelated_hidden = tmp_path / "outputs" / ".unrelated-cache"
    near_match = tmp_path / "outputs" / f".{interrupted.task_id}.staging"
    matching_file = (
        tmp_path / "outputs" / f".{interrupted.task_id}.staging-file"
    )
    final_output = tmp_path / "outputs" / interrupted.task_id
    for directory in (unrelated_hidden, near_match, final_output):
        directory.mkdir()
    matching_file.write_text("not a directory", encoding="utf-8")

    recovered = recover_interrupted_air_corridor_tasks()

    assert recovered == 1
    assert get_air_corridor_task(interrupted.task_id).status == "failed"
    assert not first_stage.exists()
    assert not second_stage.exists()
    assert other_stage.exists()
    assert unrelated_hidden.exists()
    assert near_match.exists()
    assert matching_file.exists()
    assert final_output.exists()


def request() -> AirCorridorPlanningRequest:
    return AirCorridorPlanningRequest(
        dem_id="dem_a",
        start={"lon": 79.8, "lat": 31.48, "altitude_m": 300},
        end={"lon": 79.81, "lat": 31.48, "altitude_m": 300},
        altitude_layers_m=[300],
        threats=[],
    )


def stage_dir(root: Path, task_id: str, suffix: str) -> Path:
    path = root / "outputs" / f".{task_id}.staging-{suffix}"
    path.mkdir()
    (path / "partial.txt").write_text("partial", encoding="utf-8")
    return path
