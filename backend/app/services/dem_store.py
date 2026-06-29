import json
import math
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.dem import DemChunkUploadResult, DemDeleteResult, DemMetadata, DemUploadSession, DemUploadSessionCreate

DEM_ID_PATTERN = re.compile(r"^dem_[A-Za-z0-9_-]+$")
UPLOAD_ID_PATTERN = re.compile(r"^upload_[A-Za-z0-9_-]+$")
DEM_COG_FILENAME = "dem.cog.tif"


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
    if not path.exists():
        raise AppError("DEM_NOT_FOUND", f"DEM file for '{dem_id}' was not found.", status_code=404)
    return path


def find_dem_cog_file(dem_id: str) -> Path:
    metadata = read_dem_metadata(dem_id)
    cog_path = _dem_dir(dem_id) / DEM_COG_FILENAME
    if not cog_path.exists():
        source_path = _dem_path(dem_id, metadata.filename)
        create_dem_cog(dem_id, source_path)
        metadata = metadata_with_cog(metadata, cog_path)
        _metadata_path(dem_id).write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
    return cog_path


def create_dem_cog(dem_id: str, source_path: Path) -> Path:
    return create_dem_cog_for_dir(_dem_dir(dem_id), source_path)


def create_dem_cog_for_dir(dem_dir: Path, source_path: Path) -> Path:
    cog_path = dem_dir / DEM_COG_FILENAME
    temp_path = dem_dir / f".{DEM_COG_FILENAME}.{uuid4().hex}.tmp.tif"
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
        str(temp_path),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        temp_path.replace(cog_path)
    except subprocess.CalledProcessError as exc:
        if temp_path.exists():
            temp_path.unlink()
        message = (exc.stderr or exc.stdout or "").strip()
        raise AppError("COG_GENERATION_FAILED", f"Unable to create COG DEM: {message}", status_code=500) from exc
    return cog_path


def metadata_with_cog(metadata: DemMetadata, cog_path: Path) -> DemMetadata:
    metadata.cog_path = cog_path.name
    metadata.cog_file_size_bytes = cog_path.stat().st_size if cog_path.exists() else None
    return metadata


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


def _dem_path_for_dir(dem_dir: Path, filename: str) -> Path:
    filename = validate_dem_filename(filename)
    path = (dem_dir / filename).resolve()
    resolved_dir = dem_dir.resolve()
    if resolved_dir not in path.parents:
        raise AppError("INVALID_DEM_PATH", "Resolved DEM file path escapes DEM directory.", status_code=400)
    return path
