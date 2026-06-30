from pathlib import Path
from typing import get_args

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.recon_vehicle import ReconVehicleOutputFile, ReconVehicleOutputKind


RECON_VEHICLE_OUTPUT_FILENAMES: dict[ReconVehicleOutputKind, str] = {
    "footprint_geojson": "footprint.geojson",
    "visible_geojson": "visible.geojson",
    "blocked_geojson": "blocked.geojson",
    "model_metadata_json": "model_metadata.json",
    "output_manifest_json": "output_manifest.json",
}

RECON_VEHICLE_OUTPUT_MEDIA_TYPES: dict[ReconVehicleOutputKind, str] = {
    "footprint_geojson": "application/geo+json",
    "visible_geojson": "application/geo+json",
    "blocked_geojson": "application/geo+json",
    "model_metadata_json": "application/json",
    "output_manifest_json": "application/json",
}

RECON_VEHICLE_OUTPUT_LABELS: dict[ReconVehicleOutputKind, str] = {
    "footprint_geojson": "Recon Vehicle Sensor Footprint GeoJSON",
    "visible_geojson": "Recon Vehicle Visible Area GeoJSON",
    "blocked_geojson": "Recon Vehicle Terrain Blocked Area GeoJSON",
    "model_metadata_json": "Recon Vehicle Model Metadata JSON",
    "output_manifest_json": "Recon Vehicle Output Manifest JSON",
}


def describe_recon_vehicle_output_file(task_id: str, kind: ReconVehicleOutputKind, path: Path) -> ReconVehicleOutputFile:
    exists = path.exists()
    return ReconVehicleOutputFile(
        kind=kind,
        label=RECON_VEHICLE_OUTPUT_LABELS[kind],
        url=f"/outputs/{task_id}/{path.name}",
        download_url=f"/api/recon-vehicle/coverage/{task_id}/outputs/{kind}",
        filename=path.name,
        media_type=RECON_VEHICLE_OUTPUT_MEDIA_TYPES[kind],
        size_bytes=path.stat().st_size if exists else None,
        exists=exists,
    )


def describe_recon_vehicle_output_files(task_id: str, files: dict[ReconVehicleOutputKind, Path]) -> list[ReconVehicleOutputFile]:
    return [describe_recon_vehicle_output_file(task_id, kind, path) for kind, path in files.items()]


def list_recon_vehicle_task_output_files(task_id: str) -> list[ReconVehicleOutputFile]:
    return describe_recon_vehicle_output_files(
        task_id,
        {kind: resolve_recon_vehicle_task_output_path(task_id, kind) for kind in get_args(ReconVehicleOutputKind)},
    )


def resolve_recon_vehicle_task_output_path(task_id: str, kind: ReconVehicleOutputKind) -> Path:
    if kind not in RECON_VEHICLE_OUTPUT_FILENAMES:
        raise AppError("OUTPUT_KIND_NOT_FOUND", f"Output kind '{kind}' is not supported.", status_code=404)

    from app.services.recon_vehicle_task_store import validate_recon_vehicle_task_id

    validate_recon_vehicle_task_id(task_id)
    outputs_dir = settings.outputs_dir.resolve()
    task_dir = (settings.outputs_dir / task_id).resolve()
    path = (task_dir / RECON_VEHICLE_OUTPUT_FILENAMES[kind]).resolve()
    if task_dir != outputs_dir and outputs_dir not in task_dir.parents:
        raise AppError("INVALID_OUTPUT_PATH", "Resolved task directory escapes output directory.", status_code=400)
    if path != task_dir and task_dir not in path.parents:
        raise AppError("INVALID_OUTPUT_PATH", "Resolved output path escapes task directory.", status_code=400)
    return path
