from pathlib import Path
from typing import get_args

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.watchpost import WatchpostOutputFile, WatchpostOutputKind


WATCHPOST_OUTPUT_FILENAMES: dict[WatchpostOutputKind, str] = {
    "viewshed_tif": "viewshed.tif",
    "visible_geojson": "visible.geojson",
    "blocked_geojson": "blocked.geojson",
    "range_geojson": "range.geojson",
    "model_metadata_json": "model_metadata.json",
    "output_manifest_json": "output_manifest.json",
}

WATCHPOST_OUTPUT_MEDIA_TYPES: dict[WatchpostOutputKind, str] = {
    "viewshed_tif": "image/tiff",
    "visible_geojson": "application/geo+json",
    "blocked_geojson": "application/geo+json",
    "range_geojson": "application/geo+json",
    "model_metadata_json": "application/json",
    "output_manifest_json": "application/json",
}

WATCHPOST_OUTPUT_LABELS: dict[WatchpostOutputKind, str] = {
    "viewshed_tif": "Watchpost Viewshed GeoTIFF",
    "visible_geojson": "Watchpost Visible Area GeoJSON",
    "blocked_geojson": "Watchpost Blocked Area GeoJSON",
    "range_geojson": "Watchpost Theoretical Range GeoJSON",
    "model_metadata_json": "Watchpost Model Metadata JSON",
    "output_manifest_json": "Watchpost Output Manifest JSON",
}


def describe_watchpost_output_file(task_id: str, kind: WatchpostOutputKind, path: Path) -> WatchpostOutputFile:
    exists = path.exists()
    return WatchpostOutputFile(
        kind=kind,
        label=WATCHPOST_OUTPUT_LABELS[kind],
        url=f"/outputs/{task_id}/{path.name}",
        download_url=f"/api/watchpost/detection/{task_id}/outputs/{kind}",
        filename=path.name,
        media_type=WATCHPOST_OUTPUT_MEDIA_TYPES[kind],
        size_bytes=path.stat().st_size if exists else None,
        exists=exists,
    )


def describe_watchpost_output_files(task_id: str, files: dict[WatchpostOutputKind, Path]) -> list[WatchpostOutputFile]:
    return [describe_watchpost_output_file(task_id, kind, path) for kind, path in files.items()]


def list_watchpost_task_output_files(task_id: str) -> list[WatchpostOutputFile]:
    return describe_watchpost_output_files(
        task_id,
        {kind: resolve_watchpost_task_output_path(task_id, kind) for kind in get_args(WatchpostOutputKind)},
    )


def resolve_watchpost_task_output_path(task_id: str, kind: WatchpostOutputKind) -> Path:
    if kind not in WATCHPOST_OUTPUT_FILENAMES:
        raise AppError("OUTPUT_KIND_NOT_FOUND", f"Output kind '{kind}' is not supported.", status_code=404)

    from app.services.watchpost_task_store import validate_watchpost_task_id

    validate_watchpost_task_id(task_id)
    outputs_dir = settings.outputs_dir.resolve()
    task_dir = (settings.outputs_dir / task_id).resolve()
    path = (task_dir / WATCHPOST_OUTPUT_FILENAMES[kind]).resolve()
    if task_dir != outputs_dir and outputs_dir not in task_dir.parents:
        raise AppError("INVALID_OUTPUT_PATH", "Resolved task directory escapes output directory.", status_code=400)
    if path != task_dir and task_dir not in path.parents:
        raise AppError("INVALID_OUTPUT_PATH", "Resolved output path escapes task directory.", status_code=400)
    return path
