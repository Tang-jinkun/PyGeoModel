import json
import shutil
import subprocess
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import mapping

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.radar import CoverageMetrics, CoverageOutputs, CoverageRequest
from app.services.dem_store import find_dem_file
from app.services.coverage_model import (
    PreparedCoverageDem,
    default_simplify_tolerance,
    prepare_coverage_dem,
    vectorize_visible_viewshed,
)
from app.services.geometry import make_range_geometry, project_geometry
from app.services.task_store import mark_failed, mark_finished, mark_running


def run_coverage_task(task_id: str, payload: CoverageRequest) -> None:
    try:
        mark_running(task_id, "Preparing DEM and projection.", 15)
        output_dir = settings.outputs_dir / task_id
        output_dir.mkdir(parents=True, exist_ok=True)

        dem_path = find_dem_file(payload.dem_id)
        projected_dem = output_dir / "dem_projected.tif"
        viewshed = output_dir / "viewshed.tif"

        prepared = prepare_coverage_dem(dem_path, projected_dem, payload)

        mark_running(task_id, "Running gdal_viewshed.", 45)
        _run_gdal_viewshed(projected_dem, viewshed, prepared.radar_x, prepared.radar_y, payload)

        mark_running(task_id, "Vectorizing viewshed outputs.", 80)
        outputs, metrics = _write_vector_outputs(task_id, output_dir, prepared, payload, viewshed)
        mark_finished(task_id, metrics=metrics, outputs=outputs)
    except Exception as exc:
        mark_failed(task_id, str(exc))


def _run_gdal_viewshed(dem: Path, viewshed: Path, radar_x: float, radar_y: float, payload: CoverageRequest) -> None:
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


def _write_vector_outputs(
    task_id: str,
    output_dir: Path,
    prepared: PreparedCoverageDem,
    payload: CoverageRequest,
    viewshed: Path,
) -> tuple[CoverageOutputs, CoverageMetrics]:
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

    range_geojson = output_dir / "radar_range.geojson"
    visible_geojson = output_dir / "visible.geojson"
    blocked_geojson = output_dir / "blocked.geojson"

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
    )
    return outputs, metrics


def _write_feature_collection(path: Path, geometry, properties: dict[str, str]) -> None:
    features = []
    if geometry is not None and not geometry.is_empty:
        features.append({"type": "Feature", "properties": properties, "geometry": mapping(geometry)})

    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
        encoding="utf-8",
    )
