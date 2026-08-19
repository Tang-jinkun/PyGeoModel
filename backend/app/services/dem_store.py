import json
import math
import re
import shutil
import subprocess
from contextlib import ExitStack
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.dem import (
    DemBatchCreate,
    DemBatchStatus,
    DemBatchUploadResult,
    DemChunkUploadResult,
    DemDeleteResult,
    DemMetadata,
    DemUploadSession,
    DemUploadSessionCreate,
)

# DEM ids are directory names.  Keep the historical ``dem_...`` values valid,
# while also allowing imported ids such as ``national-dem`` from the CLI.
DEM_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
UPLOAD_ID_PATTERN = re.compile(r"^upload_[A-Za-z0-9_-]+$")
BATCH_ID_PATTERN = re.compile(r"^batch_[A-Za-z0-9_-]+$")
DEM_COG_FILENAME = "dem.cog.tif"
COG_BLOCK_SIZE = 256


def _metadata_path(dem_id: str) -> Path:
    return _dem_dir(dem_id) / "metadata.json"


def _uploads_dir() -> Path:
    path = settings.resolved_data_dir / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _upload_dir(upload_id: str) -> Path:
    validate_upload_id(upload_id)
    uploads_dir = _uploads_dir().resolve()
    path = (uploads_dir / upload_id).resolve()
    if uploads_dir not in path.parents:
        raise AppError("INVALID_UPLOAD_PATH", "Resolved upload path escapes upload directory.", status_code=400)
    return path


def _upload_session_path(upload_id: str) -> Path:
    return _upload_dir(upload_id) / "session.json"


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


def validate_upload_id(upload_id: str) -> None:
    if not UPLOAD_ID_PATTERN.fullmatch(upload_id):
        raise AppError("INVALID_UPLOAD_ID", "Upload id contains unsupported characters.", status_code=400)


def validate_batch_id(batch_id: str) -> None:
    if not BATCH_ID_PATTERN.fullmatch(batch_id):
        raise AppError("INVALID_BATCH_ID", "Batch id contains unsupported characters.", status_code=400)


def _batch_dir(batch_id: str) -> Path:
    validate_batch_id(batch_id)
    uploads_dir = _uploads_dir().resolve()
    path = (uploads_dir / batch_id).resolve()
    if uploads_dir not in path.parents:
        raise AppError("INVALID_BATCH_PATH", "Resolved batch path escapes upload directory.", status_code=400)
    return path


def _batch_file_path(batch_id: str) -> Path:
    return _batch_dir(batch_id) / "batch.json"


def _batch_tiles_dir(batch_id: str) -> Path:
    path = _batch_dir(batch_id) / "tiles"
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_dem_batch(payload: DemBatchCreate) -> DemBatchStatus:
    dem_id = payload.dem_id or f"dem_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    validate_dem_id(dem_id)
    if _dem_dir(dem_id).exists():
        raise AppError("DEM_ALREADY_EXISTS", f"DEM '{dem_id}' already exists.", status_code=409)
    batch_id = f"batch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    batch = DemBatchStatus(
        batch_id=batch_id,
        dem_id=dem_id,
        label=payload.label.strip() if payload.label and payload.label.strip() else None,
        status="uploading",
        filenames=[],
        file_count=0,
    )
    batch_dir = _batch_dir(batch_id)
    batch_dir.mkdir(parents=True, exist_ok=False)
    _write_batch(batch)
    return batch


def read_dem_batch(batch_id: str) -> DemBatchStatus:
    path = _batch_file_path(batch_id)
    if not path.exists():
        raise AppError("BATCH_NOT_FOUND", f"DEM batch '{batch_id}' was not found.", status_code=404)
    try:
        return DemBatchStatus.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AppError("BATCH_RECORD_CORRUPT", f"DEM batch '{batch_id}' is invalid.", status_code=500) from exc


def _write_batch(batch: DemBatchStatus) -> None:
    path = _batch_file_path(batch.batch_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temp_path.write_text(batch.model_dump_json(indent=2), encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


async def save_dem_batch_tiles(batch_id: str, files: list[UploadFile]) -> DemBatchUploadResult:
    batch = read_dem_batch(batch_id)
    if batch.status not in {"uploading", "failed"}:
        raise AppError("DEM_BATCH_NOT_UPLOADABLE", f"DEM batch '{batch_id}' is not accepting files.", status_code=409)
    if not files:
        raise AppError("DEM_TILE_FORMAT_INVALID", "At least one DEM tile is required.")
    tiles_dir = _batch_tiles_dir(batch_id)
    existing = set(batch.filenames)
    incoming: list[str] = []
    try:
        for file in files:
            filename = validate_dem_filename(Path(file.filename or "").name)
            if filename in existing or filename in incoming:
                raise AppError("DEM_TILE_FORMAT_INVALID", f"DEM tile '{filename}' was uploaded more than once.", status_code=409)
            temp_path = tiles_dir / f".{filename}.{uuid4().hex}.tmp"
            target_path = tiles_dir / filename
            try:
                with temp_path.open("wb") as output:
                    shutil.copyfileobj(file.file, output)
                temp_path.replace(target_path)
            finally:
                if temp_path.exists():
                    temp_path.unlink()
            incoming.append(filename)
    except Exception:
        for filename in incoming:
            path = tiles_dir / filename
            if path.exists():
                path.unlink()
        raise
    batch.filenames = sorted([*existing, *incoming], key=str.lower)
    batch.file_count = len(batch.filenames)
    batch.status = "uploading"
    batch.error = None
    _write_batch(batch)
    return DemBatchUploadResult(batch_id=batch.batch_id, filenames=batch.filenames, file_count=batch.file_count)


def queue_dem_batch_merge(batch_id: str) -> DemBatchStatus:
    batch = read_dem_batch(batch_id)
    if not batch.filenames:
        raise AppError("DEM_TILE_FORMAT_INVALID", "At least one DEM tile is required.")
    if batch.status == "ready":
        return batch
    if batch.status in {"validating", "merging"}:
        raise AppError("DEM_BATCH_BUSY", f"DEM batch '{batch_id}' is already being merged.", status_code=409)
    batch.status = "merging"
    batch.error = None
    _write_batch(batch)
    return batch


def complete_dem_batch(batch_id: str) -> DemBatchStatus:
    batch = read_dem_batch(batch_id)
    if batch.status == "ready":
        return batch
    tiles_dir = _batch_tiles_dir(batch_id)
    tile_paths = [tiles_dir / filename for filename in batch.filenames]
    target_dir = _dem_dir(batch.dem_id)
    staging_dir = target_dir.with_name(f".{target_dir.name}.staging-{uuid4().hex}")
    try:
        batch.status = "validating"
        _write_batch(batch)
        validate_dem_tile_set(tile_paths)
        batch.status = "merging"
        _write_batch(batch)
        if target_dir.exists():
            raise AppError("DEM_ALREADY_EXISTS", f"DEM '{batch.dem_id}' already exists.", status_code=409)
        staging_dir.mkdir(parents=True, exist_ok=False)
        cog_path = create_dem_cog_from_tiles(tile_paths, staging_dir)
        metadata = read_dem_metadata(batch.dem_id, cog_path)
        metadata.filename = batch.label or batch.filenames[0]
        metadata.file_size_bytes = sum(path.stat().st_size for path in tile_paths)
        metadata = metadata_with_cog(metadata, cog_path)
        metadata.source_type = "tiled_upload_batch"
        metadata.source_tile_count = len(batch.filenames)
        metadata.source_filenames = list(batch.filenames)
        _write_metadata(staging_dir / "metadata.json", metadata)
        staging_dir.replace(target_dir)
        shutil.rmtree(tiles_dir, ignore_errors=True)
        batch.status = "ready"
        batch.error = None
        _write_batch(batch)
        return batch
    except Exception as exc:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        batch.status = "failed"
        batch.error = str(exc)
        _write_batch(batch)
        return batch


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
    create_dem_cog(dem_id, target_path)
    metadata = metadata_with_cog(metadata, _dem_dir(dem_id) / DEM_COG_FILENAME)
    _metadata_path(dem_id).write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
    return metadata


def create_upload_session(payload: DemUploadSessionCreate) -> DemUploadSession:
    filename = validate_dem_filename(payload.filename)
    if payload.file_size_bytes <= 0:
        raise AppError("INVALID_UPLOAD", "File size must be greater than zero.")
    if payload.chunk_size_bytes <= 0:
        raise AppError("INVALID_UPLOAD", "Chunk size must be greater than zero.")
    if payload.total_chunks <= 0:
        raise AppError("INVALID_UPLOAD", "Total chunks must be greater than zero.")
    expected_chunks = (payload.file_size_bytes + payload.chunk_size_bytes - 1) // payload.chunk_size_bytes
    if payload.total_chunks != expected_chunks:
        raise AppError("INVALID_UPLOAD", "Total chunks does not match file size and chunk size.")

    upload_id = f"upload_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    upload_dir = _upload_dir(upload_id)
    chunks_dir = upload_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    session = DemUploadSession(
        upload_id=upload_id,
        filename=filename,
        file_size_bytes=payload.file_size_bytes,
        chunk_size_bytes=payload.chunk_size_bytes,
        total_chunks=payload.total_chunks,
        uploaded_chunks=[],
    )
    write_upload_session(session)
    return session


async def save_upload_chunk(upload_id: str, chunk_index: int, file: UploadFile) -> DemChunkUploadResult:
    session = read_upload_session(upload_id)
    if chunk_index < 0 or chunk_index >= session.total_chunks:
        raise AppError("INVALID_CHUNK_INDEX", "Chunk index is outside the upload session range.")

    chunk_path = chunk_file_path(upload_id, chunk_index)
    chunk_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = chunk_path.with_suffix(f"{chunk_path.suffix}.{uuid4().hex}.tmp")
    try:
        with temp_path.open("wb") as output:
            shutil.copyfileobj(file.file, output)
        expected_size = expected_chunk_size(session, chunk_index)
        actual_size = temp_path.stat().st_size
        if actual_size != expected_size:
            raise AppError(
                "INVALID_CHUNK_SIZE",
                f"Chunk {chunk_index} has size {actual_size}, expected {expected_size}.",
                status_code=400,
            )
        temp_path.replace(chunk_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()

    uploaded = sorted({*session.uploaded_chunks, chunk_index})
    session.uploaded_chunks = uploaded
    write_upload_session(session)
    return DemChunkUploadResult(
        upload_id=upload_id,
        chunk_index=chunk_index,
        uploaded_chunks=len(uploaded),
        total_chunks=session.total_chunks,
    )


def complete_upload_session(upload_id: str) -> DemMetadata:
    session = read_upload_session(upload_id)
    missing = [index for index in range(session.total_chunks) if not chunk_file_path(upload_id, index).exists()]
    if missing:
        raise AppError("UPLOAD_INCOMPLETE", f"Upload is missing {len(missing)} chunk(s).", status_code=409)

    dem_id = f"dem_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    upload_dir = _upload_dir(upload_id)
    target_dir = settings.dem_dir / dem_id
    staging_dir = target_dir.with_name(f".{target_dir.name}.staging-{uuid4().hex}")
    staging_dir.mkdir(parents=True, exist_ok=False)
    target_path = _dem_path_for_dir(staging_dir, session.filename)

    try:
        with target_path.open("wb") as output:
            for index in range(session.total_chunks):
                with chunk_file_path(upload_id, index).open("rb") as chunk:
                    shutil.copyfileobj(chunk, output)
        actual_size = target_path.stat().st_size
        if actual_size != session.file_size_bytes:
            raise AppError(
                "UPLOAD_SIZE_MISMATCH",
                f"Merged upload has size {actual_size}, expected {session.file_size_bytes}.",
                status_code=400,
            )
        metadata = read_dem_metadata(dem_id, target_path)
        create_dem_cog_for_dir(staging_dir, target_path)
        metadata = metadata_with_cog(metadata, staging_dir / DEM_COG_FILENAME)
        (staging_dir / "metadata.json").write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
        staging_dir.replace(target_dir)
    except Exception:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    finally:
        if upload_dir.exists():
            shutil.rmtree(upload_dir, ignore_errors=True)

    return metadata


def validate_dem_filename(filename: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in {".tif", ".tiff"}:
        raise AppError("INVALID_DEM", "Only GeoTIFF DEM files are supported in the MVP.")
    safe_name = Path(filename).name
    if safe_name != filename:
        raise AppError("INVALID_DEM_PATH", "DEM filename contains unsupported path components.", status_code=400)
    return safe_name


def read_upload_session(upload_id: str) -> DemUploadSession:
    path = _upload_session_path(upload_id)
    if not path.exists():
        raise AppError("UPLOAD_NOT_FOUND", f"Upload session '{upload_id}' was not found.", status_code=404)
    return DemUploadSession.model_validate_json(path.read_text(encoding="utf-8"))


def write_upload_session(session: DemUploadSession) -> None:
    path = _upload_session_path(session.upload_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(session.model_dump_json(indent=2), encoding="utf-8")


def chunk_file_path(upload_id: str, chunk_index: int) -> Path:
    return _upload_dir(upload_id) / "chunks" / f"{chunk_index:08d}.part"


def expected_chunk_size(session: DemUploadSession, chunk_index: int) -> int:
    if chunk_index == session.total_chunks - 1:
        return session.file_size_bytes - session.chunk_size_bytes * (session.total_chunks - 1)
    return session.chunk_size_bytes


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
                bounds=[
                    require_finite_float(bounds.left, "DEM left bound"),
                    require_finite_float(bounds.bottom, "DEM bottom bound"),
                    require_finite_float(bounds.right, "DEM right bound"),
                    require_finite_float(bounds.top, "DEM top bound"),
                ],
                resolution=[
                    require_finite_float(abs(dataset.res[0]), "DEM x resolution"),
                    require_finite_float(abs(dataset.res[1]), "DEM y resolution"),
                ],
                width=dataset.width,
                height=dataset.height,
                nodata=optional_finite_float(dataset.nodata),
                file_size_bytes=path.stat().st_size,
                uploaded_at=datetime.now(timezone.utc).isoformat(),
            )
    except AppError:
        raise
    except Exception as exc:
        raise AppError("INVALID_DEM", f"Unable to read DEM: {exc}") from exc

    return metadata


def optional_finite_float(value: float | int | None) -> float | None:
    if value is None:
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def require_finite_float(value: float | int, label: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise AppError("INVALID_DEM", f"{label} is not a finite number.")
    return result


def find_dem_file(dem_id: str) -> Path:
    metadata = read_dem_metadata(dem_id)
    path = _dem_path(dem_id, metadata.filename)
    if not path.exists() and metadata.cog_path:
        path = _dem_path(dem_id, metadata.cog_path)
    if not path.exists():
        raise AppError("DEM_NOT_FOUND", f"DEM file for '{dem_id}' was not found.", status_code=404)
    return path


def find_dem_compute_file(dem_id: str) -> Path:
    """Return the COG used for all DEM calculations and terrain rendering.

    Existing uploaded DEMs may only have the original GeoTIFF in their
    directory.  In that case the COG is created lazily once and recorded in
    metadata.  Imported nationwide DEMs intentionally contain only the COG,
    so they work without retaining the original source file.
    """

    metadata = read_dem_metadata(dem_id)
    cog_filename = metadata.cog_path or DEM_COG_FILENAME
    cog_path = _dem_path(dem_id, cog_filename)
    if cog_path.is_file():
        return cog_path

    source_path = _dem_path(dem_id, metadata.filename)
    if not source_path.is_file():
        raise AppError("DEM_NOT_FOUND", f"DEM file for '{dem_id}' was not found.", status_code=404)
    create_dem_cog(dem_id, source_path)
    metadata = metadata_with_cog(metadata, cog_path)
    _write_metadata(_metadata_path(dem_id), metadata)
    return cog_path


def find_dem_cog_file(dem_id: str) -> Path:
    """Backward-compatible name for the standard DEM compute source."""

    return find_dem_compute_file(dem_id)


def import_dem_from_path(source: Path, dem_id: str) -> DemMetadata:
    """Import an external GeoTIFF as an atomic, COG-only DEM dataset."""

    validate_dem_id(dem_id)
    source_path = Path(source).expanduser().resolve()
    validate_dem_filename(source_path.name)
    if not source_path.is_file():
        raise AppError("DEM_SOURCE_NOT_FOUND", f"DEM source '{source_path}' was not found.", status_code=400)

    _validate_import_source(source_path)
    target_dir = _dem_dir(dem_id)
    if target_dir.exists():
        raise AppError("DEM_ALREADY_EXISTS", f"DEM '{dem_id}' already exists.", status_code=409)

    staging_dir = target_dir.with_name(f".{target_dir.name}.staging-{uuid4().hex}")
    staging_dir.mkdir(parents=True, exist_ok=False)
    try:
        metadata = read_dem_metadata(dem_id, source_path)
        cog_path = create_dem_cog_for_dir(staging_dir, source_path)
        validate_dem_cog(cog_path)
        metadata = metadata_with_cog(metadata, cog_path)
        _write_metadata(staging_dir / "metadata.json", metadata)
        staging_dir.replace(target_dir)
        return metadata
    except Exception:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        raise


def _validate_import_source(source_path: Path) -> None:
    try:
        import numpy
        import rasterio
    except ImportError as exc:
        raise AppError("RASTERIO_NOT_INSTALLED", "Rasterio is required to import DEM data.", status_code=500) from exc

    try:
        with rasterio.open(source_path) as dataset:
            if dataset.crs is None:
                raise AppError("DEM_WITHOUT_CRS", "DEM is missing coordinate reference system.")
            if dataset.count != 1:
                raise AppError("INVALID_DEM", "DEM must contain exactly one raster band.")
            if dataset.width <= 0 or dataset.height <= 0:
                raise AppError("INVALID_DEM", "DEM dimensions must be greater than zero.")
            if numpy.dtype(dataset.dtypes[0]).kind not in "biuf":
                raise AppError("INVALID_DEM", "DEM band must use a numeric data type.")
            bounds = dataset.bounds
            for value in (bounds.left, bounds.bottom, bounds.right, bounds.top):
                if not math.isfinite(float(value)):
                    raise AppError("INVALID_DEM", "DEM bounds must be finite.")
            if bounds.left >= bounds.right or bounds.bottom >= bounds.top:
                raise AppError("INVALID_DEM", "DEM bounds must have positive width and height.")
    except AppError:
        raise
    except Exception as exc:
        raise AppError("INVALID_DEM", f"Unable to read DEM source: {exc}") from exc


def validate_dem_cog(cog_path: Path) -> None:
    """Validate the storage properties required by the nationwide DEM flow."""

    try:
        import rasterio
    except ImportError as exc:
        raise AppError("RASTERIO_NOT_INSTALLED", "Rasterio is required to validate COG data.", status_code=500) from exc

    try:
        with rasterio.open(cog_path) as dataset:
            if dataset.count != 1 or not dataset.is_tiled:
                raise AppError("INVALID_COG", "COG must be a single-band internally tiled GeoTIFF.")
            if dataset.block_shapes[0] != (COG_BLOCK_SIZE, COG_BLOCK_SIZE):
                raise AppError("INVALID_COG", f"COG tile size must be {COG_BLOCK_SIZE}x{COG_BLOCK_SIZE}.")
            if not dataset.overviews(1):
                raise AppError("INVALID_COG", "COG must contain internal overviews.")
    except AppError:
        raise
    except Exception as exc:
        raise AppError("INVALID_COG", f"Unable to validate COG: {exc}") from exc


def create_dem_cog(dem_id: str, source_path: Path) -> Path:
    return create_dem_cog_for_dir(_dem_dir(dem_id), source_path)


def validate_dem_tile_set(tile_paths: list[Path]) -> dict[str, object]:
    """Validate a set of aligned single-band DEM tiles before mosaicking."""

    if not tile_paths:
        raise AppError("DEM_TILE_FORMAT_INVALID", "At least one DEM tile is required.")

    ordered_paths = sorted((Path(path).expanduser().resolve() for path in tile_paths), key=lambda path: path.name.lower())
    first = None
    bounds: list[float] | None = None
    for path in ordered_paths:
        validate_dem_filename(path.name)
        if not path.is_file():
            raise AppError("DEM_TILE_FORMAT_INVALID", f"DEM tile '{path.name}' was not found.")
        try:
            import rasterio
        except ImportError as exc:
            raise AppError("RASTERIO_NOT_INSTALLED", "Rasterio is required to validate DEM tiles.", status_code=500) from exc
        try:
            with rasterio.open(path) as dataset:
                if dataset.crs is None:
                    raise AppError("DEM_TILE_CRS_MISMATCH", f"DEM tile '{path.name}' is missing CRS.")
                if dataset.count != 1:
                    raise AppError("DEM_TILE_BAND_MISMATCH", f"DEM tile '{path.name}' must contain one band.")
                if dataset.width <= 0 or dataset.height <= 0:
                    raise AppError("DEM_TILE_FORMAT_INVALID", f"DEM tile '{path.name}' has invalid dimensions.")
                if first is None:
                    first = {
                        "crs": dataset.crs.to_string(),
                        "resolution": (abs(float(dataset.res[0])), abs(float(dataset.res[1]))),
                        "dtype": dataset.dtypes[0],
                        "nodata": optional_finite_float(dataset.nodata),
                        "transform": dataset.transform,
                    }
                else:
                    if dataset.crs.to_string() != first["crs"]:
                        raise AppError("DEM_TILE_CRS_MISMATCH", f"DEM tile '{path.name}' uses a different CRS.")
                    resolution = (abs(float(dataset.res[0])), abs(float(dataset.res[1])))
                    if not _nearly_equal_pair(resolution, first["resolution"]):
                        raise AppError("DEM_TILE_GRID_MISMATCH", f"DEM tile '{path.name}' uses a different resolution.")
                    if dataset.dtypes[0] != first["dtype"]:
                        raise AppError("DEM_TILE_GRID_MISMATCH", f"DEM tile '{path.name}' uses a different data type.")
                    if not _same_optional_float(optional_finite_float(dataset.nodata), first["nodata"]):
                        raise AppError("DEM_TILE_GRID_MISMATCH", f"DEM tile '{path.name}' uses a different NoData value.")
                    if not _aligned_transform(dataset.transform, first["transform"], first["resolution"]):
                        raise AppError("DEM_TILE_GRID_MISMATCH", f"DEM tile '{path.name}' is not aligned to the common pixel grid.")
                tile_bounds = dataset.bounds
                tile_values = [tile_bounds.left, tile_bounds.bottom, tile_bounds.right, tile_bounds.top]
                if not all(math.isfinite(float(value)) for value in tile_values):
                    raise AppError("DEM_TILE_FORMAT_INVALID", f"DEM tile '{path.name}' has non-finite bounds.")
                if bounds is None:
                    bounds = [float(value) for value in tile_values]
                else:
                    bounds = [
                        min(bounds[0], tile_bounds.left),
                        min(bounds[1], tile_bounds.bottom),
                        max(bounds[2], tile_bounds.right),
                        max(bounds[3], tile_bounds.top),
                    ]
        except AppError:
            raise
        except Exception as exc:
            raise AppError("DEM_TILE_FORMAT_INVALID", f"Unable to read DEM tile '{path.name}': {exc}") from exc

    if first is None or bounds is None:
        raise AppError("DEM_TILE_FORMAT_INVALID", "At least one readable DEM tile is required.")
    return {
        "paths": ordered_paths,
        "crs": first["crs"],
        "resolution": list(first["resolution"]),
        "nodata": first["nodata"],
        "bounds": bounds,
    }


def create_dem_cog_from_tiles(tile_paths: list[Path], dem_dir: Path) -> Path:
    """Create one COG from aligned tiles without loading a large mosaic in Python."""

    tile_info = validate_dem_tile_set(tile_paths)
    ordered_paths = tile_info["paths"]
    dem_dir = Path(dem_dir)
    dem_dir.mkdir(parents=True, exist_ok=True)
    cog_path = dem_dir / DEM_COG_FILENAME
    temp_cog = dem_dir / f".{DEM_COG_FILENAME}.{uuid4().hex}.tmp.tif"
    temp_vrt = dem_dir / f".dem-mosaic.{uuid4().hex}.vrt"
    temp_mosaic = dem_dir / f".dem-mosaic.{uuid4().hex}.tif"
    try:
        if shutil.which("gdalbuildvrt") and shutil.which("gdal_translate"):
            command = [
                "gdalbuildvrt",
                "-overwrite",
                "-r",
                "nearest",
                str(temp_vrt),
                *(str(path) for path in ordered_paths),
            ]
            subprocess.run(command, check=True, capture_output=True, text=True)
            create_dem_cog_with_gdal(temp_vrt, temp_cog)
        else:
            _create_small_dem_cog_from_tiles_with_rasterio(ordered_paths, temp_mosaic, temp_cog)
        validate_dem_cog(temp_cog)
        temp_cog.replace(cog_path)
        return cog_path
    except AppError:
        raise
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "").strip()
        raise AppError("DEM_COG_MERGE_FAILED", f"Unable to merge DEM tiles: {message}", status_code=500) from exc
    except Exception as exc:
        raise AppError("DEM_COG_MERGE_FAILED", f"Unable to merge DEM tiles: {exc}", status_code=500) from exc
    finally:
        for path in (temp_vrt, temp_mosaic, temp_cog):
            if path.exists():
                path.unlink()


def _create_small_dem_cog_from_tiles_with_rasterio(
    tile_paths: list[Path],
    mosaic_path: Path,
    cog_path: Path,
) -> None:
    """Development fallback for small mosaics when GDAL CLI is unavailable."""

    import rasterio
    from rasterio.merge import merge

    with ExitStack() as stack:
        sources = [stack.enter_context(rasterio.open(path)) for path in tile_paths]
        bounds = [
            min(source.bounds.left for source in sources),
            min(source.bounds.bottom for source in sources),
            max(source.bounds.right for source in sources),
            max(source.bounds.top for source in sources),
        ]
        resolution = sources[0].res
        estimated_cells = math.ceil((bounds[2] - bounds[0]) / resolution[0]) * math.ceil(
            (bounds[3] - bounds[1]) / resolution[1]
        )
        if estimated_cells > 4_000_000:
            raise AppError(
                "DEM_COG_MERGE_FAILED",
                "GDAL is required to merge DEM tiles larger than the development fallback limit.",
                status_code=500,
            )
        mosaic, transform = merge(sources, method="last")
        profile = sources[0].profile.copy()
        profile.update(
            driver="GTiff",
            width=mosaic.shape[2],
            height=mosaic.shape[1],
            count=1,
            transform=transform,
            compress="deflate",
        )
        with rasterio.open(mosaic_path, "w", **profile) as destination:
            destination.write(mosaic)
    create_dem_cog_with_rasterio(mosaic_path, cog_path)


def _nearly_equal_pair(first: tuple[float, float], second: tuple[float, float]) -> bool:
    return math.isclose(first[0], second[0], rel_tol=1e-9, abs_tol=1e-9) and math.isclose(
        first[1], second[1], rel_tol=1e-9, abs_tol=1e-9
    )


def _same_optional_float(first: float | None, second: float | None) -> bool:
    if first is None or second is None:
        return first is None and second is None
    return math.isclose(first, second, rel_tol=1e-9, abs_tol=1e-9)


def _aligned_transform(first, second, resolution: tuple[float, float]) -> bool:
    if not all(math.isclose(float(first[index]), float(second[index]), abs_tol=1e-12) for index in (0, 1, 3, 4)):
        return False
    x_offset = (float(first.c) - float(second.c)) / resolution[0]
    y_offset = (float(second.f) - float(first.f)) / resolution[1]
    return math.isclose(x_offset, round(x_offset), abs_tol=1e-6) and math.isclose(
        y_offset, round(y_offset), abs_tol=1e-6
    )


def create_dem_cog_for_dir(dem_dir: Path, source_path: Path) -> Path:
    cog_path = dem_dir / DEM_COG_FILENAME
    temp_path = dem_dir / f".{DEM_COG_FILENAME}.{uuid4().hex}.tmp.tif"
    try:
        if shutil.which("gdal_translate"):
            create_dem_cog_with_gdal(source_path, temp_path)
        else:
            create_dem_cog_with_rasterio(source_path, temp_path)
        temp_path.replace(cog_path)
    except subprocess.CalledProcessError as exc:
        if temp_path.exists():
            temp_path.unlink()
        message = (exc.stderr or exc.stdout or "").strip()
        raise AppError("COG_GENERATION_FAILED", f"Unable to create COG DEM: {message}", status_code=500) from exc
    except Exception as exc:
        if temp_path.exists():
            temp_path.unlink()
        raise AppError("COG_GENERATION_FAILED", f"Unable to create COG DEM: {exc}", status_code=500) from exc
    return cog_path


def create_dem_cog_with_gdal(source_path: Path, destination_path: Path) -> None:
    command = [
        "gdal_translate",
        "-of",
        "COG",
        "-co",
        "COMPRESS=DEFLATE",
        "-co",
        "PREDICTOR=2",
        "-co",
        "BLOCKSIZE=256",
        "-co",
        "RESAMPLING=BILINEAR",
        "-co",
        "OVERVIEWS=AUTO",
        str(source_path),
        str(destination_path),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)


def create_dem_cog_with_rasterio(source_path: Path, destination_path: Path) -> None:
    import rasterio.shutil as rio_shutil

    rio_shutil.copy(
        source_path,
        destination_path,
        driver="COG",
        strict=False,
        COMPRESS="DEFLATE",
        PREDICTOR="2",
        BLOCKSIZE="256",
        RESAMPLING="BILINEAR",
        OVERVIEWS="AUTO",
    )


def metadata_with_cog(metadata: DemMetadata, cog_path: Path) -> DemMetadata:
    metadata.cog_path = cog_path.name
    metadata.cog_file_size_bytes = cog_path.stat().st_size if cog_path.exists() else None
    return metadata


def _write_metadata(path: Path, metadata: DemMetadata) -> None:
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temp_path.write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def list_dem_metadata() -> list[DemMetadata]:
    results: list[DemMetadata] = []
    if not settings.dem_dir.exists():
        return results
    for dem_dir in settings.dem_dir.iterdir():
        if not dem_dir.is_dir() or dem_dir.name.startswith("."):
            continue
        metadata_file = dem_dir / "metadata.json"
        if not metadata_file.is_file():
            continue
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


def _dem_path_for_dir(dem_dir: Path, filename: str) -> Path:
    filename = validate_dem_filename(filename)
    path = (dem_dir / filename).resolve()
    resolved_dir = dem_dir.resolve()
    if resolved_dir not in path.parents:
        raise AppError("INVALID_DEM_PATH", "Resolved DEM file path escapes DEM directory.", status_code=400)
    return path
