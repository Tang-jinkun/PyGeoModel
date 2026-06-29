import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.dem import DemDeleteResult, DemMetadata

DEM_ID_PATTERN = re.compile(r"^dem_[A-Za-z0-9_-]+$")


def _metadata_path(dem_id: str) -> Path:
    return _dem_dir(dem_id) / "metadata.json"


def _dem_path(dem_id: str, filename: str) -> Path:
    dem_dir = _dem_dir(dem_id)
    filename_path = Path(filename)
    if filename_path.name != filename:
        raise AppError("INVALID_DEM_PATH", "DEM filename contains unsupported path components.", status_code=400)
    path = (dem_dir / filename).resolve()
    if dem_dir not in path.parents:
        raise AppError("INVALID_DEM_PATH", "Resolved DEM file path escapes DEM directory.", status_code=400)
    return path


def _dem_dir(dem_id: str) -> Path:
    validate_dem_id(dem_id)
    path = (settings.dem_dir / dem_id).resolve()
    dem_dir = settings.dem_dir.resolve()
    if dem_dir not in path.parents:
        raise AppError("INVALID_DEM_PATH", "Resolved DEM path escapes DEM directory.", status_code=400)
    return path


def validate_dem_id(dem_id: str) -> None:
    if not DEM_ID_PATTERN.fullmatch(dem_id):
        raise AppError("INVALID_DEM_ID", "DEM id contains unsupported characters.", status_code=400)


async def save_dem_upload(file: UploadFile) -> DemMetadata:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".tif", ".tiff"}:
        raise AppError("INVALID_DEM", "Only GeoTIFF DEM files are supported in the MVP.")

    dem_id = f"dem_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    target_dir = settings.dem_dir / dem_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = _dem_path(dem_id, Path(file.filename).name)

    with target_path.open("wb") as output:
        shutil.copyfileobj(file.file, output)

    metadata = read_dem_metadata(dem_id, target_path)
    _metadata_path(dem_id).write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
    return metadata


def read_dem_metadata(dem_id: str, path: Path | None = None) -> DemMetadata:
    if path is None:
        metadata_file = _metadata_path(dem_id)
        if not metadata_file.exists():
            raise AppError("DEM_NOT_FOUND", f"DEM '{dem_id}' was not found.", status_code=404)
        metadata = DemMetadata.model_validate_json(metadata_file.read_text(encoding="utf-8"))
        if metadata.dem_id != dem_id:
            raise AppError("DEM_METADATA_MISMATCH", f"DEM metadata for '{dem_id}' is inconsistent.", status_code=500)
        return attach_dem_usage(metadata)

    try:
        import rasterio
    except ImportError as exc:
        raise AppError("RASTERIO_NOT_INSTALLED", "Rasterio is required to read DEM metadata.", status_code=500) from exc

    try:
        with rasterio.open(path) as dataset:
            if dataset.crs is None:
                raise AppError("DEM_WITHOUT_CRS", "DEM is missing coordinate reference system.")

            bounds = dataset.bounds
            metadata = DemMetadata(
                dem_id=dem_id,
                filename=path.name,
                crs=dataset.crs.to_string(),
                bounds=[bounds.left, bounds.bottom, bounds.right, bounds.top],
                resolution=[abs(dataset.res[0]), abs(dataset.res[1])],
                width=dataset.width,
                height=dataset.height,
                nodata=dataset.nodata,
                file_size_bytes=path.stat().st_size,
                uploaded_at=datetime.now(timezone.utc).isoformat(),
            )
    except AppError:
        raise
    except Exception as exc:
        raise AppError("INVALID_DEM", f"Unable to read DEM: {exc}") from exc

    return metadata


def find_dem_file(dem_id: str) -> Path:
    metadata = read_dem_metadata(dem_id)
    path = _dem_path(dem_id, metadata.filename)
    if not path.exists():
        raise AppError("DEM_NOT_FOUND", f"DEM file for '{dem_id}' was not found.", status_code=404)
    return path


def list_dem_metadata() -> list[DemMetadata]:
    results: list[DemMetadata] = []
    for metadata_file in settings.dem_dir.glob("dem_*/metadata.json"):
        data = json.loads(metadata_file.read_text(encoding="utf-8"))
        results.append(attach_dem_usage(DemMetadata.model_validate(data)))
    return sorted(results, key=lambda item: item.uploaded_at or "", reverse=True)


def delete_dem(dem_id: str) -> DemDeleteResult:
    metadata = read_dem_metadata(dem_id)
    usage = dem_usage(dem_id)
    if usage["task_count"] > 0:
        raise AppError(
            "DEM_IN_USE",
            f"DEM '{dem_id}' is referenced by {usage['task_count']} task(s) and cannot be deleted.",
            status_code=409,
        )
    path = _dem_dir(dem_id)
    if not path.exists():
        raise AppError("DEM_NOT_FOUND", f"DEM '{dem_id}' was not found.", status_code=404)
    shutil.rmtree(path)
    return DemDeleteResult(dem_id=dem_id, deleted=True)


def attach_dem_usage(metadata: DemMetadata) -> DemMetadata:
    usage = dem_usage(metadata.dem_id)
    metadata.task_count = usage["task_count"]
    metadata.active_task_count = usage["active_task_count"]
    return metadata


def dem_usage(dem_id: str) -> dict[str, int]:
    validate_dem_id(dem_id)
    from app.services.task_store import list_tasks

    task_count = 0
    active_task_count = 0
    for task in list_tasks():
        if task.dem_id != dem_id:
            continue
        task_count += 1
        if task.status in {"pending", "running"}:
            active_task_count += 1
    return {"task_count": task_count, "active_task_count": active_task_count}
