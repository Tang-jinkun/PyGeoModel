import math

from pyproj import Transformer

from app.core.errors import AppError
from app.schemas.radar import CoverageProfileResult, CoverageProfileSample
from app.services.dem_store import find_dem_file
from app.services.projection import utm_epsg_from_lonlat
from app.services.task_store import get_task
from app.workers.coverage_task import _effective_max_range

EARTH_RADIUS_M = 6_371_000.0


def analyze_coverage_profile(task_id: str, lon: float, lat: float, samples: int = 160) -> CoverageProfileResult:
    task = get_task(task_id)
    if task.status != "finished":
        raise AppError("TASK_NOT_FINISHED", "Coverage profiles are available only after the task is finished.", status_code=409)
    if task.request is None:
        raise AppError("TASK_WITHOUT_REQUEST", "Task request parameters are missing.", status_code=409)

    payload = task.request
    sample_count = min(400, max(16, samples))
    dem_path = find_dem_file(payload.dem_id)
    target_epsg = utm_epsg_from_lonlat(payload.radar.lon, payload.radar.lat)

    try:
        import rasterio
    except ImportError as exc:
        raise AppError("RASTERIO_NOT_INSTALLED", "Rasterio is required to analyze terrain profiles.", status_code=500) from exc

    try:
        with rasterio.open(dem_path) as dataset:
            if dataset.crs is None:
                raise AppError("DEM_WITHOUT_CRS", "DEM is missing coordinate reference system.")

            to_projected = Transformer.from_crs("EPSG:4326", f"EPSG:{target_epsg}", always_xy=True)
            from_projected = Transformer.from_crs(f"EPSG:{target_epsg}", "EPSG:4326", always_xy=True)
            to_dem = Transformer.from_crs("EPSG:4326", dataset.crs, always_xy=True)

            radar_x, radar_y = to_projected.transform(payload.radar.lon, payload.radar.lat)
            target_x, target_y = to_projected.transform(lon, lat)
            dx = target_x - radar_x
            dy = target_y - radar_y
            distance_m = math.hypot(dx, dy)
            if not math.isfinite(distance_m) or distance_m <= 1:
                raise AppError("PROFILE_TARGET_TOO_CLOSE", "Profile target is too close to the radar.", status_code=400)

            radar_ground_m = _sample_elevation(dataset, to_dem, payload.radar.lon, payload.radar.lat, "radar")
            target_ground_m = _sample_elevation(dataset, to_dem, lon, lat, "target")
            radar_altitude_m = radar_ground_m + payload.radar.height_m
            target_altitude_m = target_ground_m + payload.target.height_m
            azimuth_deg = (math.degrees(math.atan2(dx, dy)) + 360) % 360
            elevation_deg = math.degrees(math.atan2(target_altitude_m - radar_altitude_m, distance_m))

            profile_samples: list[CoverageProfileSample] = []
            obstruction: CoverageProfileSample | None = None
            required_target_altitude_m = target_altitude_m

            for index in range(sample_count):
                fraction = index / (sample_count - 1)
                sample_x = radar_x + dx * fraction
                sample_y = radar_y + dy * fraction
                sample_lon, sample_lat = from_projected.transform(sample_x, sample_y)
                sample_distance_m = distance_m * fraction
                terrain_m = _sample_elevation(dataset, to_dem, sample_lon, sample_lat, "profile sample")
                line_of_sight_m = radar_altitude_m + (target_altitude_m - radar_altitude_m) * fraction
                clearance_m = line_of_sight_m - (terrain_m + _curvature_bulge(distance_m, sample_distance_m, payload.advanced.use_curvature, payload.advanced.curvature_coeff))
                sample = CoverageProfileSample(
                    distance_m=sample_distance_m,
                    lon=sample_lon,
                    lat=sample_lat,
                    terrain_m=terrain_m,
                    line_of_sight_m=line_of_sight_m,
                    clearance_m=clearance_m,
                )
                profile_samples.append(sample)

                if index not in {0, sample_count - 1} and clearance_m < 0:
                    if obstruction is None or clearance_m < obstruction.clearance_m:
                        obstruction = sample
                if fraction > 0:
                    required_altitude = radar_altitude_m + (
                        terrain_m
                        + _curvature_bulge(distance_m, sample_distance_m, payload.advanced.use_curvature, payload.advanced.curvature_coeff)
                        - radar_altitude_m
                    ) / fraction
                    required_target_altitude_m = max(required_target_altitude_m, required_altitude)
    except AppError:
        raise
    except Exception as exc:
        raise AppError("PROFILE_ANALYSIS_FAILED", f"Unable to analyze terrain profile: {exc}", status_code=500) from exc

    min_required_target_height_m = max(0.0, required_target_altitude_m - target_ground_m)
    required_height_delta_m = max(0.0, min_required_target_height_m - payload.target.height_m)
    effective_range_m, radar_equation_range_m = _effective_max_range(payload)
    reason = _profile_reason(
        distance_m=distance_m,
        azimuth_deg=azimuth_deg,
        elevation_deg=elevation_deg,
        blocked=obstruction is not None,
        effective_range_m=effective_range_m,
        radar_equation_range_m=radar_equation_range_m,
        requested_range_m=payload.coverage.max_range_m,
        scan_mode=payload.coverage.scan_mode,
        sector_azimuth_deg=payload.coverage.azimuth_deg,
        beam_width_deg=payload.coverage.beam_width_deg,
        min_elevation_deg=payload.advanced.min_elevation_deg,
        max_elevation_deg=payload.advanced.max_elevation_deg,
    )

    return CoverageProfileResult(
        task_id=task_id,
        target_lon=lon,
        target_lat=lat,
        distance_m=distance_m,
        azimuth_deg=azimuth_deg,
        elevation_deg=elevation_deg,
        radar_ground_m=radar_ground_m,
        target_ground_m=target_ground_m,
        radar_altitude_m=radar_altitude_m,
        target_altitude_m=target_altitude_m,
        blocked=obstruction is not None,
        obstruction_distance_m=obstruction.distance_m if obstruction else None,
        obstruction_lon=obstruction.lon if obstruction else None,
        obstruction_lat=obstruction.lat if obstruction else None,
        obstruction_clearance_m=obstruction.clearance_m if obstruction else None,
        min_required_target_height_m=min_required_target_height_m,
        required_height_delta_m=required_height_delta_m,
        reason=reason,
        samples=profile_samples,
    )


def _sample_elevation(dataset, transformer: Transformer, lon: float, lat: float, label: str) -> float:
    x, y = transformer.transform(lon, lat)
    row, col = dataset.index(x, y)
    if row < 0 or col < 0 or row >= dataset.height or col >= dataset.width:
        raise AppError("PROFILE_OUTSIDE_DEM", f"The {label} is outside the DEM coverage.", status_code=400)
    value = next(dataset.sample([(x, y)]))[0]
    elevation = float(value)
    nodata = dataset.nodata
    if not math.isfinite(elevation) or (nodata is not None and math.isclose(elevation, float(nodata))):
        raise AppError("PROFILE_NO_DATA", f"The {label} falls on a DEM nodata pixel.", status_code=400)
    return elevation


def _curvature_bulge(distance_m: float, sample_distance_m: float, enabled: bool, coeff: float) -> float:
    if not enabled:
        return 0.0
    return max(0.0, coeff) * sample_distance_m * (distance_m - sample_distance_m) / (2 * EARTH_RADIUS_M)


def _profile_reason(
    *,
    distance_m: float,
    azimuth_deg: float,
    elevation_deg: float,
    blocked: bool,
    effective_range_m: float,
    radar_equation_range_m: float | None,
    requested_range_m: float,
    scan_mode: str,
    sector_azimuth_deg: float,
    beam_width_deg: float,
    min_elevation_deg: float,
    max_elevation_deg: float,
) -> str:
    if distance_m > requested_range_m:
        return "超出最大探测半径"
    if radar_equation_range_m is not None and distance_m > effective_range_m:
        return "雷达方程能量不足"
    if scan_mode == "sector" and beam_width_deg < 360:
        half_width = beam_width_deg / 2
        delta = abs((azimuth_deg - sector_azimuth_deg + 180) % 360 - 180)
        if delta > half_width:
            return "超出方位扫描扇区"
    if elevation_deg < min_elevation_deg:
        return "低于最低俯仰角"
    if elevation_deg > max_elevation_deg:
        return "高于最高俯仰角"
    if blocked:
        return "地形遮挡"
    return "可探测"
