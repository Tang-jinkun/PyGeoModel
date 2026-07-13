from dataclasses import dataclass
from pathlib import Path

import numpy
from pyproj import CRS, Transformer
from rasterio.coords import BoundingBox
from rasterio.features import shapes
from rasterio.transform import array_bounds, from_origin
from rasterio.windows import Window, from_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds
from shapely.geometry import GeometryCollection, box, shape
from shapely.ops import unary_union

from app.core.errors import AppError
from app.schemas.radar import CoverageRequest
from app.services.coverage_domain import build_coverage_domain
from app.services.coverage_range import effective_max_range
from app.services.geometry import make_range_geometry
from app.services.projection import utm_epsg_from_lonlat

MIN_DEM_COVERAGE_RATIO = 0.5
WARN_DEM_COVERAGE_RATIO = 0.98
PROJECTED_DEM_NODATA = -3.4028235e38
COVERAGE_RATIO_ROW_CHUNK_SIZE = 256
MAX_COVERAGE_CELLS = 16_777_216


@dataclass(frozen=True)
class PreparedCoverageDem:
    source_dem: Path
    projected_dem: Path
    target_epsg: int
    radar_x: float
    radar_y: float
    projected_bounds: BoundingBox
    resolution_m: tuple[float, float]
    dem_coverage_ratio: float
    resolution_adjusted: bool = False
    analysis_domain: numpy.ndarray | None = None
    beam_clip_profile_m: tuple[float, ...] = ()
    beam_clip_azimuth_step_deg: float = 2.0


def prepare_coverage_dem(source: Path, destination: Path, payload: CoverageRequest) -> PreparedCoverageDem:
    import rasterio

    target_epsg = utm_epsg_from_lonlat(payload.radar.lon, payload.radar.lat)
    target_crs = CRS.from_epsg(target_epsg)
    radar_x, radar_y = project_lonlat_to_crs(payload.radar.lon, payload.radar.lat, target_crs)
    effective_range_m, _ = effective_max_range(payload)

    with rasterio.open(source) as src:
        if src.crs is None:
            raise AppError("DEM_WITHOUT_CRS", "DEM is missing coordinate reference system.")

        src_radar_x, src_radar_y = project_lonlat_to_crs(payload.radar.lon, payload.radar.lat, src.crs)
        if not point_in_bounds(src_radar_x, src_radar_y, src.bounds):
            raise AppError("RADAR_OUTSIDE_DEM", "Radar point is outside DEM bounds.")

        radar_row, radar_col = src.index(src_radar_x, src_radar_y)
        radar_valid = src.read_masks(1, window=Window(radar_col, radar_row, 1, 1))
        if radar_valid.size != 1 or radar_valid[0, 0] == 0:
            raise AppError(
                "RADAR_ON_DEM_NODATA",
                "Radar point is on an invalid DEM cell.",
                status_code=400,
            )

        dem_coverage_ratio = coverage_extent_ratio_for_dataset(src, payload, target_crs, radar_x, radar_y)
        if dem_coverage_ratio < MIN_DEM_COVERAGE_RATIO:
            raise AppError(
                "RANGE_OUTSIDE_DEM",
                (
                    "Coverage range is mostly outside the DEM extent "
                    f"({dem_coverage_ratio:.0%} covered; at least {MIN_DEM_COVERAGE_RATIO:.0%} required)."
                ),
                status_code=400,
            )

        target_bounds = bounds_around_point(radar_x, radar_y, effective_range_m)
        src_crop_bounds = transform_bounds(
            target_crs,
            src.crs,
            *target_bounds,
            densify_pts=21,
        )
        dem_bounds_geom = box(*src.bounds)
        crop_geom = box(*src_crop_bounds).intersection(dem_bounds_geom)
        if crop_geom.is_empty:
            raise AppError("RANGE_OUTSIDE_DEM", "Coverage range does not intersect DEM bounds.")

        crop_bounds = crop_geom.bounds
        window = from_bounds(*crop_bounds, transform=src.transform).round_offsets().round_lengths()
        window = clamp_window(window, src.width, src.height)
        if window.width <= 0 or window.height <= 0:
            raise AppError("RANGE_OUTSIDE_DEM", "DEM crop window is empty.")

        crop_transform = src.window_transform(window)
        crop_bounds_exact = array_bounds(int(window.height), int(window.width), crop_transform)
        resolution_transform, _, _ = calculate_default_transform(
            src.crs,
            target_crs,
            int(window.width),
            int(window.height),
            *crop_bounds_exact,
        )
        native_x_resolution = abs(float(resolution_transform.a))
        native_y_resolution = abs(float(resolution_transform.e))
        dst_width, dst_height, x_resolution, y_resolution = bounded_canvas(
            target_bounds,
            native_x_resolution,
            native_y_resolution,
            max_cells=MAX_COVERAGE_CELLS,
        )
        resolution_adjusted = bool(
            x_resolution > native_x_resolution or y_resolution > native_y_resolution
        )
        dst_transform = from_origin(
            target_bounds[0],
            target_bounds[3],
            x_resolution,
            y_resolution,
        )
        if dst_width <= 0 or dst_height <= 0:
            raise AppError("INVALID_DEM", "Projected DEM dimensions are empty.")

        kwargs = src.meta.copy()
        kwargs.update(
            {
                "driver": "GTiff",
                "crs": target_crs,
                "transform": dst_transform,
                "width": dst_width,
                "height": dst_height,
                "count": 1,
                "dtype": "float32",
                "nodata": PROJECTED_DEM_NODATA,
                "compress": "deflate",
            }
        )

        source_data = src.read(1, window=window, masked=True)
        source_values = numpy.asarray(source_data)
        source_valid = (
            ~numpy.ma.getmaskarray(source_data) & numpy.isfinite(source_values)
        ).astype(numpy.uint8)
        source_array = numpy.where(
            source_valid,
            source_values,
            PROJECTED_DEM_NODATA,
        ).astype(numpy.float32)
        destination_array = numpy.full(
            (dst_height, dst_width),
            PROJECTED_DEM_NODATA,
            dtype=numpy.float32,
        )
        destination_valid = numpy.zeros((dst_height, dst_width), dtype=numpy.uint8)

        reproject(
            source=source_array,
            destination=destination_array,
            src_transform=crop_transform,
            src_crs=src.crs,
            src_nodata=PROJECTED_DEM_NODATA,
            dst_transform=dst_transform,
            dst_crs=target_crs,
            dst_nodata=PROJECTED_DEM_NODATA,
            resampling=Resampling.bilinear,
        )
        reproject(
            source=source_valid,
            destination=destination_valid,
            src_transform=crop_transform,
            src_crs=src.crs,
            src_nodata=0,
            dst_transform=dst_transform,
            dst_crs=target_crs,
            dst_nodata=0,
            resampling=Resampling.nearest,
        )

        destination.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(destination, "w", **kwargs) as dst:
            dst.write(destination_array, 1)
            dst.write_mask(destination_valid * 255)

    try:
        domain = build_coverage_domain(
            destination_valid.astype(bool),
            dst_transform,
            radar_x,
            radar_y,
            effective_range_m,
        )
    except ValueError as exc:
        if "Radar is on an invalid DEM cell" in str(exc):
            raise AppError(
                "RADAR_ON_DEM_NODATA",
                "Radar point is on an invalid projected DEM cell.",
                status_code=400,
            ) from exc
        raise AppError("INVALID_DEM", str(exc), status_code=400) from exc

    dem_coverage_ratio = _coverage_ratio_for_domain(
        domain.analysis_mask,
        dst_transform,
        radar_x,
        radar_y,
        payload,
        effective_range_m,
    )
    if dem_coverage_ratio < MIN_DEM_COVERAGE_RATIO:
        raise AppError(
            "RANGE_OUTSIDE_DEM",
            (
                "Coverage range is mostly outside the valid DEM domain "
                f"({dem_coverage_ratio:.0%} covered; at least {MIN_DEM_COVERAGE_RATIO:.0%} required)."
            ),
            status_code=400,
        )

    projected_bounds_tuple = array_bounds(dst_height, dst_width, dst_transform)
    projected_bounds = BoundingBox(
        left=projected_bounds_tuple[0],
        bottom=projected_bounds_tuple[1],
        right=projected_bounds_tuple[2],
        top=projected_bounds_tuple[3],
    )
    resolution_m = (abs(dst_transform.a), abs(dst_transform.e))
    if not point_in_bounds(radar_x, radar_y, projected_bounds):
        raise AppError("RADAR_OUTSIDE_PROJECTED_DEM", "Radar point is outside projected DEM bounds.")

    return PreparedCoverageDem(
        source_dem=source,
        projected_dem=destination,
        target_epsg=target_epsg,
        radar_x=radar_x,
        radar_y=radar_y,
        projected_bounds=projected_bounds,
        resolution_m=resolution_m,
        dem_coverage_ratio=dem_coverage_ratio,
        resolution_adjusted=resolution_adjusted,
        analysis_domain=domain.analysis_mask,
        beam_clip_profile_m=domain.radius_m,
        beam_clip_azimuth_step_deg=domain.azimuth_step_deg,
    )


def validate_coverage_extent(source: Path, payload: CoverageRequest) -> float:
    import rasterio

    target_epsg = utm_epsg_from_lonlat(payload.radar.lon, payload.radar.lat)
    target_crs = CRS.from_epsg(target_epsg)
    radar_x, radar_y = project_lonlat_to_crs(payload.radar.lon, payload.radar.lat, target_crs)
    with rasterio.open(source) as src:
        if src.crs is None:
            raise AppError("DEM_WITHOUT_CRS", "DEM is missing coordinate reference system.")

        src_radar_x, src_radar_y = project_lonlat_to_crs(payload.radar.lon, payload.radar.lat, src.crs)
        if not point_in_bounds(src_radar_x, src_radar_y, src.bounds):
            raise AppError("RADAR_OUTSIDE_DEM", "Radar point is outside DEM bounds.")

        ratio = coverage_extent_ratio_for_dataset(src, payload, target_crs, radar_x, radar_y)
        if ratio < MIN_DEM_COVERAGE_RATIO:
            raise AppError(
                "RANGE_OUTSIDE_DEM",
                (
                    "Coverage range is mostly outside the DEM extent "
                    f"({ratio:.0%} covered; at least {MIN_DEM_COVERAGE_RATIO:.0%} required)."
                ),
                status_code=400,
            )
        return ratio


def coverage_extent_ratio_for_dataset(dataset, payload: CoverageRequest, target_crs, radar_x: float, radar_y: float) -> float:
    dem_bounds = transform_bounds(dataset.crs, target_crs, *dataset.bounds, densify_pts=21)
    dem_geom = box(*dem_bounds)
    range_geom = make_range_geometry(
        radar_x,
        radar_y,
        effective_max_range(payload)[0],
        payload.coverage.scan_mode,
        payload.coverage.azimuth_deg,
        payload.coverage.beam_width_deg,
    )
    if range_geom.is_empty or range_geom.area <= 0:
        return 0.0
    return max(0.0, min(1.0, dem_geom.intersection(range_geom).area / range_geom.area))


def _coverage_ratio_for_domain(
    analysis_domain: numpy.ndarray,
    transform,
    radar_x: float,
    radar_y: float,
    payload: CoverageRequest,
    effective_range_m: float,
) -> float:
    height, width = analysis_domain.shape
    column_centers = numpy.arange(width, dtype=numpy.float64) + 0.5
    requested_count = 0
    analyzed_count = 0
    for row_start in range(0, height, COVERAGE_RATIO_ROW_CHUNK_SIZE):
        row_stop = min(height, row_start + COVERAGE_RATIO_ROW_CHUNK_SIZE)
        row_centers = numpy.arange(row_start, row_stop, dtype=numpy.float64) + 0.5
        rows, cols = numpy.meshgrid(row_centers, column_centers, indexing="ij")
        xs = transform.c + cols * transform.a + rows * transform.b
        ys = transform.f + cols * transform.d + rows * transform.e
        dx = xs - radar_x
        dy = ys - radar_y
        requested = numpy.hypot(dx, dy) <= effective_range_m
        if payload.coverage.scan_mode == "sector" and payload.coverage.beam_width_deg < 360:
            azimuth = (numpy.degrees(numpy.arctan2(dx, dy)) + 360) % 360
            center = payload.coverage.azimuth_deg % 360
            delta = numpy.abs((azimuth - center + 180) % 360 - 180)
            requested &= delta <= payload.coverage.beam_width_deg / 2
        requested_count += int(requested.sum())
        analyzed_count += int((requested & analysis_domain[row_start:row_stop]).sum())
    if requested_count == 0:
        return 0.0
    return analyzed_count / requested_count


def vectorize_visible_viewshed(viewshed: Path):
    import rasterio

    with rasterio.open(viewshed) as dataset:
        data = dataset.read(1)
        mask = data > 0
        geometries = [
            shape(geom)
            for geom, value in shapes(data, mask=mask, transform=dataset.transform)
            if value > 0
        ]

    if not geometries:
        return GeometryCollection()
    return unary_union(geometries)


def default_simplify_tolerance(resolution_m: tuple[float, float], requested_tolerance: float | None) -> float:
    if requested_tolerance is not None:
        return requested_tolerance
    return max(resolution_m)


def bounded_canvas(
    bounds: tuple[float, float, float, float],
    x_resolution: float,
    y_resolution: float,
    max_cells: int = MAX_COVERAGE_CELLS,
) -> tuple[int, int, float, float]:
    left, bottom, right, top = bounds
    width_m = right - left
    height_m = top - bottom
    width = int(numpy.ceil(width_m / x_resolution))
    height = int(numpy.ceil(height_m / y_resolution))
    native_cells = width * height
    if native_cells <= max_cells:
        return width, height, x_resolution, y_resolution

    scale = numpy.sqrt(native_cells / max_cells)
    while True:
        adjusted_x_resolution = x_resolution * scale
        adjusted_y_resolution = y_resolution * scale
        width = int(numpy.ceil(width_m / adjusted_x_resolution))
        height = int(numpy.ceil(height_m / adjusted_y_resolution))
        cells = width * height
        if cells <= max_cells:
            return width, height, adjusted_x_resolution, adjusted_y_resolution
        scale *= numpy.sqrt(cells / max_cells)


def project_lonlat_to_crs(lon: float, lat: float, crs) -> tuple[float, float]:
    transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    return transformer.transform(lon, lat)


def bounds_around_point(x: float, y: float, radius: float) -> tuple[float, float, float, float]:
    return (x - radius, y - radius, x + radius, y + radius)


def point_in_bounds(x: float, y: float, bounds: BoundingBox | tuple[float, float, float, float]) -> bool:
    left, bottom, right, top = bounds
    return left <= x <= right and bottom <= y <= top


def clamp_window(window: Window, width: int, height: int) -> Window:
    col_off = max(0, int(window.col_off))
    row_off = max(0, int(window.row_off))
    col_end = min(width, int(window.col_off + window.width))
    row_end = min(height, int(window.row_off + window.height))
    return Window(col_off, row_off, max(0, col_end - col_off), max(0, row_end - row_off))
