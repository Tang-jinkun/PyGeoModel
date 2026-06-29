import json
from pathlib import Path

import numpy
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_origin

from app.core.config import settings
from app.main import app
from app.services.dem_store import read_dem_metadata


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
