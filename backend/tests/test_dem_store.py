import json
from pathlib import Path

from app.core.config import settings
from app.services.dem_store import list_dem_metadata, read_dem_metadata


def test_list_dem_metadata_sorted_by_uploaded_at(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()

    write_metadata(tmp_path, "dem_old", "old.tif", "2026-01-01T00:00:00+00:00")
    write_metadata(tmp_path, "dem_new", "new.tif", "2026-01-02T00:00:00+00:00")

    results = list_dem_metadata()

    assert [item.dem_id for item in results] == ["dem_new", "dem_old"]
    assert results[0].file_size_bytes == 2048


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
