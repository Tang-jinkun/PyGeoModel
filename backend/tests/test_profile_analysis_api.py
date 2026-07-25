import json
from pathlib import Path

import numpy
import pytest
import rasterio
from fastapi.testclient import TestClient
from pydantic import ValidationError
from rasterio.transform import from_origin

from app.core.config import settings
from app.main import app
from app.schemas.radar import CoverageProfileBatchRequest
from app.services.dem_store import read_dem_metadata
from app.services.profile_analysis import analyze_coverage_profile, analyze_coverage_profiles


def test_profile_batch_request_accepts_valid_targets() -> None:
    payload = CoverageProfileBatchRequest.model_validate(
        {
            "targets": [
                {"id": "T001", "lon": 105.010, "lat": 35.000},
                {"lon": 105.011, "lat": 35.001},
            ],
            "samples": 12,
            "include_samples": True,
        }
    )

    assert len(payload.targets) == 2
    assert payload.targets[0].id == "T001"
    assert payload.targets[1].id is None
    assert payload.samples == 12
    assert payload.include_samples is True


def test_profile_batch_request_rejects_empty_targets() -> None:
    with pytest.raises(ValidationError):
        CoverageProfileBatchRequest.model_validate({"targets": []})


def test_profile_batch_request_rejects_more_than_500_targets() -> None:
    with pytest.raises(ValidationError):
        CoverageProfileBatchRequest.model_validate(
            {
                "targets": [
                    {"lon": 105.0 + index * 0.00001, "lat": 35.0}
                    for index in range(501)
                ]
            }
        )


def test_read_coverage_profile_reports_terrain_obstruction(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    dem_path = write_profile_dem(tmp_path, "dem_a")
    metadata = read_dem_metadata("dem_a", dem_path)
    (tmp_path / "dem" / "dem_a" / "metadata.json").write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
    write_finished_task(tmp_path, "task_a")

    response = TestClient(app).get("/api/radar/coverage/task_a/profile?lon=105.010&lat=35.000&samples=80")

    assert response.status_code == 200
    payload = response.json()
    assert payload["blocked"] is True
    assert payload["reason"] == "地形遮挡"
    assert payload["obstruction_distance_m"] > 0
    assert payload["obstruction_clearance_m"] < 0
    assert payload["required_height_delta_m"] > 0
    assert len(payload["samples"]) == 80


def test_analyze_coverage_profiles_returns_compact_results(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    dem_path = write_profile_dem(tmp_path, "dem_a")
    metadata = read_dem_metadata("dem_a", dem_path)
    (tmp_path / "dem" / "dem_a" / "metadata.json").write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
    write_finished_task(tmp_path, "task_a")

    result = analyze_coverage_profiles(
        "task_a",
        CoverageProfileBatchRequest.model_validate(
            {
                "targets": [
                    {"id": "T001", "lon": 105.010, "lat": 35.000},
                    {"id": "T002", "lon": 105.004, "lat": 35.000},
                ],
                "samples": 80,
                "include_samples": False,
            }
        ),
    )

    assert result.task_id == "task_a"
    assert result.requested_count == 2
    assert result.succeeded_count == 2
    assert result.failed_count == 0
    assert [item.target_lon for item in result.results] == [105.010, 105.004]
    assert all(item.samples == [] for item in result.results)


def test_analyze_coverage_profiles_can_include_samples(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    dem_path = write_profile_dem(tmp_path, "dem_a")
    metadata = read_dem_metadata("dem_a", dem_path)
    (tmp_path / "dem" / "dem_a" / "metadata.json").write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
    write_finished_task(tmp_path, "task_a")

    result = analyze_coverage_profiles(
        "task_a",
        CoverageProfileBatchRequest.model_validate(
            {
                "targets": [{"id": "T001", "lon": 105.010, "lat": 35.000}],
                "samples": 40,
                "include_samples": True,
            }
        ),
    )

    assert result.succeeded_count == 1
    assert len(result.results[0].samples) == 40


def test_analyze_coverage_profiles_collects_target_errors(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    dem_path = write_profile_dem(tmp_path, "dem_a")
    metadata = read_dem_metadata("dem_a", dem_path)
    (tmp_path / "dem" / "dem_a" / "metadata.json").write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
    write_finished_task(tmp_path, "task_a")

    result = analyze_coverage_profiles(
        "task_a",
        CoverageProfileBatchRequest.model_validate(
            {
                "targets": [
                    {"id": "valid", "lon": 105.010, "lat": 35.000},
                    {"id": "outside", "lon": 106.500, "lat": 35.000},
                ],
                "samples": 40,
            }
        ),
    )

    assert result.requested_count == 2
    assert result.succeeded_count == 1
    assert result.failed_count == 1
    assert result.results[0].target_lon == 105.010
    assert result.errors[0].id == "outside"
    assert result.errors[0].index == 1
    assert result.errors[0].code == "PROFILE_OUTSIDE_DEM"


def test_single_and_batch_profiles_share_core_fields(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    dem_path = write_profile_dem(tmp_path, "dem_a")
    metadata = read_dem_metadata("dem_a", dem_path)
    (tmp_path / "dem" / "dem_a" / "metadata.json").write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
    write_finished_task(tmp_path, "task_a")

    single = analyze_coverage_profile("task_a", 105.010, 35.000, samples=80)
    batch = analyze_coverage_profiles(
        "task_a",
        CoverageProfileBatchRequest.model_validate(
            {
                "targets": [{"id": "same", "lon": 105.010, "lat": 35.000}],
                "samples": 80,
                "include_samples": True,
            }
        ),
    ).results[0]

    assert batch.blocked == single.blocked
    assert batch.reason == single.reason
    assert batch.distance_m == single.distance_m
    assert batch.required_height_delta_m == single.required_height_delta_m
    assert len(batch.samples) == len(single.samples)


def test_read_coverage_profiles_batch_returns_partial_results(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    dem_path = write_profile_dem(tmp_path, "dem_a")
    metadata = read_dem_metadata("dem_a", dem_path)
    (tmp_path / "dem" / "dem_a" / "metadata.json").write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
    write_finished_task(tmp_path, "task_a")

    response = TestClient(app).post(
        "/api/radar/coverage/task_a/profiles",
        json={
            "targets": [
                {"id": "valid", "lon": 105.010, "lat": 35.000},
                {"id": "outside", "lon": 106.500, "lat": 35.000},
            ],
            "samples": 40,
            "include_samples": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == "task_a"
    assert payload["requested_count"] == 2
    assert payload["succeeded_count"] == 1
    assert payload["failed_count"] == 1
    assert payload["results"][0]["samples"] == []
    assert payload["errors"][0]["id"] == "outside"
    assert payload["errors"][0]["code"] == "PROFILE_OUTSIDE_DEM"


def test_read_coverage_profiles_batch_rejects_empty_targets(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()

    response = TestClient(app).post("/api/radar/coverage/task_a/profiles", json={"targets": []})

    assert response.status_code == 422


def write_profile_dem(root: Path, dem_id: str) -> Path:
    dem_dir = root / "dem" / dem_id
    dem_dir.mkdir(parents=True, exist_ok=True)
    path = dem_dir / "profile.tif"
    data = numpy.zeros((120, 120), dtype=numpy.float32)
    data[:, 82:88] = 200
    transform = from_origin(104.988, 35.012, 0.0002, 0.0002)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=data.shape[1],
        height=data.shape[0],
        count=1,
        dtype=data.dtype,
        crs="EPSG:4326",
        transform=transform,
        nodata=-9999,
    ) as dataset:
        dataset.write(data, 1)
    return path


def write_finished_task(root: Path, task_id: str) -> None:
    task_dir = root / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / f"{task_id}.json").write_text(
        json.dumps(
            {
                "task": {
                    "task_id": task_id,
                    "dem_id": "dem_a",
                    "status": "finished",
                    "progress": 100,
                    "message": "finished",
                    "warnings": [],
                },
                "payload": {
                    "dem_id": "dem_a",
                    "radar": {"lon": 105.000, "lat": 35.000, "height_m": 10},
                    "target": {"height_m": 0},
                    "coverage": {
                        "max_range_m": 5000,
                        "scan_mode": "omni",
                        "azimuth_deg": 0,
                        "beam_width_deg": 360,
                    },
                    "advanced": {
                        "min_elevation_deg": -10,
                        "max_elevation_deg": 89,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
