import json
from pathlib import Path

import pytest

from app.core.errors import AppError
from app.core.config import settings
from app.services.dem_store import delete_dem, find_dem_file, list_dem_metadata, read_dem_metadata
from app.services.task_store import create_task
from app.schemas.radar import CoverageRequest


def test_list_dem_metadata_sorted_by_uploaded_at(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()

    write_metadata(tmp_path, "dem_old", "old.tif", "2026-01-01T00:00:00+00:00")
    write_metadata(tmp_path, "dem_new", "new.tif", "2026-01-02T00:00:00+00:00")

    results = list_dem_metadata()

    assert [item.dem_id for item in results] == ["dem_new", "dem_old"]
    assert results[0].file_size_bytes == 2048
    assert results[0].task_count == 0


def test_read_dem_metadata_supports_optional_runtime_fields(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()

    metadata_dir = tmp_path / "dem" / "dem_legacy"
    metadata_dir.mkdir(parents=True)
    (metadata_dir / "metadata.json").write_text(
        json.dumps(
            {
                "dem_id": "dem_legacy",
                "filename": "legacy.tif",
                "crs": "EPSG:4326",
                "bounds": [0, 0, 1, 1],
                "resolution": [30, 30],
                "width": 10,
                "height": 10,
                "nodata": None,
            }
        ),
        encoding="utf-8",
    )

    metadata = read_dem_metadata("dem_legacy")

    assert metadata.file_size_bytes is None
    assert metadata.uploaded_at is None
    assert metadata.task_count == 0


def test_list_dem_metadata_includes_task_usage(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()

    write_metadata(tmp_path, "dem_used", "used.tif", "2026-01-02T00:00:00+00:00")
    create_task(make_request("dem_used"))

    metadata = list_dem_metadata()[0]

    assert metadata.dem_id == "dem_used"
    assert metadata.task_count == 1
    assert metadata.active_task_count == 1


def test_delete_dem_removes_unreferenced_directory(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_metadata(tmp_path, "dem_free", "free.tif", "2026-01-02T00:00:00+00:00")
    dem_dir = tmp_path / "dem" / "dem_free"
    (dem_dir / "free.tif").write_bytes(b"dem")

    result = delete_dem("dem_free")

    assert result.deleted is True
    assert not dem_dir.exists()


def test_delete_dem_rejects_referenced_dem(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_metadata(tmp_path, "dem_used", "used.tif", "2026-01-02T00:00:00+00:00")
    create_task(make_request("dem_used"))

    with pytest.raises(AppError) as exc_info:
        delete_dem("dem_used")

    assert exc_info.value.code == "DEM_IN_USE"
    assert (tmp_path / "dem" / "dem_used").exists()


def test_delete_dem_rejects_invalid_id(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()

    with pytest.raises(AppError) as exc_info:
        delete_dem("../dem_bad")

    assert exc_info.value.code == "INVALID_DEM_ID"


def test_delete_dem_rejects_metadata_mismatch(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_metadata(tmp_path, "dem_a", "a.tif", "2026-01-02T00:00:00+00:00")
    write_metadata(tmp_path, "dem_b", "b.tif", "2026-01-02T00:00:00+00:00")
    metadata_path = tmp_path / "dem" / "dem_a" / "metadata.json"
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["dem_id"] = "dem_b"
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AppError) as exc_info:
        delete_dem("dem_a")

    assert exc_info.value.code == "DEM_METADATA_MISMATCH"
    assert (tmp_path / "dem" / "dem_a").exists()
    assert (tmp_path / "dem" / "dem_b").exists()


def test_find_dem_file_rejects_filename_path_escape(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_metadata(tmp_path, "dem_a", "../outside.tif", "2026-01-02T00:00:00+00:00")

    with pytest.raises(AppError) as exc_info:
        find_dem_file("dem_a")

    assert exc_info.value.code == "INVALID_DEM_PATH"


def write_metadata(root: Path, dem_id: str, filename: str, uploaded_at: str) -> None:
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
                "file_size_bytes": 2048,
                "uploaded_at": uploaded_at,
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
