from pathlib import Path
from typing import get_args

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.air_corridor import AirCorridorOutputFile, AirCorridorOutputKind


AIR_CORRIDOR_OUTPUT_FILENAMES: dict[AirCorridorOutputKind, str] = {
    "corridor_path_geojson": "corridor_path.geojson",
    "corridor_buffer_geojson": "corridor_buffer.geojson",
    "threat_zones_geojson": "threat_zones.geojson",
    "risk_samples_geojson": "risk_samples.geojson",
    "cost_summary_json": "cost_summary.json",
    "model_metadata_json": "model_metadata.json",
    "output_manifest_json": "output_manifest.json",
}

AIR_CORRIDOR_OUTPUT_MEDIA_TYPES: dict[AirCorridorOutputKind, str] = {
    "corridor_path_geojson": "application/geo+json",
    "corridor_buffer_geojson": "application/geo+json",
    "threat_zones_geojson": "application/geo+json",
    "risk_samples_geojson": "application/geo+json",
    "cost_summary_json": "application/json",
    "model_metadata_json": "application/json",
    "output_manifest_json": "application/json",
}

AIR_CORRIDOR_OUTPUT_LABELS: dict[AirCorridorOutputKind, str] = {
    "corridor_path_geojson": "Air Corridor Path GeoJSON",
    "corridor_buffer_geojson": "Air Corridor Buffer GeoJSON",
    "threat_zones_geojson": "Air Defense Threat Zones GeoJSON",
    "risk_samples_geojson": "Air Corridor Risk Samples GeoJSON",
    "cost_summary_json": "Air Corridor Cost Summary JSON",
    "model_metadata_json": "Air Corridor Model Metadata JSON",
    "output_manifest_json": "Air Corridor Output Manifest JSON",
}


def describe_air_corridor_output_file(task_id: str, kind: AirCorridorOutputKind, path: Path) -> AirCorridorOutputFile:
    exists = path.exists()
    return AirCorridorOutputFile(
        kind=kind,
        label=AIR_CORRIDOR_OUTPUT_LABELS[kind],
        url=f"/outputs/{task_id}/{path.name}",
        download_url=f"/api/air-corridor/planning/{task_id}/outputs/{kind}",
        filename=path.name,
        media_type=AIR_CORRIDOR_OUTPUT_MEDIA_TYPES[kind],
        size_bytes=path.stat().st_size if exists else None,
        exists=exists,
    )


def describe_air_corridor_output_files(task_id: str, files: dict[AirCorridorOutputKind, Path]) -> list[AirCorridorOutputFile]:
    return [describe_air_corridor_output_file(task_id, kind, path) for kind, path in files.items()]


def list_air_corridor_task_output_files(task_id: str) -> list[AirCorridorOutputFile]:
    return describe_air_corridor_output_files(
        task_id,
        {kind: resolve_air_corridor_task_output_path(task_id, kind) for kind in get_args(AirCorridorOutputKind)},
    )


def resolve_air_corridor_task_output_path(task_id: str, kind: AirCorridorOutputKind) -> Path:
    if kind not in AIR_CORRIDOR_OUTPUT_FILENAMES:
        raise AppError("OUTPUT_KIND_NOT_FOUND", f"Output kind '{kind}' is not supported.", status_code=404)

    from app.services.air_corridor_task_store import validate_air_corridor_task_id

    validate_air_corridor_task_id(task_id)
    outputs_dir = settings.outputs_dir.resolve()
    task_dir = (settings.outputs_dir / task_id).resolve()
    path = (task_dir / AIR_CORRIDOR_OUTPUT_FILENAMES[kind]).resolve()
    if task_dir != outputs_dir and outputs_dir not in task_dir.parents:
        raise AppError("INVALID_OUTPUT_PATH", "Resolved task directory escapes output directory.", status_code=400)
    if path != task_dir and task_dir not in path.parents:
        raise AppError("INVALID_OUTPUT_PATH", "Resolved output path escapes task directory.", status_code=400)
    return path
