from dataclasses import dataclass
from pathlib import Path

import numpy
from pyproj import CRS, Transformer
from rasterio.coords import BoundingBox
from rasterio.features import shapes
from rasterio.transform import array_bounds
from rasterio.windows import Window, from_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds
from shapely.geometry import GeometryCollection, box, shape
from shapely.ops import unary_union

from app.core.errors import AppError
from app.schemas.radar import CoverageRequest
from app.services.projection import utm_epsg_from_lonlat


@dataclass(frozen=True)
class PreparedCoverageDem:
    source_dem: Path
    projected_dem: Path
    target_epsg: int
    radar_x: float
    radar_y: float
    projected_bounds: BoundingBox
    resolution_m: tuple[float, float]


def prepare_coverage_dem(source: Path, destination: Path, payload: CoverageRequest) -> PreparedCoverageDem:
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

        target_bounds = bounds_around_point(radar_x, radar_y, payload.coverage.max_range_m)
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
        dst_transform, dst_width, dst_height = calculate_default_transform(
            src.crs,
            target_crs,
            int(window.width),
            int(window.height),
            *crop_bounds_exact,
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
                "compress": "deflate",
            }
        )

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

        destination.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(destination, "w", **kwargs) as dst:
            dst.write(destination_array, 1)

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
    )


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
