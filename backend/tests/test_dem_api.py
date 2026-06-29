import json
from pathlib import Path

from fastapi.testclient import TestClient
import numpy
import rasterio
from rasterio.transform import from_origin
from PIL import Image
import io

from app.core.config import settings
from app.main import app
from app.services.dem_tiles import terrarium_png
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


def test_chunked_dem_upload_api_merges_and_reads_metadata(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    dem_path = tmp_path / "chunked.tif"
    with rasterio.open(
        dem_path,
        "w",
        driver="GTiff",
        width=4,
        height=4,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(100, 30, 0.1, 0.1),
        nodata=None,
    ) as dataset:
        dataset.write(numpy.zeros((4, 4), dtype=numpy.float32), 1)

    data = dem_path.read_bytes()
    chunk_size = max(1, len(data) // 3)
    chunks = [data[index : index + chunk_size] for index in range(0, len(data), chunk_size)]
    client = TestClient(app)

    start = client.post(
        "/api/dem/uploads",
        json={
            "filename": "chunked.tif",
            "file_size_bytes": len(data),
            "chunk_size_bytes": chunk_size,
            "total_chunks": len(chunks),
        },
    )
    assert start.status_code == 201
    upload_id = start.json()["upload_id"]

    for index, chunk in enumerate(chunks):
        response = client.put(
            f"/api/dem/uploads/{upload_id}/chunks/{index}",
            files={"file": (f"{index}.part", chunk, "application/octet-stream")},
        )
        assert response.status_code == 200
        assert response.json()["uploaded_chunks"] == index + 1

    complete = client.post(f"/api/dem/uploads/{upload_id}/complete")

    assert complete.status_code == 201
    payload = complete.json()
    assert payload["filename"] == "chunked.tif"
    assert payload["width"] == 4
    assert payload["height"] == 4
    assert payload["file_size_bytes"] == len(data)
    assert payload["cog_path"] == "dem.cog.tif"
    assert payload["cog_file_size_bytes"] > 0


def test_dem_tile_api_returns_png(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    dem_id = "dem_tile"
    dem_dir = tmp_path / "dem" / dem_id
    dem_dir.mkdir(parents=True)
    dem_path = dem_dir / "tile.tif"
    with rasterio.open(
        dem_path,
        "w",
        driver="GTiff",
        width=32,
        height=32,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(78, 33, 0.1, 0.1),
        nodata=None,
    ) as dataset:
        dataset.write(numpy.arange(32 * 32, dtype=numpy.float32).reshape((32, 32)), 1)

    metadata = json.loads(read_metadata_json(dem_id, dem_path))
    metadata["uploaded_at"] = "2026-01-02T00:00:00+00:00"
    (dem_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    response = TestClient(app).get(f"/api/dem/{dem_id}/tiles/5/22/12.png")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG")
    assert (dem_dir / "dem.cog.tif").exists()


def test_dem_terrain_tile_api_returns_terrarium_png(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    dem_id = "dem_terrain"
    dem_dir = tmp_path / "dem" / dem_id
    dem_dir.mkdir(parents=True)
    dem_path = dem_dir / "terrain.tif"
    with rasterio.open(
        dem_path,
        "w",
        driver="GTiff",
        width=32,
        height=32,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(78, 33, 0.1, 0.1),
        nodata=None,
    ) as dataset:
        dataset.write(numpy.full((32, 32), 1000, dtype=numpy.float32), 1)

    metadata = json.loads(read_metadata_json(dem_id, dem_path))
    metadata["uploaded_at"] = "2026-01-02T00:00:00+00:00"
    (dem_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    response = TestClient(app).get(f"/api/dem/{dem_id}/terrain/5/22/12.png")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG")
    assert (dem_dir / "dem.cog.tif").exists()


def test_terrarium_png_encodes_elevation() -> None:
    image = Image.open(io.BytesIO(terrarium_png(numpy.full((256, 256), 1000, dtype=numpy.float32)))).convert("RGBA")

    red, green, blue, alpha = image.getpixel((0, 0))

    assert (red, green, blue, alpha) == (131, 232, 0, 255)


def test_dem_tile_api_rejects_invalid_tile_coordinate(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()

    response = TestClient(app).get("/api/dem/dem_tile/tiles/2/4/0.png")

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_TILE_COORDINATE"


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


def read_metadata_json(dem_id: str, path: Path) -> str:
    from app.services.dem_store import read_dem_metadata

    return read_dem_metadata(dem_id, path).model_dump_json()


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
