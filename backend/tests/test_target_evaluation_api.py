import json
from pathlib import Path

import numpy
import rasterio
from fastapi.testclient import TestClient
from pyproj import Transformer
from rasterio.transform import from_origin

from app.core.config import settings
from app.services.dem_store import read_dem_metadata


def test_evaluate_target_uses_3d_detection_domain_and_optional_type(
    tmp_path: Path,
) -> None:
    from app.main import app

    settings.data_dir = tmp_path
    settings.ensure_directories()
    dem_path = _write_dem(tmp_path)
    metadata = read_dem_metadata("dem_target", dem_path)
    metadata_path = tmp_path / "dem" / "dem_target" / "metadata.json"
    metadata_path.write_text(metadata.model_dump_json(indent=2), encoding="utf-8")

    radar_x, radar_y = Transformer.from_crs(
        "EPSG:4326", "EPSG:32648", always_xy=True
    ).transform(105.0, 35.0)
    target_lon, target_lat = Transformer.from_crs(
        "EPSG:32648", "EPSG:4326", always_xy=True
    ).transform(radar_x + 1_000, radar_y)
    _write_minimum_visible_height(tmp_path, radar_x, radar_y)
    _write_finished_task(tmp_path)
    client = TestClient(app)

    detectable = client.post(
        "/api/radar/coverage/task_target/evaluate-target",
        json={"x": target_lon, "y": target_lat, "z": 200},
    )
    blocked = client.post(
        "/api/radar/coverage/task_target/evaluate-target",
        json={
            "x": target_lon,
            "y": target_lat,
            "z": 120,
            "target_type": "aircraft",
        },
    )

    assert detectable.status_code == 200
    result = detectable.json()
    assert result["detectable"] is True
    assert result["reason"] == "detectable"
    assert result["target_type"] is None
    assert result["target_crs"] == "EPSG:4326"
    assert result["within_range"] is True
    assert result["within_beam"] is True
    assert result["within_elevation"] is True
    assert result["within_dem"] is True
    assert result["terrain_blocked"] is False
    assert result["minimum_detectable_altitude_m"] == 150

    assert blocked.status_code == 200
    blocked_result = blocked.json()
    assert blocked_result["detectable"] is False
    assert blocked_result["reason"] == "terrain_blocked"
    assert blocked_result["target_type"] == "aircraft"
    assert blocked_result["terrain_blocked"] is True


def _write_dem(root: Path) -> Path:
    dem_dir = root / "dem" / "dem_target"
    dem_dir.mkdir(parents=True, exist_ok=True)
    path = dem_dir / "terrain.tif"
    data = numpy.full((200, 200), 100, dtype=numpy.float32)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=data.shape[1],
        height=data.shape[0],
        count=1,
        dtype=data.dtype,
        crs="EPSG:4326",
        transform=from_origin(104.98, 35.02, 0.0002, 0.0002),
        nodata=-9999,
    ) as dataset:
        dataset.write(data, 1)
    return path


def _write_minimum_visible_height(root: Path, radar_x: float, radar_y: float) -> None:
    output_dir = root / "outputs" / "task_target"
    output_dir.mkdir(parents=True, exist_ok=True)
    data = numpy.full((120, 120), 50, dtype=numpy.float32)
    with rasterio.open(
        output_dir / "min_visible_height.tif",
        "w",
        driver="GTiff",
        width=data.shape[1],
        height=data.shape[0],
        count=1,
        dtype=data.dtype,
        crs="EPSG:32648",
        transform=from_origin(radar_x - 6_000, radar_y + 6_000, 100, 100),
        nodata=-9999,
    ) as dataset:
        dataset.write(data, 1)


def _write_finished_task(root: Path) -> None:
    task_dir = root / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task_target.json").write_text(
        json.dumps(
            {
                "task": {
                    "task_id": "task_target",
                    "dem_id": "dem_target",
                    "status": "finished",
                    "progress": 100,
                    "message": "finished",
                    "warnings": [],
                },
                "payload": {
                    "dem_id": "dem_target",
                    "radar": {"lon": 105.0, "lat": 35.0, "height_m": 10},
                    "coverage": {
                        "max_range_m": 5_000,
                        "scan_mode": "omni",
                        "azimuth_deg": 0,
                        "beam_width_deg": 360,
                    },
                    "advanced": {
                        "min_elevation_deg": -10,
                        "max_elevation_deg": 90,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
