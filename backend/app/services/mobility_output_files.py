from pathlib import Path
from app.core.config import settings
from app.core.errors import AppError
from app.schemas.mobility import MobilityOutputFile, MobilityOutputKind
from app.services.artifact_contracts import get_output_contract
from app.services.artifact_store import get_artifact_store


MOBILITY_OUTPUT_FILENAMES: dict[MobilityOutputKind, str] = {
    "wheeled_path_geojson": "wheeled_path.geojson",
    "tracked_path_geojson": "tracked_path.geojson",
    "road_mask_geojson": "road_mask.geojson",
    "cost_summary_json": "cost_summary.json",
    "model_metadata_json": "model_metadata.json",
    "output_manifest_json": "output_manifest.json",
}

MOBILITY_OUTPUT_MEDIA_TYPES: dict[MobilityOutputKind, str] = {
    "wheeled_path_geojson": "application/geo+json",
    "tracked_path_geojson": "application/geo+json",
    "road_mask_geojson": "application/geo+json",
    "cost_summary_json": "application/json",
    "model_metadata_json": "application/json",
    "output_manifest_json": "application/json",
}

MOBILITY_OUTPUT_LABELS: dict[MobilityOutputKind, str] = {
    "wheeled_path_geojson": "Wheeled Vehicle Path GeoJSON",
    "tracked_path_geojson": "Tracked Vehicle Path GeoJSON",
    "road_mask_geojson": "Road Mask GeoJSON",
    "cost_summary_json": "Mobility Cost Summary JSON",
    "model_metadata_json": "Mobility Model Metadata JSON",
    "output_manifest_json": "Mobility Output Manifest JSON",
}


def describe_mobility_output_file(task_id: str, kind: MobilityOutputKind, path: Path) -> MobilityOutputFile:
    exists = path.exists()
    contract = get_output_contract("mobility")
    spec = contract.spec(kind)
    download_path = contract.download_path_template.format(task_id=task_id, kind=kind)
    return MobilityOutputFile(
        kind=kind,
        label=spec.label, url=None, download_path=download_path if exists else None,
        download_url=download_path if exists else None,
        filename=path.name,
        media_type=MOBILITY_OUTPUT_MEDIA_TYPES[kind],
        size_bytes=path.stat().st_size if exists else None,
        exists=exists,
    )


def describe_mobility_output_files(task_id: str, files: dict[MobilityOutputKind, Path]) -> list[MobilityOutputFile]:
    return [describe_mobility_output_file(task_id, kind, path) for kind, path in files.items()]


def list_mobility_task_output_files(task_id: str) -> list[MobilityOutputFile]:
    return [MobilityOutputFile.model_validate(item.model_dump()) for item in get_artifact_store().list_descriptors(task_id, get_output_contract("mobility"))]


def resolve_mobility_task_output_path(task_id: str, kind: MobilityOutputKind) -> Path:
    spec = get_output_contract("mobility").spec(kind)

    from app.services.mobility_task_store import validate_mobility_task_id

    validate_mobility_task_id(task_id)
    outputs_dir = settings.outputs_dir.resolve()
    task_dir = (settings.outputs_dir / task_id).resolve()
    path = (task_dir / spec.filename).resolve()
    if task_dir != outputs_dir and outputs_dir not in task_dir.parents:
        raise AppError("INVALID_OUTPUT_PATH", "Resolved task directory escapes output directory.", status_code=400)
    if path != task_dir and task_dir not in path.parents:
        raise AppError("INVALID_OUTPUT_PATH", "Resolved output path escapes task directory.", status_code=400)
    return path
