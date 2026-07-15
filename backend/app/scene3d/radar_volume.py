from dataclasses import dataclass
from pathlib import Path

import numpy
import rasterio
from skimage import measure

from app.schemas.radar import CoverageRequest
from app.services.coverage_model import PreparedCoverageDem
from app.services.coverage_range import effective_max_range


MAX_GRID_SHAPE = (256, 256, 128)


@dataclass(frozen=True)
class RadarVisibilityVolume:
    vertices: numpy.ndarray
    faces: numpy.ndarray
    terrain_segments: numpy.ndarray
    unknown_segments: numpy.ndarray
    grid_shape: tuple[int, int, int]
    occupied_voxel_count: int


def build_radar_visibility_volume(
    prepared: PreparedCoverageDem,
    payload: CoverageRequest,
    min_visible_height: Path,
    *,
    grid_shape: tuple[int, int, int] | None = None,
) -> RadarVisibilityVolume:
    """Build a terrain-carved nominal radar volume in projected XYZ coordinates."""
    x_count, y_count, z_count = _bounded_grid_shape(grid_shape)
    effective_range_m, _ = effective_max_range(payload)

    with rasterio.open(prepared.projected_dem) as dem_source, rasterio.open(
        min_visible_height
    ) as min_height_source:
        _validate_raster_pair(dem_source, min_height_source)
        dem = dem_source.read(1, masked=True)
        threshold = min_height_source.read(1, masked=True)
        transform = dem_source.transform

    dem_values = numpy.asarray(dem.data, dtype=numpy.float64)
    threshold_values = numpy.asarray(threshold.data, dtype=numpy.float64)
    dem_valid = ~numpy.ma.getmaskarray(dem) & numpy.isfinite(dem_values)
    threshold_valid = (
        ~numpy.ma.getmaskarray(threshold)
        & numpy.isfinite(threshold_values)
        & (threshold_values >= 0)
    )
    analysis_domain = _analysis_domain(prepared, dem_values.shape)
    source_valid = dem_valid & threshold_valid & analysis_domain

    radar_ground, radar_ground_valid = _sample_raster_grid(
        dem_values,
        dem_valid & analysis_domain,
        transform,
        numpy.asarray([[prepared.radar_x]], dtype=numpy.float64),
        numpy.asarray([[prepared.radar_y]], dtype=numpy.float64),
    )
    if not radar_ground_valid[0, 0]:
        raise ValueError("Radar must be on a valid projected DEM cell")
    radar_z = float(radar_ground[0, 0] + payload.radar.height_m)

    x_min = prepared.radar_x - effective_range_m
    y_min = prepared.radar_y - effective_range_m
    x_coordinates = numpy.linspace(
        x_min,
        prepared.radar_x + effective_range_m,
        x_count,
        dtype=numpy.float64,
    )
    y_coordinates = numpy.linspace(
        y_min,
        prepared.radar_y + effective_range_m,
        y_count,
        dtype=numpy.float64,
    )
    z_coordinates = numpy.linspace(
        radar_z,
        radar_z + effective_range_m,
        z_count,
        dtype=numpy.float64,
    )
    x_grid, y_grid = numpy.meshgrid(x_coordinates, y_coordinates)
    terrain_grid, valid_horizontal = _sample_raster_grid(
        dem_values,
        source_valid,
        transform,
        x_grid,
        y_grid,
    )
    min_height_grid, min_height_sample_valid = _sample_raster_grid(
        threshold_values,
        source_valid,
        transform,
        x_grid,
        y_grid,
    )
    valid_horizontal &= min_height_sample_valid

    dx = x_grid - prepared.radar_x
    dy = y_grid - prepared.radar_y
    horizontal_distance_squared = dx * dx + dy * dy
    dz = z_coordinates[:, numpy.newaxis, numpy.newaxis] - radar_z
    nominal_upper_hemisphere = (
        horizontal_distance_squared[numpy.newaxis, :, :] + dz * dz
        <= effective_range_m * effective_range_m
    )
    above_terrain = (
        z_coordinates[:, numpy.newaxis, numpy.newaxis]
        >= terrain_grid[numpy.newaxis, :, :]
    )
    meets_los_threshold = (
        z_coordinates[:, numpy.newaxis, numpy.newaxis]
        - terrain_grid[numpy.newaxis, :, :]
        >= min_height_grid[numpy.newaxis, :, :]
    )
    sector = _sector_mask(dx, dy, payload)

    occupancy = nominal_upper_hemisphere
    occupancy &= above_terrain
    occupancy &= meets_los_threshold
    occupancy &= sector[numpy.newaxis, :, :]
    occupancy &= valid_horizontal[numpy.newaxis, :, :]
    occupied_voxel_count = int(numpy.count_nonzero(occupancy))

    x_pitch = (2 * effective_range_m) / (x_count - 1)
    y_pitch = (2 * effective_range_m) / (y_count - 1)
    z_pitch = effective_range_m / (z_count - 1)
    vertices, faces = _extract_surface(
        occupancy,
        spacing=(z_pitch, y_pitch, x_pitch),
        origin=(x_min, y_min, radar_z),
    )
    terrain_segments = _terrain_contact_segments(
        vertices,
        faces,
        terrain_grid,
        valid_horizontal,
        origin=(x_min, y_min),
        pitch=(x_pitch, y_pitch, z_pitch),
    )
    unknown_segments = _unknown_boundary_segments(
        valid_horizontal,
        terrain_grid,
        min_height_grid,
        radar_z,
        origin=(x_min, y_min),
        pitch=(x_pitch, y_pitch),
    )

    return RadarVisibilityVolume(
        vertices=vertices,
        faces=faces,
        terrain_segments=terrain_segments,
        unknown_segments=unknown_segments,
        grid_shape=(x_count, y_count, z_count),
        occupied_voxel_count=occupied_voxel_count,
    )


def _bounded_grid_shape(
    grid_shape: tuple[int, int, int] | None,
) -> tuple[int, int, int]:
    requested = MAX_GRID_SHAPE if grid_shape is None else grid_shape
    if len(requested) != 3 or any(
        isinstance(value, bool) or not isinstance(value, (int, numpy.integer))
        for value in requested
    ):
        raise ValueError("grid_shape must contain integer (x, y, z) counts")
    if any(value < 2 for value in requested):
        raise ValueError("grid_shape counts must be at least 2")
    return tuple(
        min(int(value), maximum)
        for value, maximum in zip(requested, MAX_GRID_SHAPE, strict=True)
    )


def _validate_raster_pair(dem_source, min_height_source) -> None:
    if (
        dem_source.shape != min_height_source.shape
        or dem_source.transform != min_height_source.transform
        or dem_source.crs != min_height_source.crs
    ):
        raise ValueError("Projected DEM and minimum-visible-height raster must align")


def _analysis_domain(
    prepared: PreparedCoverageDem,
    shape: tuple[int, int],
) -> numpy.ndarray:
    if prepared.analysis_domain is None:
        return numpy.ones(shape, dtype=bool)
    domain = numpy.asarray(prepared.analysis_domain, dtype=bool)
    if domain.shape != shape:
        raise ValueError("Prepared analysis domain must match the projected DEM")
    return domain


def _sample_raster_grid(
    values: numpy.ndarray,
    valid: numpy.ndarray,
    transform,
    x_grid: numpy.ndarray,
    y_grid: numpy.ndarray,
) -> tuple[numpy.ndarray, numpy.ndarray]:
    column, row = (~transform) * (x_grid, y_grid)
    row = numpy.floor(row).astype(numpy.int64)
    column = numpy.floor(column).astype(numpy.int64)
    in_bounds = (
        (row >= 0)
        & (row < values.shape[0])
        & (column >= 0)
        & (column < values.shape[1])
    )
    safe_row = numpy.clip(row, 0, values.shape[0] - 1)
    safe_column = numpy.clip(column, 0, values.shape[1] - 1)
    sampled_valid = in_bounds & valid[safe_row, safe_column]
    sampled = values[safe_row, safe_column]
    return sampled, sampled_valid


def _sector_mask(
    dx: numpy.ndarray,
    dy: numpy.ndarray,
    payload: CoverageRequest,
) -> numpy.ndarray:
    if payload.coverage.scan_mode != "sector" or payload.coverage.beam_width_deg >= 360:
        return numpy.ones(dx.shape, dtype=bool)
    azimuth = (numpy.degrees(numpy.arctan2(dx, dy)) + 360) % 360
    delta = numpy.abs(
        (azimuth - payload.coverage.azimuth_deg + 180) % 360 - 180
    )
    return delta <= payload.coverage.beam_width_deg / 2


def _extract_surface(
    occupancy: numpy.ndarray,
    *,
    spacing: tuple[float, float, float],
    origin: tuple[float, float, float],
) -> tuple[numpy.ndarray, numpy.ndarray]:
    if not occupancy.any() or occupancy.all():
        return (
            numpy.empty((0, 3), dtype=numpy.float64),
            numpy.empty((0, 3), dtype=numpy.int64),
        )
    vertices_zyx, faces, _, _ = measure.marching_cubes(
        occupancy.astype(numpy.float32),
        level=0.5,
        spacing=spacing,
    )
    vertices = numpy.column_stack(
        (
            origin[0] + vertices_zyx[:, 2],
            origin[1] + vertices_zyx[:, 1],
            origin[2] + vertices_zyx[:, 0],
        )
    )
    return vertices, numpy.asarray(faces, dtype=numpy.int64)


def _terrain_contact_segments(
    vertices: numpy.ndarray,
    faces: numpy.ndarray,
    terrain_grid: numpy.ndarray,
    valid_horizontal: numpy.ndarray,
    *,
    origin: tuple[float, float],
    pitch: tuple[float, float, float],
) -> numpy.ndarray:
    if len(vertices) == 0 or len(faces) == 0:
        return numpy.empty((0, 2, 3), dtype=numpy.float64)
    x_index = numpy.rint((vertices[:, 0] - origin[0]) / pitch[0]).astype(int)
    y_index = numpy.rint((vertices[:, 1] - origin[1]) / pitch[1]).astype(int)
    x_index = numpy.clip(x_index, 0, terrain_grid.shape[1] - 1)
    y_index = numpy.clip(y_index, 0, terrain_grid.shape[0] - 1)
    clearance = vertices[:, 2] - terrain_grid[y_index, x_index]
    touches_terrain = (
        valid_horizontal[y_index, x_index]
        & (numpy.abs(clearance) <= 0.75 * pitch[2])
    )
    edges = numpy.concatenate(
        (faces[:, (0, 1)], faces[:, (1, 2)], faces[:, (2, 0)]),
        axis=0,
    )
    edges = numpy.unique(numpy.sort(edges, axis=1), axis=0)
    contact_edges = edges[touches_terrain[edges].all(axis=1)]
    return numpy.asarray(vertices[contact_edges], dtype=numpy.float64)


def _unknown_boundary_segments(
    valid_horizontal: numpy.ndarray,
    terrain_grid: numpy.ndarray,
    min_height_grid: numpy.ndarray,
    radar_z: float,
    *,
    origin: tuple[float, float],
    pitch: tuple[float, float],
) -> numpy.ndarray:
    contours = measure.find_contours(valid_horizontal.astype(numpy.float32), 0.5)
    segments: list[numpy.ndarray] = []
    base_height = numpy.maximum(radar_z, terrain_grid + min_height_grid)
    for contour in contours:
        if len(contour) < 2:
            continue
        points = numpy.empty((len(contour), 3), dtype=numpy.float64)
        points[:, 0] = origin[0] + contour[:, 1] * pitch[0]
        points[:, 1] = origin[1] + contour[:, 0] * pitch[1]
        points[:, 2] = [
            _nearest_valid_height(row, column, valid_horizontal, base_height, radar_z)
            for row, column in contour
        ]
        segments.extend(numpy.stack((points[:-1], points[1:]), axis=1))
    if not segments:
        return numpy.empty((0, 2, 3), dtype=numpy.float64)
    return numpy.asarray(segments, dtype=numpy.float64)


def _nearest_valid_height(
    row: float,
    column: float,
    valid: numpy.ndarray,
    height: numpy.ndarray,
    fallback: float,
) -> float:
    row_candidates = {int(numpy.floor(row)), int(numpy.ceil(row))}
    column_candidates = {int(numpy.floor(column)), int(numpy.ceil(column))}
    candidates = [
        (candidate_row, candidate_column)
        for candidate_row in row_candidates
        for candidate_column in column_candidates
        if 0 <= candidate_row < valid.shape[0]
        and 0 <= candidate_column < valid.shape[1]
        and valid[candidate_row, candidate_column]
    ]
    if not candidates:
        return fallback
    nearest_row, nearest_column = min(
        candidates,
        key=lambda item: (item[0] - row) ** 2 + (item[1] - column) ** 2,
    )
    return float(height[nearest_row, nearest_column])
