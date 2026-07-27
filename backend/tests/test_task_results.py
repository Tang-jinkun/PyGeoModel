from pathlib import Path

from app.schemas.artifacts import ArtifactDescriptor
from app.schemas.radar import CoverageMetrics, CoverageOutputFile, CoverageTaskStatus, MultiRadarTaskStatus
from app.services.artifact_contracts import get_output_contract
from app.services.artifact_store import ArtifactStore
from app.services.task_results import apply_live_result


def test_finished_task_ignores_stale_persisted_exists_flag(tmp_path: Path) -> None:
    task = CoverageTaskStatus(
        task_id="task_stale",
        status="finished",
        progress=100,
        message="finished",
        metrics=CoverageMetrics(visible_area_m2=123),
        output_files=[
            CoverageOutputFile(
                kind="visible_geojson",
                label="Visible",
                filename="visible.geojson",
                media_type="application/geo+json",
                exists=True,
                size_bytes=42,
                url="/outputs/task_stale/visible.geojson",
                download_url="/api/radar/coverage/task_stale/outputs/visible_geojson",
            )
        ],
    )

    live = apply_live_result(
        task,
        get_output_contract("radar"),
        ArtifactStore(tmp_path / "outputs"),
    )

    assert live.result_state == "unavailable"
    assert live.result_reason_code == "ARTIFACT_DIRECTORY_MISSING"
    assert all(item.exists is False for item in live.output_files)
    assert all(item.size_bytes is None and item.download_path is None for item in live.output_files)
    assert live.metrics.visible_area_m2 == 123


def test_pending_task_has_pending_result_and_no_download_paths(tmp_path: Path) -> None:
    task = CoverageTaskStatus(
        task_id="task_pending",
        status="pending",
        progress=0,
        message="queued",
    )

    live = apply_live_result(
        task,
        get_output_contract("radar"),
        ArtifactStore(tmp_path / "outputs"),
    )

    assert live.result_state == "pending"
    assert live.result_reason_code is None
    assert all(item.download_path is None for item in live.output_files)


def test_task_schemas_use_shared_descriptors_and_result_fields() -> None:
    radar = CoverageTaskStatus(
        task_id="task_schema",
        status="pending",
        progress=0,
        message="queued",
        rerun_of="task_original",
        output_files=[
            {
                "kind": "height_visible_0",
                "label": "Height layer",
                "filename": "visible_h_0.geojson",
                "media_type": "application/geo+json",
                "exists": False,
            }
        ],
    )
    multi = MultiRadarTaskStatus(
        task_id="multi_task_schema",
        dem_id="dem_a",
        status="pending",
        output_files=[],
    )

    assert radar.rerun_of == "task_original"
    assert radar.result_state == "pending"
    assert isinstance(radar.output_files[0], ArtifactDescriptor)
    assert multi.result_state == "pending"
    assert multi.output_files == []
