from dataclasses import dataclass
from pathlib import Path

import numpy
from pyproj import CRS
from rasterio.coords import BoundingBox
from rasterio.transform import array_bounds, from_origin
from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds
from rasterio.windows import from_bounds

from app.core.errors import AppError
from app.schemas.radar import CoverageRequest, MultiRadarRequest
from app.services.coverage_model import (
    MAX_COVERAGE_CELLS,
    PROJECTED_DEM_NODATA,
    bounded_canvas,
    clamp_window,
)
from app.services.coverage_range import effective_max_range
from app.services.multi_radar_projection import prepare_multi_radar_projection


@dataclass(frozen=True)
class SharedMultiRadarDem:
    projected_dem: Path
    target_epsg: int
    transform: object
    analysis_domain: numpy.ndarray
    station_points: dict[str, tuple[float, float]]
    bounds: BoundingBox | None = None
    resolution_m: tuple[float, float] | None = None


def station_coverage_request(dem_id: str, station) -> CoverageRequest:
    return CoverageRequest(
        dem_id=dem_id,
        radar=station.radar,
        target=station.target,
        coverage=station.coverage,
        advanced=station.advanced,
        reserved_radar_params=station.reserved_radar_params,
    )


def prepare_shared_multi_radar_dem(source: Path, destination: Path, payload: MultiRadarRequest) -> SharedMultiRadarDem:
    import rasterio

    projection = prepare_multi_radar_projection([
        (station.radar.lon, station.radar.lat) for station in payload.radars
    ])
    target_crs = CRS.from_epsg(projection.target_epsg)
    station_points = dict(zip((station.radar_id for station in payload.radars), projection.projected_points, strict=True))
    ranges = [
        effective_max_range(station_coverage_request(payload.dem_id, station))[0]
        for station in payload.radars
    ]
    target_bounds = (
        min(point[0] - radius for point, radius in zip(projection.projected_points, ranges, strict=True)),
        min(point[1] - radius for point, radius in zip(projection.projected_points, ranges, strict=True)),
        max(point[0] + radius for point, radius in zip(projection.projected_points, ranges, strict=True)),
        max(point[1] + radius for point, radius in zip(projection.projected_points, ranges, strict=True)),
    )

    with rasterio.open(source) as src:
        if src.crs is None:
            raise AppError("DEM_WITHOUT_CRS", "DEM is missing coordinate reference system.")
        source_bounds = transform_bounds(target_crs, src.crs, *target_bounds, densify_pts=21)
        crop_bounds = BoundingBox(
            max(source_bounds[0], src.bounds.left),
            max(source_bounds[1], src.bounds.bottom),
            min(source_bounds[2], src.bounds.right),
            min(source_bounds[3], src.bounds.top),
        )
        if crop_bounds.left >= crop_bounds.right or crop_bounds.bottom >= crop_bounds.top:
            raise AppError("RANGE_OUTSIDE_DEM", "Radar ranges do not intersect DEM bounds.", status_code=400)
        window = clamp_window(
            from_bounds(*crop_bounds, transform=src.transform).round_offsets().round_lengths(),
            src.width,
            src.height,
        )
        if window.width <= 0 or window.height <= 0:
            raise AppError("RANGE_OUTSIDE_DEM", "DEM crop window is empty.", status_code=400)
        crop_transform = src.window_transform(window)
        crop_bounds_exact = array_bounds(int(window.height), int(window.width), crop_transform)
        resolution_transform, _, _ = calculate_default_transform(
            src.crs, target_crs, int(window.width), int(window.height), *crop_bounds_exact
        )
        native_x_resolution = abs(float(resolution_transform.a))
        native_y_resolution = abs(float(resolution_transform.e))
        width, height, x_resolution, y_resolution = bounded_canvas(
            target_bounds, native_x_resolution, native_y_resolution, max_cells=MAX_COVERAGE_CELLS
        )
        transform = from_origin(target_bounds[0], target_bounds[3], x_resolution, y_resolution)
        source_data = src.read(1, window=window, masked=True)
        source_values = numpy.asarray(source_data)
        source_valid = (~numpy.ma.getmaskarray(source_data) & numpy.isfinite(source_values)).astype(numpy.uint8)
        source_array = numpy.where(source_valid, source_values, PROJECTED_DEM_NODATA).astype(numpy.float32)
        destination_array = numpy.full((height, width), PROJECTED_DEM_NODATA, dtype=numpy.float32)
        destination_valid = numpy.zeros((height, width), dtype=numpy.uint8)
        reproject(
            source=source_array, destination=destination_array, src_transform=crop_transform, src_crs=src.crs,
            src_nodata=PROJECTED_DEM_NODATA, dst_transform=transform, dst_crs=target_crs,
            dst_nodata=PROJECTED_DEM_NODATA, resampling=Resampling.bilinear,
        )
        reproject(
            source=source_valid, destination=destination_valid, src_transform=crop_transform, src_crs=src.crs,
            src_nodata=0, dst_transform=transform, dst_crs=target_crs, dst_nodata=0,
            resampling=Resampling.nearest,
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        metadata = src.meta.copy()
        metadata.update({
            "driver": "GTiff", "crs": target_crs, "transform": transform, "width": width, "height": height,
            "count": 1, "dtype": "float32", "nodata": PROJECTED_DEM_NODATA, "compress": "deflate",
        })
        with rasterio.open(destination, "w", **metadata) as dst:
            dst.write(destination_array, 1)
            dst.write_mask(destination_valid * 255)

    bounds = BoundingBox(*array_bounds(height, width, transform))
    return SharedMultiRadarDem(
        projected_dem=destination,
        target_epsg=projection.target_epsg,
        transform=transform,
        analysis_domain=destination_valid.astype(bool),
        station_points=station_points,
        bounds=bounds,
        resolution_m=(abs(transform.a), abs(transform.e)),
    )
