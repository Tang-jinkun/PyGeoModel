import json
import math
import os
import shutil
from pathlib import Path
from uuid import uuid4

import numpy
from pyproj import CRS, Transformer
from rasterio.features import shapes
from rasterio.transform import array_bounds
from rasterio.windows import from_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds
from shapely.geometry import GeometryCollection, LineString, MultiPoint, Point, mapping, shape
from shapely.ops import unary_union

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.artillery import (
    ArtilleryCoverageMetrics,
    ArtilleryCoverageOutputs,
    ArtilleryCoverageRequest,
    ArtilleryModelMetadata,
)
from app.services.artillery_output_files import (
    ARTILLERY_OUTPUT_FILENAMES,
    describe_artillery_output_files,
    list_artillery_task_output_files,
)
from app.services.artillery_task_store import mark_artillery_failed, mark_artillery_finished, mark_artillery_running
from app.services.dem_store import find_dem_file
from app.services.geometry import make_range_geometry, project_geometry
from app.services.projection import utm_epsg_from_lonlat

GRAVITY_MPS2 = 9.80665


class PreparedArtilleryDem:
    def __init__(
        self,
        projected_dem: Path,
        target_epsg: int,
        battery_x: float,
        battery_y: float,
        bounds,
        resolution_m: tuple[float, float],
    ) -> None:
        self.projected_dem = projected_dem
        self.target_epsg = target_epsg
        self.battery_x = battery_x
        self.battery_y = battery_y
        self.bounds = bounds
        self.resolution_m = resolution_m


def run_artillery_task(task_id: str, payload: ArtilleryCoverageRequest) -> None:
    try:
        mark_artillery_running(task_id, "Preparing DEM and artillery projection.", 15)
        output_dir = settings.outputs_dir / task_id
        output_dir.mkdir(parents=True, exist_ok=True)
        staging_dir = output_dir / f".staging-{uuid4().hex}"
        staging_dir.mkdir(parents=True, exist_ok=False)

        try:
            prepared = _prepare_artillery_dem(find_dem_file(payload.dem_id), staging_dir / "dem_projected.tif", payload)
            mark_artillery_running(task_id, "Computing terrain-masked trajectories.", 55)
            outputs, output_files, metrics, model, warnings = _write_artillery_outputs(
                task_id, staging_dir, output_dir, prepared, payload
            )
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)

        mark_artillery_finished(task_id, metrics=metrics, outputs=outputs, output_files=output_files, model=model, warnings=warnings)
    except Exception as exc:
        mark_artillery_failed(task_id, str(exc))


def _prepare_artillery_dem(source: Path, destination: Path, payload: ArtilleryCoverageRequest) -> PreparedArtilleryDem:
    import rasterio

    target_epsg = utm_epsg_from_lonlat(payload.battery.lon, payload.battery.lat)
    target_crs = CRS.from_epsg(target_epsg)
    to_target = Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)
    battery_x, battery_y = to_target.transform(payload.battery.lon, payload.battery.lat)

    with rasterio.open(source) as src:
        if src.crs is None:
            raise AppError("DEM_WITHOUT_CRS", "DEM is missing coordinate reference system.")
        src_battery_x, src_battery_y = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True).transform(
            payload.battery.lon, payload.battery.lat
        )
        if not (src.bounds.left <= src_battery_x <= src.bounds.right and src.bounds.bottom <= src_battery_y <= src.bounds.top):
            raise AppError("ARTILLERY_OUTSIDE_DEM", "Artillery battery point is outside DEM bounds.", status_code=400)

        radius = payload.weapon.max_range_m + max(payload.munition.effective_radius_m, payload.munition.lethal_radius_m)
        target_bounds = (battery_x - radius, battery_y - radius, battery_x + radius, battery_y + radius)
        src_crop_bounds = transform_bounds(target_crs, src.crs, *target_bounds, densify_pts=21)
        crop_bounds = (
            max(src.bounds.left, src_crop_bounds[0]),
            max(src.bounds.bottom, src_crop_bounds[1]),
            min(src.bounds.right, src_crop_bounds[2]),
            min(src.bounds.top, src_crop_bounds[3]),
        )
        if crop_bounds[0] >= crop_bounds[2] or crop_bounds[1] >= crop_bounds[3]:
            raise AppError("RANGE_OUTSIDE_DEM", "Artillery range does not intersect DEM bounds.", status_code=400)

        window = from_bounds(*crop_bounds, transform=src.transform).round_offsets().round_lengths()
        crop_transform = src.window_transform(window)
        crop_bounds_exact = array_bounds(int(window.height), int(window.width), crop_transform)
        dst_transform, dst_width, dst_height = calculate_default_transform(
            src.crs,
            target_crs,
            int(window.width),
            int(window.height),
            *crop_bounds_exact,
        )
        if dst_width <= 0 or dst_height <= 0:
            raise AppError("INVALID_DEM", "Projected DEM dimensions are empty.")

        source_data = src.read(1, window=window, masked=True)
        fill_value = src.nodata if src.nodata is not None else 0
        source_array = source_data.filled(fill_value)
        destination_array = numpy.full((dst_height, dst_width), fill_value, dtype=source_array.dtype)

        reproject(
            source=source_array,
            destination=destination_array,
            src_transform=crop_transform,
            src_crs=src.crs,
            src_nodata=src.nodata,
            dst_transform=dst_transform,
            dst_crs=target_crs,
            dst_nodata=src.nodata,
            resampling=Resampling.bilinear,
        )

        metadata = src.meta.copy()
        metadata.update(
            {
                "driver": "GTiff",
                "crs": target_crs,
                "transform": dst_transform,
                "width": dst_width,
                "height": dst_height,
                "count": 1,
                "compress": "deflate",
            }
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(destination, "w", **metadata) as dst:
            dst.write(destination_array, 1)

    projected_bounds_tuple = array_bounds(dst_height, dst_width, dst_transform)
    bounds = type("Bounds", (), {
        "left": projected_bounds_tuple[0],
        "bottom": projected_bounds_tuple[1],
        "right": projected_bounds_tuple[2],
        "top": projected_bounds_tuple[3],
    })()
    return PreparedArtilleryDem(
        projected_dem=destination,
        target_epsg=target_epsg,
        battery_x=battery_x,
        battery_y=battery_y,
        bounds=bounds,
        resolution_m=(abs(dst_transform.a), abs(dst_transform.e)),
    )


def _write_artillery_outputs(
    task_id: str,
    staging_dir: Path,
    output_dir: Path,
    prepared: PreparedArtilleryDem,
    payload: ArtilleryCoverageRequest,
):
    import rasterio

    with rasterio.open(prepared.projected_dem) as src:
        dem = src.read(1)
        transform = src.transform
        nodata = src.nodata

    masks, sample_features, model, metrics = _compute_artillery_masks(dem, transform, nodata, prepared, payload)
    transformer = Transformer.from_crs(f"EPSG:{prepared.target_epsg}", "EPSG:4326", always_xy=True)

    theoretical_geom = _mask_to_geometry(masks["theoretical"], transform)
    reachable_geom = _mask_to_geometry(masks["reachable"], transform)
    masked_geom = _mask_to_geometry(masks["terrain_masked"], transform)
    tolerance = payload.analysis.output_simplify_tolerance_m
    if tolerance is None:
        tolerance = max(prepared.resolution_m)
    if tolerance > 0:
        theoretical_geom = theoretical_geom.simplify(tolerance, preserve_topology=True)
        reachable_geom = reachable_geom.simplify(tolerance, preserve_topology=True)
        masked_geom = masked_geom.simplify(tolerance, preserve_topology=True)

    theoretical_path = staging_dir / "theoretical.geojson"
    reachable_path = staging_dir / "reachable.geojson"
    terrain_masked_path = staging_dir / "terrain_masked.geojson"
    sample_points_path = staging_dir / "sample_points.geojson"
    model_path = staging_dir / "model_metadata.json"
    manifest_path = staging_dir / "output_manifest.json"

    _write_feature_collection(theoretical_path, project_geometry(theoretical_geom, transformer), {"kind": "artillery_theoretical"})
    _write_feature_collection(reachable_path, project_geometry(reachable_geom, transformer), {"kind": "artillery_reachable"})
    _write_feature_collection(terrain_masked_path, project_geometry(masked_geom, transformer), {"kind": "artillery_terrain_masked"})
    _write_sample_points(sample_points_path, sample_features, transformer)

    outputs = ArtilleryCoverageOutputs(
        theoretical_geojson=f"/outputs/{task_id}/theoretical.geojson",
        reachable_geojson=f"/outputs/{task_id}/reachable.geojson",
        terrain_masked_geojson=f"/outputs/{task_id}/terrain_masked.geojson",
        sample_points_geojson=f"/outputs/{task_id}/sample_points.geojson",
        model_metadata_json=f"/outputs/{task_id}/model_metadata.json",
        output_manifest_json=f"/outputs/{task_id}/output_manifest.json",
    )
    _write_json_atomic(model_path, {"model": model.model_dump(), "metrics": metrics.model_dump(), "warnings": []})
    output_paths = {kind: staging_dir / filename for kind, filename in ARTILLERY_OUTPUT_FILENAMES.items()}
    manifest_files = describe_artillery_output_files(task_id, output_paths)
    _write_json_atomic(
        manifest_path,
        {
            "files": [item.model_dump() for item in manifest_files],
            "metrics": metrics.model_dump(),
            "model": model.model_dump(),
            "warnings": [],
        },
    )
    _ensure_staged_outputs_exist(staging_dir)
    _commit_staged_outputs(staging_dir, output_dir)
    output_files = list_artillery_task_output_files(task_id)
    return outputs, output_files, metrics, model, []


def _compute_artillery_masks(dem, transform, nodata, prepared: PreparedArtilleryDem, payload: ArtilleryCoverageRequest):
    height, width = dem.shape
    cols = numpy.arange(width, dtype=numpy.float64)
    rows = numpy.arange(height, dtype=numpy.float64)
    xs = transform.c + (cols + 0.5) * transform.a
    ys = transform.f + (rows + 0.5) * transform.e
    x_grid, y_grid = numpy.meshgrid(xs, ys)
    finite = numpy.isfinite(dem)
    if nodata is not None:
        finite &= dem != nodata

    theoretical_geom = _annular_sector_geometry(prepared, payload)
    theoretical = _geometry_to_mask(theoretical_geom, dem.shape, transform) & finite
    reachable = numpy.zeros_like(theoretical, dtype=bool)
    terrain_masked = numpy.zeros_like(theoretical, dtype=bool)
    sample_features: list[dict] = []
    clearances: list[float] = []

    ground = _sample_nearest(dem, transform, prepared.battery_x, prepared.battery_y, nodata)
    if not math.isfinite(ground):
        raise AppError("ARTILLERY_NO_DATA", "Artillery battery point falls on DEM nodata.", status_code=400)
    battery_altitude = payload.battery.height_m if payload.battery.altitude_mode == "amsl" else ground + payload.battery.height_m
    sample_resolution = payload.analysis.sample_resolution_m or max(prepared.resolution_m) * 4
    candidate_indices = _sample_candidate_indices(theoretical, sample_resolution, transform)

    for row, col in candidate_indices:
        target_x = float(x_grid[row, col])
        target_y = float(y_grid[row, col])
        target_ground = float(dem[row, col]) if payload.analysis.use_dem_elevation else 0.0
        target_z = target_ground + payload.target.target_height_m
        result = _trajectory_clearance(
            dem,
            transform,
            nodata,
            prepared.battery_x,
            prepared.battery_y,
            battery_altitude,
            target_x,
            target_y,
            target_z,
            payload,
        )
        clearances.append(result["min_clearance_m"])
        if result["is_clear"]:
            reachable[row, col] = True
        else:
            terrain_masked[row, col] = True
        sample_features.append(
            {
                "geometry": Point(target_x, target_y),
                "properties": {
                    "kind": "artillery_sample",
                    "is_clear": result["is_clear"],
                    "range_m": result["range_m"],
                    "min_clearance_m": result["min_clearance_m"],
                    "masking_distance_m": result["masking_distance_m"],
                    "trajectory_peak_m": result["trajectory_peak_m"],
                },
            }
        )

    reachable = _expand_sampled_mask(reachable, theoretical, sample_resolution, transform)
    terrain_masked = theoretical & ~reachable if payload.analysis.use_terrain_masking else numpy.zeros_like(theoretical, dtype=bool)
    if not payload.analysis.use_terrain_masking:
        reachable = theoretical.copy()

    cell_area = abs(float(transform.a) * float(transform.e))
    theoretical_area = float(theoretical.sum()) * cell_area
    reachable_area = float(reachable.sum()) * cell_area
    masked_area = float(terrain_masked.sum()) * cell_area
    lethal_area = _area_with_radius(reachable, transform, payload.munition.lethal_radius_m)
    effective_area = _area_with_radius(reachable, transform, payload.munition.effective_radius_m)
    min_clearance = min(clearances) if clearances else None
    mean_clearance = float(sum(clearances) / len(clearances)) if clearances else None
    metrics = ArtilleryCoverageMetrics(
        theoretical_area_m2=theoretical_area,
        reachable_area_m2=reachable_area,
        terrain_masked_area_m2=masked_area,
        terrain_masked_ratio=masked_area / theoretical_area if theoretical_area > 0 else 0,
        lethal_area_m2=lethal_area,
        effective_area_m2=effective_area,
        min_range_m=payload.weapon.min_range_m,
        max_range_m=payload.weapon.max_range_m,
        effective_traverse_deg=payload.weapon.traverse_deg,
        lethal_radius_m=payload.munition.lethal_radius_m,
        effective_radius_m=payload.munition.effective_radius_m,
        sample_point_count=len(sample_features),
        reachable_sample_count=sum(1 for item in sample_features if item["properties"]["is_clear"]),
        masked_sample_count=sum(1 for item in sample_features if not item["properties"]["is_clear"]),
        min_clearance_m=min_clearance,
        mean_clearance_m=mean_clearance,
        battery_ground_elevation_m=float(ground),
        battery_altitude_m=float(battery_altitude),
    )
    model = ArtilleryModelMetadata(
        target_epsg=prepared.target_epsg,
        battery_projected_xy=[prepared.battery_x, prepared.battery_y],
        projected_dem_bounds=[prepared.bounds.left, prepared.bounds.bottom, prepared.bounds.right, prepared.bounds.top],
        projected_dem_resolution_m=[prepared.resolution_m[0], prepared.resolution_m[1]],
        battery_ground_elevation_m=float(ground),
        battery_altitude_m=float(battery_altitude),
        min_range_m=payload.weapon.min_range_m,
        max_range_m=payload.weapon.max_range_m,
        azimuth_deg=payload.weapon.azimuth_deg,
        traverse_deg=payload.weapon.traverse_deg,
        muzzle_velocity_mps=payload.weapon.muzzle_velocity_mps,
        elevation_deg=payload.weapon.elevation_deg,
        target_height_m=payload.target.target_height_m,
        sample_resolution_m=sample_resolution,
        trajectory_samples=payload.analysis.trajectory_samples,
        clearance_margin_m=payload.analysis.clearance_margin_m,
        use_dem_elevation=payload.analysis.use_dem_elevation,
        use_terrain_masking=payload.analysis.use_terrain_masking,
        simplify_tolerance_m=payload.analysis.output_simplify_tolerance_m or max(prepared.resolution_m),
    )
    return {"theoretical": theoretical, "reachable": reachable, "terrain_masked": terrain_masked}, sample_features, model, metrics


def _annular_sector_geometry(prepared: PreparedArtilleryDem, payload: ArtilleryCoverageRequest):
    outer = make_range_geometry(
        prepared.battery_x,
        prepared.battery_y,
        payload.weapon.max_range_m,
        "omni" if payload.weapon.traverse_deg >= 360 else "sector",
        payload.weapon.azimuth_deg,
        payload.weapon.traverse_deg,
    )
    if payload.weapon.min_range_m <= 0:
        return outer
    inner = Point(prepared.battery_x, prepared.battery_y).buffer(payload.weapon.min_range_m, resolution=96)
    return outer.difference(inner)


def _trajectory_clearance(
    dem,
    transform,
    nodata,
    x0: float,
    y0: float,
    z0: float,
    x1: float,
    y1: float,
    z1: float,
    payload: ArtilleryCoverageRequest,
) -> dict:
    distance = math.hypot(x1 - x0, y1 - y0)
    if distance <= 0:
        return {
            "is_clear": True,
            "range_m": 0.0,
            "min_clearance_m": float("inf"),
            "masking_distance_m": None,
            "trajectory_peak_m": z0,
        }

    theta = math.radians(payload.weapon.elevation_deg)
    velocity = payload.weapon.muzzle_velocity_mps
    cos_theta = max(math.cos(theta), 0.001)
    tan_theta = math.tan(theta)
    drop_factor = GRAVITY_MPS2 / (2 * velocity * velocity * cos_theta * cos_theta)
    baseline_error = distance * tan_theta - drop_factor * distance * distance - (z1 - z0)
    samples = payload.analysis.trajectory_samples
    min_clearance = float("inf")
    masking_distance = None
    peak = z0
    for index in range(1, samples):
        t = index / samples
        horizontal = distance * t
        x = x0 + (x1 - x0) * t
        y = y0 + (y1 - y0) * t
        trajectory_z = z0 + horizontal * tan_theta - drop_factor * horizontal * horizontal - baseline_error * t
        peak = max(peak, trajectory_z)
        terrain = _sample_nearest(dem, transform, x, y, nodata)
        if not math.isfinite(terrain):
            continue
        clearance = trajectory_z - terrain - payload.analysis.clearance_margin_m
        min_clearance = min(min_clearance, clearance)
        if payload.analysis.use_terrain_masking and clearance < 0 and masking_distance is None:
            masking_distance = horizontal
    if not math.isfinite(min_clearance):
        min_clearance = 0.0
    return {
        "is_clear": masking_distance is None,
        "range_m": distance,
        "min_clearance_m": float(min_clearance),
        "masking_distance_m": masking_distance,
        "trajectory_peak_m": float(peak),
    }


def _sample_candidate_indices(mask, sample_resolution: float, transform) -> list[tuple[int, int]]:
    rows, cols = numpy.where(mask)
    if rows.size == 0:
        return []
    cell_size = max(abs(float(transform.a)), abs(float(transform.e)), 1)
    stride = max(1, int(round(sample_resolution / cell_size)))
    selected = [(int(row), int(col)) for row, col in zip(rows, cols) if row % stride == 0 and col % stride == 0]
    if selected:
        return selected
    return [(int(rows[index]), int(cols[index])) for index in range(0, rows.size, max(1, rows.size // 5000))]


def _expand_sampled_mask(sample_mask, theoretical, sample_resolution: float, transform):
    if not sample_mask.any():
        return numpy.zeros_like(theoretical, dtype=bool)
    resolution = max(abs(float(transform.a)), abs(float(transform.e)), 1)
    radius = max(sample_resolution * 0.75, resolution)
    points = []
    rows, cols = numpy.where(sample_mask)
    for row, col in zip(rows, cols):
        x = transform.c + (float(col) + 0.5) * transform.a
        y = transform.f + (float(row) + 0.5) * transform.e
        points.append(Point(x, y))
    geometry = MultiPoint(points).buffer(radius, resolution=8)
    return _geometry_to_mask(geometry, theoretical.shape, transform) & theoretical


def _area_with_radius(mask, transform, radius_m: float) -> float:
    if radius_m <= 0 or not mask.any():
        return 0.0
    geometry = _mask_to_geometry(mask, transform).buffer(radius_m, resolution=24)
    buffered = _geometry_to_mask(geometry, mask.shape, transform)
    return float(buffered.sum()) * abs(float(transform.a) * float(transform.e))


def _sample_nearest(dem, transform, x: float, y: float, nodata) -> float:
    col = int((x - transform.c) / transform.a)
    row = int((y - transform.f) / transform.e)
    if row < 0 or col < 0 or row >= dem.shape[0] or col >= dem.shape[1]:
        return float("nan")
    value = float(dem[row, col])
    if nodata is not None and value == nodata:
        return float("nan")
    return value


def _geometry_to_mask(geometry, out_shape, transform):
    from rasterio.features import rasterize

    if geometry is None or geometry.is_empty:
        return numpy.zeros(out_shape, dtype=bool)
    return rasterize([(geometry, 1)], out_shape=out_shape, transform=transform, fill=0, dtype=numpy.uint8).astype(bool)


def _mask_to_geometry(mask, transform):
    geometries = [
        shape(geom)
        for geom, value in shapes(mask.astype(numpy.uint8), mask=mask, transform=transform)
        if value > 0
    ]
    if not geometries:
        return GeometryCollection()
    return unary_union(geometries)


def _write_feature_collection(path: Path, geometry, properties: dict | None = None) -> None:
    features = []
    if geometry is not None and not geometry.is_empty:
        features.append({"type": "Feature", "properties": properties or {}, "geometry": mapping(geometry)})
    _write_json_atomic(path, {"type": "FeatureCollection", "features": features})


def _write_sample_points(path: Path, sample_features: list[dict], transformer: Transformer) -> None:
    features = []
    for item in sample_features:
        geometry = project_geometry(item["geometry"], transformer)
        features.append({"type": "Feature", "properties": item["properties"], "geometry": mapping(geometry)})
    _write_json_atomic(path, {"type": "FeatureCollection", "features": features})


def _ensure_staged_outputs_exist(staging_dir: Path) -> None:
    missing = [
        kind
        for kind, filename in ARTILLERY_OUTPUT_FILENAMES.items()
        if not (staging_dir / filename).exists() or (staging_dir / filename).stat().st_size <= 0
    ]
    if missing:
        raise AppError("OUTPUT_INCOMPLETE", f"Artillery task staged outputs are incomplete: {', '.join(missing)}.", status_code=500)


def _commit_staged_outputs(staging_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename in ARTILLERY_OUTPUT_FILENAMES.values():
        (staging_dir / filename).replace(output_dir / filename)
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
