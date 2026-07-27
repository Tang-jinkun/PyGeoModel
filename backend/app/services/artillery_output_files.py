from pathlib import Path
from app.core.config import settings
from app.core.errors import AppError
from app.schemas.artillery import ArtilleryOutputFile, ArtilleryOutputKind
from app.services.artifact_contracts import get_output_contract
from app.services.artifact_store import get_artifact_store


ARTILLERY_OUTPUT_FILENAMES: dict[ArtilleryOutputKind, str] = {
    "theoretical_geojson": "theoretical.geojson",
    "reachable_geojson": "reachable.geojson",
    "terrain_masked_geojson": "terrain_masked.geojson",
    "sample_points_geojson": "sample_points.geojson",
    "model_metadata_json": "model_metadata.json",
    "output_manifest_json": "output_manifest.json",
}

ARTILLERY_OUTPUT_MEDIA_TYPES: dict[ArtilleryOutputKind, str] = {
    "theoretical_geojson": "application/geo+json",
    "reachable_geojson": "application/geo+json",
    "terrain_masked_geojson": "application/geo+json",
    "sample_points_geojson": "application/geo+json",
    "model_metadata_json": "application/json",
    "output_manifest_json": "application/json",
}

ARTILLERY_OUTPUT_LABELS: dict[ArtilleryOutputKind, str] = {
    "theoretical_geojson": "Artillery Theoretical Coverage GeoJSON",
    "reachable_geojson": "Artillery Terrain-Cleared Coverage GeoJSON",
    "terrain_masked_geojson": "Artillery Terrain-Masked Area GeoJSON",
    "sample_points_geojson": "Artillery Trajectory Sample Points GeoJSON",
    "model_metadata_json": "Artillery Model Metadata JSON",
    "output_manifest_json": "Artillery Output Manifest JSON",
}


def describe_artillery_output_file(task_id: str, kind: ArtilleryOutputKind, path: Path) -> ArtilleryOutputFile:
    exists = path.exists()
    contract = get_output_contract("artillery")
    spec = contract.spec(kind)
    download_path = contract.download_path_template.format(task_id=task_id, kind=kind)
    return ArtilleryOutputFile(
        kind=kind,
        label=spec.label, url=None, download_path=download_path if exists else None,
        download_url=download_path if exists else None,
        filename=path.name,
        media_type=ARTILLERY_OUTPUT_MEDIA_TYPES[kind],
        size_bytes=path.stat().st_size if exists else None,
        exists=exists,
    )


def describe_artillery_output_files(task_id: str, files: dict[ArtilleryOutputKind, Path]) -> list[ArtilleryOutputFile]:
    return [describe_artillery_output_file(task_id, kind, path) for kind, path in files.items()]


def list_artillery_task_output_files(task_id: str) -> list[ArtilleryOutputFile]:
    return [ArtilleryOutputFile.model_validate(item.model_dump()) for item in get_artifact_store().list_descriptors(task_id, get_output_contract("artillery"))]


def resolve_artillery_task_output_path(task_id: str, kind: ArtilleryOutputKind) -> Path:
    spec = get_output_contract("artillery").spec(kind)

    from app.services.artillery_task_store import validate_artillery_task_id

    validate_artillery_task_id(task_id)
    outputs_dir = settings.outputs_dir.resolve()
    task_dir = (settings.outputs_dir / task_id).resolve()
    path = (task_dir / spec.filename).resolve()
    if task_dir != outputs_dir and outputs_dir not in task_dir.parents:
        raise AppError("INVALID_OUTPUT_PATH", "Resolved task directory escapes output directory.", status_code=400)
    if path != task_dir and task_dir not in path.parents:
        raise AppError("INVALID_OUTPUT_PATH", "Resolved output path escapes task directory.", status_code=400)
    return path
