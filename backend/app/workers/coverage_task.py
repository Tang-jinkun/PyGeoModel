import json
import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

from pyproj import Transformer
from shapely.geometry import box, mapping

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.radar import CoverageMetrics, CoverageModelMetadata, CoverageOutputFile, CoverageOutputs, CoverageRequest
from app.services.dem_store import find_dem_file
from app.services.coverage_model import (
    PreparedCoverageDem,
    default_simplify_tolerance,
    prepare_coverage_dem,
    vectorize_visible_viewshed,
)
from app.services.geometry import make_range_geometry, project_geometry
from app.services.output_files import OUTPUT_FILENAMES, describe_output_files, list_task_output_files
from app.services.task_store import mark_failed, mark_finished, mark_running


def run_coverage_task(task_id: str, payload: CoverageRequest) -> None:
    try:
        mark_running(task_id, "Preparing DEM and projection.", 15)
        output_dir = settings.outputs_dir / task_id
        output_dir.mkdir(parents=True, exist_ok=True)
        staging_dir = output_dir / f".staging-{uuid4().hex}"
        staging_dir.mkdir(parents=True, exist_ok=False)

        dem_path = find_dem_file(payload.dem_id)
        projected_dem = staging_dir / "dem_projected.tif"
        viewshed = staging_dir / "viewshed.tif"

        try:
            prepared = prepare_coverage_dem(dem_path, projected_dem, payload)

            mark_running(task_id, "Running gdal_viewshed.", 45)
            gdal_command = _run_gdal_viewshed(projected_dem, viewshed, prepared.radar_x, prepared.radar_y, payload)

            mark_running(task_id, "Vectorizing viewshed outputs.", 80)
            outputs, output_files, metrics, model, warnings = _write_vector_outputs(
                task_id,
                staging_dir,
                output_dir,
                prepared,
                payload,
                viewshed,
                gdal_command,
            )
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)
        mark_finished(
            task_id,
            metrics=metrics,
            outputs=outputs,
            output_files=output_files,
            model=model,
            warnings=warnings,
        )
    except Exception as exc:
        mark_failed(task_id, str(exc))


def _run_gdal_viewshed(dem: Path, viewshed: Path, radar_x: float, radar_y: float, payload: CoverageRequest) -> list[str]:
    if shutil.which("gdal_viewshed") is None:
        raise AppError("GDAL_VIEWSHED_NOT_FOUND", "gdal_viewshed command is not available.", status_code=500)

    command = [
        "gdal_viewshed",
        "-ox",
        str(radar_x),
        "-oy",
        str(radar_y),
        "-oz",
        str(payload.radar.height_m),
        "-tz",
        str(payload.target.height_m),
        "-md",
        str(payload.coverage.max_range_m),
        "-om",
        "NORMAL",
    ]

    if payload.advanced.use_curvature:
        command.extend(["-cc", str(payload.advanced.curvature_coeff)])

    command.extend([str(dem), str(viewshed)])
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AppError("GDAL_VIEWSHED_FAILED", result.stderr.strip() or "gdal_viewshed failed.", status_code=500)
    return command


def _write_vector_outputs(
    task_id: str,
    staging_dir: Path,
    output_dir: Path,
    prepared: PreparedCoverageDem,
    payload: CoverageRequest,
    viewshed: Path,
    gdal_command: list[str],
) -> tuple[CoverageOutputs, list[CoverageOutputFile], CoverageMetrics, CoverageModelMetadata, list[str]]:
    range_geom = make_range_geometry(
        prepared.radar_x,
        prepared.radar_y,
        payload.coverage.max_range_m,
        payload.coverage.scan_mode,
        payload.coverage.azimuth_deg,
        payload.coverage.beam_width_deg,
    )
    transformer = Transformer.from_crs(f"EPSG:{prepared.target_epsg}", "EPSG:4326", always_xy=True)
    range_wgs84 = project_geometry(range_geom, transformer)
    visible_geom = vectorize_visible_viewshed(viewshed)
    visible_clipped = visible_geom.intersection(range_geom)
    blocked_geom = range_geom.difference(visible_clipped)

    tolerance = default_simplify_tolerance(prepared.resolution_m, payload.advanced.output_simplify_tolerance_m)
    if tolerance > 0:
        visible_clipped = visible_clipped.simplify(tolerance, preserve_topology=True)
        blocked_geom = blocked_geom.simplify(tolerance, preserve_topology=True)

    range_geojson = staging_dir / "radar_range.geojson"
    visible_geojson = staging_dir / "visible.geojson"
    blocked_geojson = staging_dir / "blocked.geojson"
    model_metadata_json = staging_dir / "model_metadata.json"
    output_manifest_json = staging_dir / "output_manifest.json"

    _write_feature_collection(range_geojson, range_wgs84, {"kind": "theoretical_range"})
    _write_feature_collection(
        visible_geojson,
        project_geometry(visible_clipped, transformer),
        {"kind": "visible"},
    )
    _write_feature_collection(
        blocked_geojson,
        project_geometry(blocked_geom, transformer),
        {"kind": "blocked"},
    )

    theoretical_area = float(range_geom.area)
    visible_area = float(visible_clipped.area)
    blocked_area = float(blocked_geom.area)
    metrics = CoverageMetrics(
        theoretical_area_m2=theoretical_area,
        visible_area_m2=visible_area,
        blocked_area_m2=blocked_area,
        blocked_ratio=blocked_area / theoretical_area if theoretical_area else 0,
    )
    outputs = CoverageOutputs(
        viewshed_tif=f"/outputs/{task_id}/{viewshed.name}",
        visible_geojson=f"/outputs/{task_id}/{visible_geojson.name}",
        blocked_geojson=f"/outputs/{task_id}/{blocked_geojson.name}",
        range_geojson=f"/outputs/{task_id}/{range_geojson.name}",
        model_metadata_json=f"/outputs/{task_id}/{model_metadata_json.name}",
        output_manifest_json=f"/outputs/{task_id}/{output_manifest_json.name}",
    )
    warnings = _build_model_warnings(prepared, range_geom)
    model = CoverageModelMetadata(
        target_epsg=prepared.target_epsg,
        radar_projected_xy=[prepared.radar_x, prepared.radar_y],
        projected_dem_bounds=[
            prepared.projected_bounds.left,
            prepared.projected_bounds.bottom,
            prepared.projected_bounds.right,
            prepared.projected_bounds.top,
        ],
        projected_dem_resolution_m=[prepared.resolution_m[0], prepared.resolution_m[1]],
        max_range_m=payload.coverage.max_range_m,
        scan_mode=payload.coverage.scan_mode,
        azimuth_deg=payload.coverage.azimuth_deg,
        beam_width_deg=payload.coverage.beam_width_deg,
        simplify_tolerance_m=tolerance,
        gdal_viewshed_command=gdal_command,
    )
    _write_json_atomic(
        model_metadata_json,
        {
            "model": model.model_dump(),
            "metrics": metrics.model_dump(),
            "warnings": warnings,
        },
    )
    output_paths = {
        kind: staging_dir / filename
        for kind, filename in OUTPUT_FILENAMES.items()
    }
    _write_output_manifest(output_manifest_json, [], metrics, model, warnings)
    manifest_files = describe_output_files(task_id, output_paths)
    _write_output_manifest(output_manifest_json, manifest_files, metrics, model, warnings)
    _ensure_staged_outputs_exist(staging_dir)
    _commit_staged_outputs(staging_dir, output_dir)
    output_files = list_task_output_files(task_id)
    _ensure_finished_outputs_exist(output_files)
    return outputs, output_files, metrics, model, warnings


def _write_output_manifest(
    path: Path,
    output_files: list[CoverageOutputFile],
    metrics: CoverageMetrics,
    model: CoverageModelMetadata,
    warnings: list[str],
) -> None:
    _write_json_atomic(
        path,
        {
            "files": [item.model_dump() for item in output_files],
            "metrics": metrics.model_dump(),
            "model": model.model_dump(),
            "warnings": warnings,
        },
    )


def _build_model_warnings(prepared: PreparedCoverageDem, range_geom) -> list[str]:
    warnings: list[str] = []
    dem_bounds_geom = box(
        prepared.projected_bounds.left,
        prepared.projected_bounds.bottom,
        prepared.projected_bounds.right,
        prepared.projected_bounds.top,
    )
    if not dem_bounds_geom.contains(range_geom):
        warnings.append("Requested radar range is not fully covered by the available DEM extent.")
    return warnings


def _write_feature_collection(path: Path, geometry, properties: dict[str, str]) -> None:
    features = []
    if geometry is not None and not geometry.is_empty:
        features.append({"type": "Feature", "properties": properties, "geometry": mapping(geometry)})

    _write_json_atomic(path, {"type": "FeatureCollection", "features": features})


def _ensure_finished_outputs_exist(output_files: list[CoverageOutputFile]) -> None:
    missing = [item.kind for item in output_files if not item.exists or item.size_bytes is None or item.size_bytes <= 0]
    if missing:
        raise AppError(
            "OUTPUT_INCOMPLETE",
            f"Coverage task outputs are incomplete: {', '.join(missing)}.",
            status_code=500,
        )


def _ensure_staged_outputs_exist(staging_dir: Path) -> None:
    missing = [
        kind
        for kind, filename in OUTPUT_FILENAMES.items()
        if not (staging_dir / filename).exists() or (staging_dir / filename).stat().st_size <= 0
    ]
    if missing:
        raise AppError(
            "OUTPUT_INCOMPLETE",
            f"Coverage task staged outputs are incomplete: {', '.join(missing)}.",
            status_code=500,
        )


def _commit_staged_outputs(staging_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename in OUTPUT_FILENAMES.values():
        source = staging_dir / filename
        destination = output_dir / filename
        source.replace(destination)
    _fsync_directory(output_dir)


def _write_json_atomic(path: Path, payload: dict) -> None:
    _write_text_atomic(path, json.dumps(payload, ensure_ascii=False, indent=2))


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        temp_path.replace(path)
        _fsync_directory(path.parent)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
