import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.task_store import create_task
from app.schemas.radar import CoverageRequest


def test_delete_dem_api_removes_unreferenced_dem(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_metadata(tmp_path, "dem_free", "free.tif")
    dem_dir = tmp_path / "dem" / "dem_free"
    (dem_dir / "free.tif").write_bytes(b"dem")

    response = TestClient(app).delete("/api/dem/dem_free")

    assert response.status_code == 200
    assert response.json() == {"dem_id": "dem_free", "deleted": True}
    assert not dem_dir.exists()


def test_delete_dem_api_rejects_referenced_dem(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_metadata(tmp_path, "dem_used", "used.tif")
    create_task(make_request("dem_used"))

    response = TestClient(app).delete("/api/dem/dem_used")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "DEM_IN_USE"


def test_delete_dem_api_rejects_invalid_id(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()

    response = TestClient(app).delete("/api/dem/..%5Cdem_bad")

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_DEM_ID"


def test_list_dems_api_includes_usage(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_metadata(tmp_path, "dem_used", "used.tif")
    create_task(make_request("dem_used"))

    response = TestClient(app).get("/api/dem")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["dem_id"] == "dem_used"
    assert payload[0]["task_count"] == 1
    assert payload[0]["active_task_count"] == 1


def write_metadata(root: Path, dem_id: str, filename: str) -> None:
    metadata_dir = root / "dem" / dem_id
    metadata_dir.mkdir(parents=True)
    (metadata_dir / "metadata.json").write_text(
        json.dumps(
            {
                "dem_id": dem_id,
                "filename": filename,
                "crs": "EPSG:4326",
                "bounds": [0, 0, 1, 1],
                "resolution": [30, 30],
                "width": 10,
                "height": 10,
                "nodata": None,
                "uploaded_at": "2026-01-02T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )


def make_request(dem_id: str) -> CoverageRequest:
    return CoverageRequest.model_validate(
        {
            "dem_id": dem_id,
            "radar": {"lon": 105, "lat": 35, "height_m": 10},
            "target": {"height_m": 0},
            "coverage": {
                "max_range_m": 1000,
                "scan_mode": "omni",
                "azimuth_deg": 0,
                "beam_width_deg": 360,
            },
        }
    )
