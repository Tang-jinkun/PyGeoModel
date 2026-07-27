from pathlib import Path
from app.core.config import settings
from app.core.errors import AppError
from app.schemas.recon_vehicle import ReconVehicleOutputFile, ReconVehicleOutputKind
from app.services.artifact_contracts import get_output_contract
from app.services.artifact_store import get_artifact_store


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
    contract = get_output_contract("recon_vehicle")
    spec = contract.spec(kind)
    download_path = contract.download_path_template.format(task_id=task_id, kind=kind)
    return ReconVehicleOutputFile(
        kind=kind,
        label=spec.label, url=None, download_path=download_path if exists else None,
        download_url=download_path if exists else None,
        filename=path.name,
        media_type=RECON_VEHICLE_OUTPUT_MEDIA_TYPES[kind],
        size_bytes=path.stat().st_size if exists else None,
        exists=exists,
    )


def describe_recon_vehicle_output_files(task_id: str, files: dict[ReconVehicleOutputKind, Path]) -> list[ReconVehicleOutputFile]:
    return [describe_recon_vehicle_output_file(task_id, kind, path) for kind, path in files.items()]


def list_recon_vehicle_task_output_files(task_id: str) -> list[ReconVehicleOutputFile]:
    return [ReconVehicleOutputFile.model_validate(item.model_dump()) for item in get_artifact_store().list_descriptors(task_id, get_output_contract("recon_vehicle"))]


def resolve_recon_vehicle_task_output_path(task_id: str, kind: ReconVehicleOutputKind) -> Path:
    spec = get_output_contract("recon_vehicle").spec(kind)

    from app.services.recon_vehicle_task_store import validate_recon_vehicle_task_id

    validate_recon_vehicle_task_id(task_id)
    outputs_dir = settings.outputs_dir.resolve()
    task_dir = (settings.outputs_dir / task_id).resolve()
    path = (task_dir / spec.filename).resolve()
    if task_dir != outputs_dir and outputs_dir not in task_dir.parents:
        raise AppError("INVALID_OUTPUT_PATH", "Resolved task directory escapes output directory.", status_code=400)
    if path != task_dir and task_dir not in path.parents:
        raise AppError("INVALID_OUTPUT_PATH", "Resolved output path escapes task directory.", status_code=400)
    return path
