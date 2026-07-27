import json
from pathlib import Path
from unittest.mock import Mock

from fastapi.testclient import TestClient
import numpy
import rasterio
from rasterio.transform import from_origin

from app.core.config import settings
from app.main import app, create_app
from app.services.dem_store import read_dem_metadata
from app.services.artifact_contracts import get_output_contract
from app.services.artifact_store import ArtifactStore


def test_list_coverage_outputs(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_task(tmp_path, "task_a", "finished")
    publish_radar_outputs(tmp_path, "task_a")

    response = TestClient(app).get("/api/radar/coverage/task_a/outputs")

    assert response.status_code == 200
    payload = response.json()
    visible = next(item for item in payload if item["kind"] == "visible_geojson")
    assert visible["exists"] is True
    assert visible["download_path"] == "/api/radar/coverage/task_a/outputs/visible_geojson"
    assert visible["download_url"] == "/api/radar/coverage/task_a/outputs/visible_geojson"
    assert visible["url"] is None


def test_download_coverage_output(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_task(tmp_path, "task_a", "finished")
    publish_radar_outputs(tmp_path, "task_a", {"model_metadata.json": b'{"ok": true}'})

    response = TestClient(app).get("/api/radar/coverage/task_a/outputs/model_metadata_json")

    assert response.status_code == 200
    assert response.content == b'{"ok": true}'
    assert response.headers["content-type"].startswith("application/json")
    assert "model_metadata.json" in response.headers["content-disposition"]


def test_download_coverage_output_requires_finished_task(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_task(tmp_path, "task_a", "running")

    response = TestClient(app).get("/api/radar/coverage/task_a/outputs/model_metadata_json")

    assert response.status_code == 409


def test_finished_task_with_missing_artifact_directory_is_unavailable(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_task(tmp_path, "task_a", "finished")

    detail = TestClient(app).get("/api/radar/coverage/task_a")
    response = TestClient(app).get("/api/radar/coverage/task_a/outputs/model_metadata_json")

    assert detail.status_code == 200
    assert detail.json()["result_state"] == "unavailable"
    assert detail.json()["result_reason_code"] == "ARTIFACT_DIRECTORY_MISSING"
    assert all(item["download_path"] is None for item in detail.json()["output_files"])
    assert response.status_code == 410
    assert response.json()["detail"]["code"] == "ARTIFACT_DIRECTORY_MISSING"


def test_unknown_output_kind_on_ready_task_returns_not_found(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_task(tmp_path, "task_a", "finished")
    publish_radar_outputs(tmp_path, "task_a")

    response = TestClient(app).get("/api/radar/coverage/task_a/outputs/not_a_kind")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "OUTPUT_KIND_NOT_FOUND"


def test_raw_outputs_are_not_statically_served(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_task(tmp_path, "task_a", "finished")
    publish_radar_outputs(tmp_path, "task_a")

    response = TestClient(create_app()).get("/outputs/task_a/visible.geojson")

    assert response.status_code == 404


def test_rerun_requires_idempotency_key(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_task_with_payload(tmp_path, "task_a", "finished")

    response = TestClient(app).post("/api/radar/coverage/task_a/rerun")

    assert response.status_code == 422


def test_rerun_reuses_child_and_schedules_once(tmp_path: Path, monkeypatch) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_task_with_payload(tmp_path, "task_a", "finished")
    scheduled = Mock()
    monkeypatch.setattr("app.api.radar.read_dem_metadata", lambda *_: None)
    monkeypatch.setattr("app.api.radar.run_coverage_task", scheduled)
    headers = {"Idempotency-Key": "radar-rerun-key"}

    response = TestClient(app).post("/api/radar/coverage/task_a/rerun", headers=headers)
    repeated = TestClient(app).post("/api/radar/coverage/task_a/rerun", headers=headers)

    assert response.status_code == 202
    assert repeated.status_code == 202
    assert response.json()["task_id"] != "task_a"
    assert response.json()["rerun_of"] == "task_a"
    assert repeated.json()["task_id"] == response.json()["task_id"]
    assert scheduled.call_count == 1


def test_reading_history_never_schedules_work(tmp_path: Path, monkeypatch) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_task_with_payload(tmp_path, "task_a", "finished")
    scheduled = Mock()
    monkeypatch.setattr("app.api.radar.run_coverage_task", scheduled)

    response = TestClient(app).get("/api/radar/coverage/task_a")

    assert response.status_code == 200
    scheduled.assert_not_called()


def test_read_coverage_task_includes_request(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_task_with_payload(tmp_path, "task_a", "finished")

    response = TestClient(app).get("/api/radar/coverage/task_a")

    assert response.status_code == 200
    payload = response.json()
    assert payload["request"]["dem_id"] == "dem_a"
    assert payload["request"]["radar"]["lon"] == 105


def test_read_coverage_metrics_returns_json(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_task(tmp_path, "task_a", "finished", metrics={"theoretical_area_m2": 100, "visible_area_m2": 60})

    response = TestClient(app).get("/api/radar/coverage/task_a/metrics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["theoretical_area_m2"] == 100
    assert payload["visible_area_m2"] == 60
    assert payload["requested_theoretical_area_m2"] == 100
    assert payload["unknown_area_m2"] == 0


def test_read_coverage_task_returns_dem_clip_contract(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_task(
        tmp_path,
        "task_a",
        "finished",
        metrics={
            "requested_theoretical_area_m2": 1200,
            "theoretical_area_m2": 1000,
            "unknown_area_m2": 200,
        },
        model={
            "coverage_contract_version": 2,
            "target_epsg": 32648,
            "radar_projected_xy": [0, 0],
            "projected_dem_bounds": [0, 0, 10, 10],
            "projected_dem_resolution_m": [10, 10],
            "max_range_m": 1000,
            "scan_mode": "omni",
            "azimuth_deg": 0,
            "beam_width_deg": 360,
            "simplify_tolerance_m": 10,
            "beam_clip_profile": {"azimuth_step_deg": 2, "radius_m": [1000, 900]},
        },
    )

    response = TestClient(app).get("/api/radar/coverage/task_a")

    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics"]["unknown_area_m2"] == 200
    assert payload["model"]["coverage_contract_version"] == 2
    assert payload["model"]["beam_clip_profile"]["radius_m"] == [1000, 900]


def test_read_legacy_coverage_task_defaults_contract_version(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_task(
        tmp_path,
        "task_legacy",
        "finished",
        model={
            "target_epsg": 32648,
            "radar_projected_xy": [0, 0],
            "projected_dem_bounds": [0, 0, 10, 10],
            "projected_dem_resolution_m": [10, 10],
            "max_range_m": 1000,
            "scan_mode": "omni",
            "azimuth_deg": 0,
            "beam_width_deg": 360,
            "simplify_tolerance_m": 10,
        },
    )

    response = TestClient(app).get("/api/radar/coverage/task_legacy")

    assert response.status_code == 200
    assert response.json()["model"]["coverage_contract_version"] == 1


def test_list_coverage_tasks_omits_request(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_task_with_payload(tmp_path, "task_a", "finished")

    response = TestClient(app).get("/api/radar/coverage")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["task_id"] == "task_a"
    assert "request" not in payload[0]


def test_create_app_recovers_interrupted_tasks(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_task(tmp_path, "task_a", "running")

    response = TestClient(create_app()).get("/api/radar/coverage/task_a")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["progress"] == 100
    assert "interrupted" in payload["message"]


def test_list_coverage_tasks_skips_corrupt_record(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_task_with_payload(tmp_path, "task_a", "finished")
    corrupt_path = tmp_path / "tasks" / "task_bad.json"
    corrupt_path.write_text("{", encoding="utf-8")

    response = TestClient(app).get("/api/radar/coverage")

    assert response.status_code == 200
    payload = response.json()
    assert [item["task_id"] for item in payload] == ["task_a"]
    assert not corrupt_path.exists()
    assert list((tmp_path / "tasks").glob("task_bad.json*.corrupt"))


def test_read_coverage_task_reports_corrupt_record(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    corrupt_path = tmp_path / "tasks" / "task_bad.json"
    corrupt_path.write_text("{", encoding="utf-8")

    response = TestClient(app).get("/api/radar/coverage/task_bad")

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "TASK_RECORD_CORRUPT"
    assert not corrupt_path.exists()
    assert list((tmp_path / "tasks").glob("task_bad.json*.corrupt"))


def test_delete_coverage_task_api(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_task(tmp_path, "task_a", "finished")
    output_dir = tmp_path / "outputs" / "task_a"
    output_dir.mkdir(parents=True)
    (output_dir / "visible.geojson").write_text("{}", encoding="utf-8")

    response = TestClient(app).delete("/api/radar/coverage/task_a")

    assert response.status_code == 200
    payload = response.json()
    assert payload["deleted_task_record"] is True
    assert payload["deleted_output_dir"] is True
    assert not output_dir.exists()


def test_delete_coverage_task_is_retry_safe(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_task(tmp_path, "task_a", "finished")

    first = TestClient(app).delete("/api/radar/coverage/task_a")
    second = TestClient(app).delete("/api/radar/coverage/task_a")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == {
        "task_id": "task_a",
        "deleted_task_record": False,
        "deleted_output_dir": False,
        "errors": [],
    }


def test_delete_coverage_task_api_rejects_running(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_task(tmp_path, "task_a", "running")

    response = TestClient(app).delete("/api/radar/coverage/task_a")

    assert response.status_code == 409


def test_delete_coverage_task_api_rejects_invalid_id(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()

    response = TestClient(app).delete("/api/radar/coverage/..%5Ctask_a")

    assert response.status_code == 400


def test_create_coverage_task_rejects_range_mostly_outside_dem(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    dem_dir = tmp_path / "dem" / "dem_small"
    dem_dir.mkdir(parents=True)
    dem_path = dem_dir / "small.tif"
    data = numpy.zeros((50, 50), dtype=numpy.float32)
    with rasterio.open(
        dem_path,
        "w",
        driver="GTiff",
        width=50,
        height=50,
        count=1,
        dtype=data.dtype,
        crs="EPSG:4326",
        transform=from_origin(104.975, 35.025, 0.001, 0.001),
        nodata=-9999,
    ) as dataset:
        dataset.write(data, 1)
    metadata = read_dem_metadata("dem_small", dem_path)
    (dem_dir / "metadata.json").write_text(metadata.model_dump_json(indent=2), encoding="utf-8")

    response = TestClient(app).post(
        "/api/radar/coverage",
        json={
            "dem_id": "dem_small",
            "radar": {"lon": 105.0, "lat": 35.0, "height_m": 10},
            "target": {"height_m": 0},
            "coverage": {
                "max_range_m": 50_000,
                "scan_mode": "omni",
                "azimuth_deg": 0,
                "beam_width_deg": 360,
            },
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "RANGE_OUTSIDE_DEM"


def write_task(
    root: Path,
    task_id: str,
    status: str,
    metrics: dict | None = None,
    model: dict | None = None,
) -> None:
    task_dir = root / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    task = {
        "task_id": task_id,
        "dem_id": "dem_a",
        "status": status,
        "progress": 100 if status == "finished" else 50,
        "message": status,
        "warnings": [],
    }
    if metrics is not None:
        task["metrics"] = metrics
    if model is not None:
        task["model"] = model
    (task_dir / f"{task_id}.json").write_text(json.dumps({"task": task}), encoding="utf-8")


def write_task_with_payload(root: Path, task_id: str, status: str) -> None:
    task_dir = root / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / f"{task_id}.json").write_text(
        json.dumps(
            {
                "task": {
                    "task_id": task_id,
                    "dem_id": "dem_a",
                    "status": status,
                    "progress": 100,
                    "message": status,
                    "warnings": [],
                },
                "payload": {
                    "dem_id": "dem_a",
                    "radar": {"lon": 105, "lat": 35, "height_m": 10},
                    "target": {"height_m": 0},
                    "coverage": {
                        "max_range_m": 1000,
                        "scan_mode": "omni",
                        "azimuth_deg": 0,
                        "beam_width_deg": 360,
                    },
                },
            }
        ),
        encoding="utf-8",
    )


def publish_radar_outputs(root: Path, task_id: str, overrides: dict[str, bytes] | None = None) -> None:
    store = ArtifactStore(root / "outputs")
    contract = get_output_contract("radar")
    staging = store.create_staging_dir(task_id)
    overrides = overrides or {}
    for spec in contract.artifacts:
        (staging / spec.filename).write_bytes(overrides.get(spec.filename, b"{}"))
    store.publish(task_id, contract, staging)
