import math

import rasterio
from pyproj import CRS, Transformer

from app.core.errors import AppError
from app.schemas.radar import TargetEvaluationRequest, TargetEvaluationResult
from app.services.coverage_range import effective_max_range
from app.services.dem_store import find_dem_file
from app.services.output_files import resolve_task_output_path
from app.services.projection import utm_epsg_from_lonlat
from app.services.task_store import get_task


def evaluate_coverage_target(
    task_id: str,
    target: TargetEvaluationRequest,
) -> TargetEvaluationResult:
    task = get_task(task_id)
    if task.status != "finished":
        raise AppError(
            "TASK_NOT_FINISHED",
            "Target evaluation is available only after the task is finished.",
            status_code=409,
        )
    if task.request is None:
        raise AppError(
            "TASK_WITHOUT_REQUEST",
            "Task request parameters are missing.",
            status_code=409,
        )

    payload = task.request
    target_epsg = (
        task.model.target_epsg
        if task.model is not None
        else utm_epsg_from_lonlat(payload.radar.lon, payload.radar.lat)
    )
    projected_crs = CRS.from_epsg(target_epsg)
    input_crs = CRS.from_epsg(4326)
    to_projected = Transformer.from_crs(
        input_crs, projected_crs, always_xy=True
    )
    projected_x, projected_y = to_projected.transform(target.x, target.y)
    if not all(math.isfinite(value) for value in (projected_x, projected_y)):
        raise AppError(
            "TARGET_COORDINATES_INVALID",
            "Target coordinates could not be transformed to finite values.",
            status_code=400,
        )

    from_wgs84 = Transformer.from_crs(
        "EPSG:4326", projected_crs, always_xy=True
    )
    radar_x, radar_y = from_wgs84.transform(
        payload.radar.lon, payload.radar.lat
    )
    radar_ground_m = _sample_source_dem(
        payload.dem_id,
        payload.radar.lon,
        payload.radar.lat,
        input_is_wgs84=True,
    )
    if radar_ground_m is None:
        raise AppError(
            "RADAR_DEM_UNAVAILABLE",
            "Radar terrain elevation is unavailable.",
            status_code=409,
        )
    radar_altitude_m = radar_ground_m + payload.radar.height_m

    dx = projected_x - radar_x
    dy = projected_y - radar_y
    distance_m = math.hypot(dx, dy)
    vertical_delta_m = target.z - radar_altitude_m
    slant_range_m = math.hypot(distance_m, vertical_delta_m)
    azimuth_deg = (math.degrees(math.atan2(dx, dy)) + 360) % 360
    elevation_deg = math.degrees(math.atan2(vertical_delta_m, distance_m))
    range_m, _ = effective_max_range(payload)
    within_range = slant_range_m <= range_m
    within_beam = _inside_sector(azimuth_deg, payload)
    within_elevation = (
        payload.advanced.min_elevation_deg
        <= elevation_deg
        <= payload.advanced.max_elevation_deg
    )

    maximum_altitude_m = radar_altitude_m + math.sqrt(
        max(0.0, range_m**2 - distance_m**2)
    )
    if payload.advanced.max_elevation_deg < 90:
        maximum_altitude_m = min(
            maximum_altitude_m,
            radar_altitude_m
            + distance_m
            * math.tan(math.radians(payload.advanced.max_elevation_deg)),
        )

    terrain_m, terrain_state = _sample_target_terrain(
        payload.dem_id,
        projected_crs,
        projected_x,
        projected_y,
    )
    minimum_height_m, threshold_state = _sample_minimum_height(
        task_id,
        projected_crs,
        projected_x,
        projected_y,
    )
    within_dem = terrain_m is not None and minimum_height_m is not None
    minimum_altitude_m = None
    target_height_agl_m = None
    terrain_blocked = False
    if within_dem:
        target_height_agl_m = target.z - terrain_m
        visibility_floor_m = terrain_m + minimum_height_m
        elevation_floor_m = radar_altitude_m + distance_m * math.tan(
            math.radians(payload.advanced.min_elevation_deg)
        )
        minimum_altitude_m = max(visibility_floor_m, elevation_floor_m)
        terrain_blocked = target.z < visibility_floor_m

    reason = _evaluation_reason(
        within_range=within_range,
        within_beam=within_beam,
        elevation_deg=elevation_deg,
        min_elevation_deg=payload.advanced.min_elevation_deg,
        max_elevation_deg=payload.advanced.max_elevation_deg,
        terrain_state=terrain_state,
        threshold_state=threshold_state,
        target_z=target.z,
        terrain_m=terrain_m,
        terrain_blocked=terrain_blocked,
    )
    detectable = reason == "detectable"

    return TargetEvaluationResult(
        task_id=task_id,
        detectable=detectable,
        reason=reason,
        target_type=target.target_type,
        target_crs="EPSG:4326",
        projected_crs=projected_crs.to_string(),
        input_x=target.x,
        input_y=target.y,
        input_z=target.z,
        projected_x=projected_x,
        projected_y=projected_y,
        distance_m=distance_m,
        slant_range_m=slant_range_m,
        azimuth_deg=azimuth_deg,
        elevation_deg=elevation_deg,
        radar_altitude_m=radar_altitude_m,
        terrain_elevation_m=terrain_m,
        target_height_agl_m=target_height_agl_m,
        minimum_detectable_altitude_m=minimum_altitude_m,
        maximum_detectable_altitude_m=maximum_altitude_m,
        within_range=within_range,
        within_beam=within_beam,
        within_elevation=within_elevation,
        within_dem=within_dem,
        terrain_blocked=terrain_blocked,
    )


def _sample_source_dem(
    dem_id: str,
    x: float,
    y: float,
    *,
    input_is_wgs84: bool = False,
) -> float | None:
    with rasterio.open(find_dem_file(dem_id)) as dataset:
        if dataset.crs is None:
            return None
        if input_is_wgs84:
            transformer = Transformer.from_crs(
                "EPSG:4326", dataset.crs, always_xy=True
            )
            x, y = transformer.transform(x, y)
        return _sample_dataset(dataset, x, y)[0]


def _sample_target_terrain(
    dem_id: str,
    source_crs: CRS,
    x: float,
    y: float,
) -> tuple[float | None, str]:
    with rasterio.open(find_dem_file(dem_id)) as dataset:
        if dataset.crs is None:
            return None, "nodata"
        transformer = Transformer.from_crs(
            source_crs, dataset.crs, always_xy=True
        )
        dem_x, dem_y = transformer.transform(x, y)
        return _sample_dataset(dataset, dem_x, dem_y)


def _sample_minimum_height(
    task_id: str,
    source_crs: CRS,
    x: float,
    y: float,
) -> tuple[float | None, str]:
    path = resolve_task_output_path(task_id, "min_visible_height_tif")
    if not path.exists():
        raise AppError(
            "MIN_VISIBLE_HEIGHT_NOT_FOUND",
            "The task does not contain minimum visible height output.",
            status_code=409,
        )
    with rasterio.open(path) as dataset:
        if dataset.crs is None:
            return None, "nodata"
        transformer = Transformer.from_crs(
            source_crs, dataset.crs, always_xy=True
        )
        raster_x, raster_y = transformer.transform(x, y)
        return _sample_dataset(dataset, raster_x, raster_y)


def _sample_dataset(dataset, x: float, y: float) -> tuple[float | None, str]:
    row, column = dataset.index(x, y)
    if row < 0 or column < 0 or row >= dataset.height or column >= dataset.width:
        return None, "outside"
    value = float(next(dataset.sample([(x, y)]))[0])
    nodata = dataset.nodata
    if not math.isfinite(value) or (
        nodata is not None and math.isclose(value, float(nodata))
    ):
        return None, "nodata"
    return value, "valid"


def _inside_sector(azimuth_deg: float, payload) -> bool:
    if payload.coverage.scan_mode == "omni" or payload.coverage.beam_width_deg >= 360:
        return True
    delta = abs(
        (azimuth_deg - payload.coverage.azimuth_deg + 180) % 360 - 180
    )
    return delta <= payload.coverage.beam_width_deg / 2


def _evaluation_reason(
    *,
    within_range: bool,
    within_beam: bool,
    elevation_deg: float,
    min_elevation_deg: float,
    max_elevation_deg: float,
    terrain_state: str,
    threshold_state: str,
    target_z: float,
    terrain_m: float | None,
    terrain_blocked: bool,
) -> str:
    if not within_range:
        return "outside_range"
    if not within_beam:
        return "outside_sector"
    if elevation_deg < min_elevation_deg:
        return "below_min_elevation"
    if elevation_deg > max_elevation_deg:
        return "above_max_elevation"
    if "outside" in {terrain_state, threshold_state}:
        return "outside_dem"
    if "nodata" in {terrain_state, threshold_state}:
        return "dem_nodata"
    if terrain_m is not None and target_z < terrain_m:
        return "below_terrain"
    if terrain_blocked:
        return "terrain_blocked"
    return "detectable"
