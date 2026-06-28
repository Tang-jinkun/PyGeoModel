import json
import shutil
import subprocess
from pathlib import Path

from pyproj import CRS, Transformer
from rasterio.warp import Resampling, calculate_default_transform, reproject
from shapely.geometry import GeometryCollection, mapping, shape
from shapely.ops import unary_union

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.radar import CoverageMetrics, CoverageOutputs, CoverageRequest
from app.services.dem_store import find_dem_file
from app.services.geometry import make_range_geometry, project_geometry
from app.services.projection import utm_epsg_from_lonlat
from app.services.task_store import mark_failed, mark_finished, mark_running


def run_coverage_task(task_id: str, payload: CoverageRequest) -> None:
    try:
        mark_running(task_id, "Preparing DEM and projection.", 15)
        output_dir = settings.outputs_dir / task_id
        output_dir.mkdir(parents=True, exist_ok=True)

        dem_path = find_dem_file(payload.dem_id)
        epsg = utm_epsg_from_lonlat(payload.radar.lon, payload.radar.lat)
        projected_dem = output_dir / "dem_projected.tif"
        viewshed = output_dir / "viewshed.tif"

        _reproject_dem(dem_path, projected_dem, epsg)
        radar_x, radar_y = _project_radar_point(payload.radar.lon, payload.radar.lat, epsg)

        mark_running(task_id, "Running gdal_viewshed.", 45)
        _run_gdal_viewshed(projected_dem, viewshed, radar_x, radar_y, payload)

        mark_running(task_id, "Vectorizing viewshed outputs.", 80)
        outputs, metrics = _write_vector_outputs(task_id, output_dir, radar_x, radar_y, epsg, payload, viewshed)
        mark_finished(task_id, metrics=metrics, outputs=outputs)
    except Exception as exc:
        mark_failed(task_id, str(exc))


def _reproject_dem(source: Path, destination: Path, epsg: int) -> None:
    try:
        import rasterio
    except ImportError as exc:
        raise AppError("RASTERIO_NOT_INSTALLED", "Rasterio is required for DEM reprojection.", status_code=500) from exc

    with rasterio.open(source) as src:
        dst_crs = CRS.from_epsg(epsg)
        transform, width, height = calculate_default_transform(
            src.crs,
            dst_crs,
            src.width,
            src.height,
            *src.bounds,
        )
        kwargs = src.meta.copy()
        kwargs.update({"crs": dst_crs, "transform": transform, "width": width, "height": height})

        with rasterio.open(destination, "w", **kwargs) as dst:
            for band_index in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, band_index),
                    destination=rasterio.band(dst, band_index),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=dst_crs,
                    resampling=Resampling.bilinear,
                )


def _project_radar_point(lon: float, lat: float, epsg: int) -> tuple[float, float]:
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    return transformer.transform(lon, lat)


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
    radar_x: float,
    radar_y: float,
    epsg: int,
    payload: CoverageRequest,
    viewshed: Path,
) -> tuple[CoverageOutputs, CoverageMetrics]:
    range_geom = make_range_geometry(
        radar_x,
        radar_y,
        payload.coverage.max_range_m,
        payload.coverage.scan_mode,
        payload.coverage.azimuth_deg,
        payload.coverage.beam_width_deg,
    )
    transformer = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    range_wgs84 = project_geometry(range_geom, transformer)
    visible_geom = _vectorize_visible_viewshed(viewshed)
    visible_clipped = visible_geom.intersection(range_geom)
    blocked_geom = range_geom.difference(visible_clipped)

    tolerance = payload.advanced.output_simplify_tolerance_m
    if tolerance is None:
        tolerance = 0
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


def _vectorize_visible_viewshed(viewshed: Path):
    try:
        import rasterio
        from rasterio import features
    except ImportError as exc:
        raise AppError("RASTERIO_NOT_INSTALLED", "Rasterio is required for viewshed vectorization.", status_code=500) from exc

    with rasterio.open(viewshed) as dataset:
        data = dataset.read(1)
        mask = data > 0
        geometries = [
            shape(geom)
            for geom, value in features.shapes(data, mask=mask, transform=dataset.transform)
            if value > 0
        ]

    if not geometries:
        return GeometryCollection()
    return unary_union(geometries)


def _write_feature_collection(path: Path, geometry, properties: dict[str, str]) -> None:
    features = []
    if geometry is not None and not geometry.is_empty:
        features.append({"type": "Feature", "properties": properties, "geometry": mapping(geometry)})

    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
        encoding="utf-8",
    )
