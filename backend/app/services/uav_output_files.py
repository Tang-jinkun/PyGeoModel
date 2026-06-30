from pathlib import Path
from typing import get_args

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.uav import UavOutputFile, UavOutputKind


UAV_OUTPUT_FILENAMES: dict[UavOutputKind, str] = {
    "footprint_geojson": "footprint.geojson",
    "visible_geojson": "visible.geojson",
    "blocked_geojson": "blocked.geojson",
    "model_metadata_json": "model_metadata.json",
    "output_manifest_json": "output_manifest.json",
}

UAV_OUTPUT_MEDIA_TYPES: dict[UavOutputKind, str] = {
    "footprint_geojson": "application/geo+json",
    "visible_geojson": "application/geo+json",
    "blocked_geojson": "application/geo+json",
    "model_metadata_json": "application/json",
    "output_manifest_json": "application/json",
}

UAV_OUTPUT_LABELS: dict[UavOutputKind, str] = {
    "footprint_geojson": "UAV Sensor Footprint GeoJSON",
    "visible_geojson": "UAV Visible Recon Area GeoJSON",
    "blocked_geojson": "UAV Terrain Blocked Area GeoJSON",
    "model_metadata_json": "UAV Model Metadata JSON",
    "output_manifest_json": "UAV Output Manifest JSON",
}


def describe_uav_output_file(task_id: str, kind: UavOutputKind, path: Path) -> UavOutputFile:
    exists = path.exists()
    return UavOutputFile(
        kind=kind,
        label=UAV_OUTPUT_LABELS[kind],
        url=f"/outputs/{task_id}/{path.name}",
        download_url=f"/api/uav/recon/{task_id}/outputs/{kind}",
        filename=path.name,
        media_type=UAV_OUTPUT_MEDIA_TYPES[kind],
        size_bytes=path.stat().st_size if exists else None,
        exists=exists,
    )


def describe_uav_output_files(task_id: str, files: dict[UavOutputKind, Path]) -> list[UavOutputFile]:
    return [describe_uav_output_file(task_id, kind, path) for kind, path in files.items()]


def list_uav_task_output_files(task_id: str) -> list[UavOutputFile]:
    return describe_uav_output_files(
        task_id,
        {kind: resolve_uav_task_output_path(task_id, kind) for kind in get_args(UavOutputKind)},
    )


def resolve_uav_task_output_path(task_id: str, kind: UavOutputKind) -> Path:
    if kind not in UAV_OUTPUT_FILENAMES:
        raise AppError("OUTPUT_KIND_NOT_FOUND", f"Output kind '{kind}' is not supported.", status_code=404)

    from app.services.uav_task_store import validate_uav_task_id

    validate_uav_task_id(task_id)
    outputs_dir = settings.outputs_dir.resolve()
    task_dir = (settings.outputs_dir / task_id).resolve()
    path = (task_dir / UAV_OUTPUT_FILENAMES[kind]).resolve()
    if task_dir != outputs_dir and outputs_dir not in task_dir.parents:
        raise AppError("INVALID_OUTPUT_PATH", "Resolved task directory escapes output directory.", status_code=400)
    if path != task_dir and task_dir not in path.parents:
        raise AppError("INVALID_OUTPUT_PATH", "Resolved output path escapes task directory.", status_code=400)
    return path
