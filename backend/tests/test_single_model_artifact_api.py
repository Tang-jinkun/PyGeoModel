import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


MODEL_CASES = (
    ("uav_task_missing", "/api/uav/recon", "visible_geojson"),
    ("watchpost_task_missing", "/api/watchpost/detection", "visible_geojson"),
    ("artillery_task_missing", "/api/artillery/coverage", "reachable_geojson"),
    ("recon_vehicle_task_missing", "/api/recon-vehicle/coverage", "visible_geojson"),
    ("mobility_task_missing", "/api/mobility/accessibility", "wheeled_path_geojson"),
    ("air_corridor_task_missing", "/api/air-corridor/planning", "corridor_path_geojson"),
)


@pytest.mark.parametrize(("task_id", "base_route", "kind"), MODEL_CASES)
def test_finished_single_model_task_without_artifacts_is_unavailable(
    tmp_path: Path,
    task_id: str,
    base_route: str,
    kind: str,
) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    _write_finished_task(tmp_path, task_id)

    detail = TestClient(app).get(f"{base_route}/{task_id}")
    download = TestClient(app).get(f"{base_route}/{task_id}/outputs/{kind}")

    assert detail.status_code == 200
    assert detail.json()["result_state"] == "unavailable"
    assert detail.json()["result_reason_code"] == "ARTIFACT_DIRECTORY_MISSING"
    assert download.status_code == 410
    assert download.json()["detail"]["code"] == "ARTIFACT_DIRECTORY_MISSING"


@pytest.mark.parametrize(("task_id", "base_route", "kind"), MODEL_CASES)
def test_single_model_rerun_requires_idempotency_key(
    tmp_path: Path,
    task_id: str,
    base_route: str,
    kind: str,
) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    _write_finished_task(tmp_path, task_id)

    response = TestClient(app).post(f"{base_route}/{task_id}/rerun")

    assert response.status_code == 422


def _write_finished_task(root: Path, task_id: str) -> None:
    path = root / "tasks" / f"{task_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "task": {
                    "task_id": task_id,
                    "dem_id": "dem_a",
                    "status": "finished",
                    "progress": 100,
                    "message": "finished",
                    "warnings": [],
                }
            }
        ),
        encoding="utf-8",
    )
