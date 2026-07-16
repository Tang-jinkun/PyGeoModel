from dataclasses import dataclass
from math import atan, cos, degrees, floor, hypot, radians, sin, sqrt
from pathlib import Path

import numpy
import rasterio
from rasterio.windows import Window
from rasterio.warp import transform as transform_points


@dataclass(frozen=True)
class TerrainAnchor:
    ground_elevation_amsl_m: float
    normal_enu: tuple[float, float, float]
    slope_deg: float
    fit_rmse_m: float
    max_residual_m: float


def sample_terrain_anchor(
    dem_path: Path,
    target_epsg: int,
    position_xy: tuple[float, float],
    heading_deg: float,
    footprint_length_m: float,
    footprint_width_m: float,
) -> TerrainAnchor:
    center_x, center_y = position_xy
    heading = radians(heading_deg)
    forward = (sin(heading), cos(heading))
    right = (cos(heading), -sin(heading))
    sample_xy = [
        (
            center_x + forward[0] * longitudinal + right[0] * lateral,
            center_y + forward[1] * longitudinal + right[1] * lateral,
        )
        for longitudinal in (-footprint_length_m / 2, 0, footprint_length_m / 2)
        for lateral in (-footprint_width_m / 2, 0, footprint_width_m / 2)
    ]

    with rasterio.open(dem_path) as source:
        if source.crs is None:
            raise ValueError("terrain sample source has no CRS")
        source_x, source_y = transform_points(
            f"EPSG:{target_epsg}",
            source.crs,
            [point[0] for point in sample_xy],
            [point[1] for point in sample_xy],
        )
        elevations = numpy.asarray(
            [
                _bilinear_sample(source, x, y)
                for x, y in zip(source_x, source_y)
            ],
            dtype=numpy.float64,
        )

    local_xy = numpy.asarray(sample_xy, dtype=numpy.float64)
    local_xy -= numpy.asarray((center_x, center_y), dtype=numpy.float64)
    design = numpy.column_stack((local_xy, numpy.ones(len(local_xy))))
    coefficients, _, _, _ = numpy.linalg.lstsq(design, elevations, rcond=None)
    x_slope, y_slope, center_elevation = coefficients
    fitted = design @ coefficients
    residuals = elevations - fitted

    normal = numpy.asarray((-x_slope, -y_slope, 1), dtype=numpy.float64)
    normal /= numpy.linalg.norm(normal)
    slope_deg = degrees(atan(hypot(x_slope, y_slope)))
    rmse_m = sqrt(float(numpy.mean(numpy.square(residuals))))

    return TerrainAnchor(
        ground_elevation_amsl_m=float(center_elevation),
        normal_enu=tuple(float(value) for value in normal),
        slope_deg=float(slope_deg),
        fit_rmse_m=rmse_m,
        max_residual_m=float(numpy.max(numpy.abs(residuals))),
    )


def _bilinear_sample(
    source: rasterio.io.DatasetReader,
    x: float,
    y: float,
) -> float:
    column_corner, row_corner = ~source.transform * (x, y)
    column = column_corner - 0.5
    row = row_corner - 0.5
    column_start = floor(column)
    row_start = floor(row)
    if (
        column_start < 0
        or row_start < 0
        or column_start + 1 >= source.width
        or row_start + 1 >= source.height
    ):
        raise ValueError("terrain sample falls outside DEM bounds")

    window = Window(column_start, row_start, 2, 2)
    values = numpy.asarray(
        source.read(indexes=[1], window=window)[0],
        dtype=numpy.float64,
    )
    valid_mask = source.read_masks(indexes=[1], window=window)[0]
    if not valid_mask.all() or not numpy.isfinite(values).all():
        raise ValueError("terrain sample contains nodata")

    column_fraction = column - column_start
    row_fraction = row - row_start
    upper = values[0, 0] * (1 - column_fraction) + values[0, 1] * column_fraction
    lower = values[1, 0] * (1 - column_fraction) + values[1, 1] * column_fraction
    return float(upper * (1 - row_fraction) + lower * row_fraction)
