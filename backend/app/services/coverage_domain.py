from dataclasses import dataclass
import math

import numpy
from rasterio.transform import rowcol


@dataclass(frozen=True)
class CoverageDomain:
    analysis_mask: numpy.ndarray
    azimuth_step_deg: float
    radius_m: tuple[float, ...]


def build_coverage_domain(
    valid_pixels: numpy.ndarray,
    transform,
    radar_x: float,
    radar_y: float,
    max_range_m: float,
    azimuth_step_deg: float = 2.0,
) -> CoverageDomain:
    if valid_pixels.ndim != 2 or not valid_pixels.any():
        raise ValueError("DEM valid mask is empty")
    if max_range_m <= 0:
        raise ValueError("Maximum range must be positive")
    if azimuth_step_deg <= 0 or azimuth_step_deg > 360:
        raise ValueError("Azimuth step must be between 0 and 360 degrees")

    radar_row, radar_col = rowcol(transform, radar_x, radar_y)
    if not _inside(valid_pixels, radar_row, radar_col) or not valid_pixels[radar_row, radar_col]:
        raise ValueError("Radar is on an invalid DEM cell")

    sample_count = max(1, round(360 / azimuth_step_deg))
    actual_step_deg = 360 / sample_count
    sample_step_m = max(0.01, min(abs(float(transform.a)), abs(float(transform.e))) / 2)
    radius_m = tuple(
        _continuous_valid_radius(
            valid_pixels,
            transform,
            radar_x,
            radar_y,
            azimuth_deg=index * actual_step_deg,
            max_range_m=max_range_m,
            sample_step_m=sample_step_m,
        )
        for index in range(sample_count)
    )
    analysis_mask = _profile_to_mask(
        valid_pixels,
        transform,
        radar_x,
        radar_y,
        radius_m,
        actual_step_deg,
        sample_step_m,
    )
    return CoverageDomain(
        analysis_mask=analysis_mask,
        azimuth_step_deg=actual_step_deg,
        radius_m=radius_m,
    )


def _continuous_valid_radius(
    valid_pixels: numpy.ndarray,
    transform,
    radar_x: float,
    radar_y: float,
    azimuth_deg: float,
    max_range_m: float,
    sample_step_m: float,
) -> float:
    azimuth_rad = math.radians(azimuth_deg)
    distances = numpy.arange(0, max_range_m + sample_step_m, sample_step_m)
    xs = radar_x + math.sin(azimuth_rad) * distances
    ys = radar_y + math.cos(azimuth_rad) * distances
    rows, cols = rowcol(transform, xs, ys)
    rows = numpy.asarray(rows, dtype=numpy.int64)
    cols = numpy.asarray(cols, dtype=numpy.int64)
    inside = (
        (rows >= 0)
        & (rows < valid_pixels.shape[0])
        & (cols >= 0)
        & (cols < valid_pixels.shape[1])
    )
    samples_valid = numpy.zeros(distances.shape, dtype=bool)
    samples_valid[inside] = valid_pixels[rows[inside], cols[inside]]
    invalid_indices = numpy.flatnonzero(~samples_valid)
    if invalid_indices.size:
        first_invalid_distance = float(distances[int(invalid_indices[0])])
        return max(0.0, min(max_range_m, first_invalid_distance - sample_step_m))
    return float(max_range_m)


def _profile_to_mask(
    valid_pixels: numpy.ndarray,
    transform,
    radar_x: float,
    radar_y: float,
    radius_m: tuple[float, ...],
    azimuth_step_deg: float,
    tolerance_m: float,
) -> numpy.ndarray:
    height, width = valid_pixels.shape
    rows, cols = numpy.meshgrid(
        numpy.arange(height, dtype=numpy.float64) + 0.5,
        numpy.arange(width, dtype=numpy.float64) + 0.5,
        indexing="ij",
    )
    xs = transform.c + cols * transform.a + rows * transform.b
    ys = transform.f + cols * transform.d + rows * transform.e
    dx = xs - radar_x
    dy = ys - radar_y
    distances = numpy.hypot(dx, dy)
    azimuths = (numpy.degrees(numpy.arctan2(dx, dy)) + 360) % 360

    profile = numpy.asarray(radius_m, dtype=numpy.float64)
    fractional_indices = azimuths / azimuth_step_deg
    lower_indices = numpy.floor(fractional_indices).astype(numpy.int64) % len(profile)
    upper_indices = (lower_indices + 1) % len(profile)
    fractions = fractional_indices - numpy.floor(fractional_indices)
    limits = profile[lower_indices] + (profile[upper_indices] - profile[lower_indices]) * fractions
    return valid_pixels.astype(bool, copy=False) & (distances <= limits + tolerance_m)


def _inside(array: numpy.ndarray, row: int, col: int) -> bool:
    return 0 <= row < array.shape[0] and 0 <= col < array.shape[1]
