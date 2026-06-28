from pathlib import Path
from typing import get_args

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.radar import CoverageOutputFile, CoverageOutputKind


OUTPUT_FILENAMES: dict[CoverageOutputKind, str] = {
    "viewshed_tif": "viewshed.tif",
    "visible_geojson": "visible.geojson",
    "blocked_geojson": "blocked.geojson",
    "range_geojson": "radar_range.geojson",
    "model_metadata_json": "model_metadata.json",
    "output_manifest_json": "output_manifest.json",
}

OUTPUT_MEDIA_TYPES: dict[CoverageOutputKind, str] = {
    "viewshed_tif": "image/tiff",
    "visible_geojson": "application/geo+json",
    "blocked_geojson": "application/geo+json",
    "range_geojson": "application/geo+json",
    "model_metadata_json": "application/json",
    "output_manifest_json": "application/json",
}

OUTPUT_LABELS: dict[CoverageOutputKind, str] = {
    "viewshed_tif": "Viewshed GeoTIFF",
    "visible_geojson": "Visible Area GeoJSON",
    "blocked_geojson": "Blocked Area GeoJSON",
    "range_geojson": "Theoretical Range GeoJSON",
    "model_metadata_json": "Model Metadata JSON",
    "output_manifest_json": "Output Manifest JSON",
}


def describe_output_file(task_id: str, kind: CoverageOutputKind, path: Path) -> CoverageOutputFile:
    exists = path.exists()
    return CoverageOutputFile(
        kind=kind,
        label=OUTPUT_LABELS[kind],
        url=f"/outputs/{task_id}/{path.name}",
        download_url=f"/api/radar/coverage/{task_id}/outputs/{kind}",
        filename=path.name,
        media_type=OUTPUT_MEDIA_TYPES[kind],
        size_bytes=path.stat().st_size if exists else None,
        exists=exists,
    )


def describe_output_files(task_id: str, files: dict[CoverageOutputKind, Path]) -> list[CoverageOutputFile]:
    return [describe_output_file(task_id, kind, path) for kind, path in files.items()]


def list_task_output_files(task_id: str) -> list[CoverageOutputFile]:
    return describe_output_files(
        task_id,
        {kind: resolve_task_output_path(task_id, kind) for kind in get_args(CoverageOutputKind)},
    )


def resolve_task_output_path(task_id: str, kind: CoverageOutputKind) -> Path:
    if kind not in OUTPUT_FILENAMES:
        raise AppError("OUTPUT_KIND_NOT_FOUND", f"Output kind '{kind}' is not supported.", status_code=404)

    task_dir = (settings.outputs_dir / task_id).resolve()
    path = (task_dir / OUTPUT_FILENAMES[kind]).resolve()
    if path != task_dir and task_dir not in path.parents:
        raise AppError("INVALID_OUTPUT_PATH", "Resolved output path escapes task directory.", status_code=400)
    return path
