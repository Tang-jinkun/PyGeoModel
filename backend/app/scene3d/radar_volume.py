from dataclasses import dataclass
from pathlib import Path

import numpy
import rasterio
from skimage import measure

from app.schemas.radar import CoverageRequest
from app.services.coverage_model import PreparedCoverageDem
from app.services.coverage_range import effective_max_range


MAX_GRID_SHAPE = (256, 256, 128)
MIN_PREVIEW_GRID_SIZE = 64
MIN_PREVIEW_VERTICAL_LEVELS = 32


@dataclass(frozen=True)
class RadarVisibilityVolume:
    vertices: numpy.ndarray
    faces: numpy.ndarray
    terrain_segments: numpy.ndarray
    unknown_segments: numpy.ndarray
    grid_shape: tuple[int, int, int]
    occupied_voxel_count: int
    blocked_vertices: numpy.ndarray | None = None
    blocked_faces: numpy.ndarray | None = None
    blocked_contact_segments: numpy.ndarray | None = None


def build_radar_visibility_volume(
    prepared: PreparedCoverageDem,
    payload: CoverageRequest,
    min_visible_height: Path,
    *,
    grid_shape: tuple[int, int, int] | None = None,
) -> RadarVisibilityVolume:
    """Build a terrain-carved nominal radar volume in projected XYZ coordinates."""
    x_count, y_count, z_count = _bounded_grid_shape(grid_shape, payload)
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
    sector = _sector_mask(dx, dy, payload)
    vertical_domain = (
        valid_horizontal
        & (horizontal_distance_squared <= effective_range_m * effective_range_m)
        & sector
    )
    sampled_terrain = terrain_grid[vertical_domain]
    if sampled_terrain.size == 0:
        raise ValueError("Radar analysis domain contains no valid terrain samples")
    terrain_min = min(float(sampled_terrain.min()), float(radar_ground[0, 0]))
    terrain_max = max(float(sampled_terrain.max()), float(radar_ground[0, 0]))
    z_min = terrain_min
    z_max = terrain_max + payload.advanced.voxel_max_height_m
    z_coordinates = numpy.linspace(
        z_min,
        z_max,
        z_count,
        dtype=numpy.float64,
    )

    horizontal_distance = numpy.sqrt(horizontal_distance_squared)
    dz = z_coordinates[:, numpy.newaxis, numpy.newaxis] - radar_z
    nominal_range = (
        horizontal_distance_squared[numpy.newaxis, :, :] + dz * dz
        <= effective_range_m * effective_range_m
    )
    elevation = numpy.arctan2(
        dz,
        horizontal_distance[numpy.newaxis, :, :],
    )
    within_elevation = (
        elevation >= numpy.radians(payload.advanced.min_elevation_deg)
    ) & (
        elevation <= numpy.radians(payload.advanced.max_elevation_deg)
    )
    height_above_terrain = (
        z_coordinates[:, numpy.newaxis, numpy.newaxis]
        - terrain_grid[numpy.newaxis, :, :]
    )
    above_terrain = (
        height_above_terrain >= 0
    )
    meets_los_threshold = (
        height_above_terrain >= min_height_grid[numpy.newaxis, :, :]
    )
    within_height_limit = (
        height_above_terrain <= payload.advanced.voxel_max_height_m
    )
    occupancy = nominal_range
    occupancy &= within_elevation
    occupancy &= above_terrain
    occupancy &= meets_los_threshold
    occupancy &= within_height_limit
    occupancy &= sector[numpy.newaxis, :, :]
    occupancy &= valid_horizontal[numpy.newaxis, :, :]
    occupied_voxel_count = int(numpy.count_nonzero(occupancy))

    x_pitch = (2 * effective_range_m) / (x_count - 1)
    y_pitch = (2 * effective_range_m) / (y_count - 1)
    z_pitch = (z_max - z_min) / (z_count - 1)
    blocked_contact_segments = _terrain_shadow_boundary_segments(
        min_height_grid,
        terrain_grid,
        vertical_domain,
        origin=(x_min, y_min),
        pitch=(x_pitch, y_pitch),
    )
    vertices, faces = _extract_surface(
        occupancy,
        spacing=(z_pitch, y_pitch, x_pitch),
        origin=(x_min, y_min, z_min),
    )
    terrain_segments = _terrain_contact_segments(
        vertices,
        faces,
        terrain_grid,
        min_height_grid,
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
        radar_xy=(prepared.radar_x, prepared.radar_y),
        effective_range_m=effective_range_m,
        payload=payload,
    )

    return RadarVisibilityVolume(
        vertices=vertices,
        faces=faces,
        terrain_segments=terrain_segments,
        unknown_segments=unknown_segments,
        grid_shape=(x_count, y_count, z_count),
        occupied_voxel_count=occupied_voxel_count,
        blocked_contact_segments=blocked_contact_segments,
    )


def build_radar_visibility_envelope(
    prepared: PreparedCoverageDem,
    payload: CoverageRequest,
    min_visible_height: Path,
    *,
    grid_shape: tuple[int, int, int] | None = None,
) -> RadarVisibilityVolume:
    """Build a closed DEM-derived lower surface with an analytic spherical top."""
    x_count, y_count, _ = _bounded_grid_shape(grid_shape, payload)
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
    x_grid, y_grid = numpy.meshgrid(x_coordinates, y_coordinates)
    terrain_grid, valid_horizontal = _sample_raster_grid(
        dem_values,
        source_valid,
        transform,
        x_grid,
        y_grid,
    )
    min_height_grid, min_height_valid = _sample_raster_grid(
        threshold_values,
        source_valid,
        transform,
        x_grid,
        y_grid,
    )
    valid_horizontal &= min_height_valid

    dx = x_grid - prepared.radar_x
    dy = y_grid - prepared.radar_y
    horizontal_distance_squared = dx * dx + dy * dy
    horizontal_distance = numpy.sqrt(horizontal_distance_squared)
    inside_range = horizontal_distance_squared <= effective_range_m**2
    sector = _sector_mask(dx, dy, payload)

    lower_surface = terrain_grid + min_height_grid
    minimum_elevation = numpy.radians(payload.advanced.min_elevation_deg)
    lower_surface = numpy.maximum(
        lower_surface,
        radar_z + horizontal_distance * numpy.tan(minimum_elevation),
    )
    upper_surface = radar_z + numpy.sqrt(
        numpy.maximum(0.0, effective_range_m**2 - horizontal_distance_squared)
    )
    if payload.advanced.max_elevation_deg < 90:
        upper_surface = numpy.minimum(
            upper_surface,
            radar_z
            + horizontal_distance
            * numpy.tan(numpy.radians(payload.advanced.max_elevation_deg)),
        )

    envelope_valid = (
        valid_horizontal
        & inside_range
        & sector
        & (lower_surface <= upper_surface)
    )
    vertices, faces = _height_field_envelope_mesh(
        x_grid,
        y_grid,
        lower_surface,
        upper_surface,
        envelope_valid,
    )
    terrain_visibility_floor = terrain_grid + min_height_grid
    blocked_upper_surface = numpy.minimum(
        terrain_visibility_floor,
        upper_surface,
    )
    blocked_valid = (
        valid_horizontal
        & inside_range
        & sector
        & (min_height_grid > 1e-6)
        & (terrain_grid < blocked_upper_surface)
    )
    blocked_cells = (
        blocked_valid[:-1, :-1]
        & blocked_valid[:-1, 1:]
        & blocked_valid[1:, :-1]
        & blocked_valid[1:, 1:]
    )
    if blocked_cells.any():
        blocked_vertices, blocked_faces = _height_field_envelope_mesh(
            x_grid,
            y_grid,
            terrain_grid,
            blocked_upper_surface,
            blocked_valid,
        )
    else:
        blocked_vertices = numpy.empty((0, 3), dtype=numpy.float64)
        blocked_faces = numpy.empty((0, 3), dtype=numpy.int64)
    x_pitch = (2 * effective_range_m) / (x_count - 1)
    y_pitch = (2 * effective_range_m) / (y_count - 1)
    blocked_contact_segments = _terrain_shadow_boundary_segments(
        min_height_grid,
        terrain_grid,
        valid_horizontal & inside_range & sector,
        origin=(x_min, y_min),
        pitch=(x_pitch, y_pitch),
    )
    vertical_span = max(1.0, float(upper_surface[envelope_valid].max() - lower_surface[envelope_valid].min()))
    terrain_segments = _terrain_contact_segments(
        vertices,
        faces,
        terrain_grid,
        min_height_grid,
        valid_horizontal,
        origin=(x_min, y_min),
        pitch=(x_pitch, y_pitch, vertical_span),
    )
    unknown_segments = _unknown_boundary_segments(
        valid_horizontal,
        terrain_grid,
        min_height_grid,
        radar_z,
        origin=(x_min, y_min),
        pitch=(x_pitch, y_pitch),
        radar_xy=(prepared.radar_x, prepared.radar_y),
        effective_range_m=effective_range_m,
        payload=payload,
    )
    return RadarVisibilityVolume(
        vertices=vertices,
        faces=faces,
        terrain_segments=terrain_segments,
        unknown_segments=unknown_segments,
        grid_shape=(x_count, y_count, 2),
        occupied_voxel_count=int(numpy.count_nonzero(envelope_valid)),
        blocked_vertices=blocked_vertices,
        blocked_faces=blocked_faces,
        blocked_contact_segments=blocked_contact_segments,
    )


def _height_field_envelope_mesh(
    x_grid: numpy.ndarray,
    y_grid: numpy.ndarray,
    lower: numpy.ndarray,
    upper: numpy.ndarray,
    valid: numpy.ndarray,
) -> tuple[numpy.ndarray, numpy.ndarray]:
    cell_valid = valid[:-1, :-1] & valid[:-1, 1:] & valid[1:, :-1] & valid[1:, 1:]
    if not cell_valid.any():
        raise ValueError("Radar height-field envelope contains no valid surface cells")

    used = numpy.zeros_like(valid, dtype=bool)
    used[:-1, :-1] |= cell_valid
    used[:-1, 1:] |= cell_valid
    used[1:, :-1] |= cell_valid
    used[1:, 1:] |= cell_valid
    bottom_index = numpy.full(valid.shape, -1, dtype=numpy.int64)
    top_index = numpy.full(valid.shape, -1, dtype=numpy.int64)
    vertices: list[tuple[float, float, float]] = []
    for row, column in numpy.argwhere(used):
        bottom_index[row, column] = len(vertices)
        vertices.append((x_grid[row, column], y_grid[row, column], lower[row, column]))
        top_index[row, column] = len(vertices)
        vertices.append((x_grid[row, column], y_grid[row, column], upper[row, column]))

    faces: list[list[int]] = []
    row_count, column_count = cell_valid.shape

    def add_side(first: tuple[int, int], second: tuple[int, int]) -> None:
        first_bottom = int(bottom_index[first])
        second_bottom = int(bottom_index[second])
        first_top = int(top_index[first])
        second_top = int(top_index[second])
        faces.extend(
            [
                [first_bottom, second_bottom, second_top],
                [first_bottom, second_top, first_top],
            ]
        )

    for row, column in numpy.argwhere(cell_valid):
        bottom_a = int(bottom_index[row, column])
        bottom_b = int(bottom_index[row, column + 1])
        bottom_c = int(bottom_index[row + 1, column])
        bottom_d = int(bottom_index[row + 1, column + 1])
        top_a = int(top_index[row, column])
        top_b = int(top_index[row, column + 1])
        top_c = int(top_index[row + 1, column])
        top_d = int(top_index[row + 1, column + 1])
        faces.extend(
            [
                [top_a, top_c, top_b],
                [top_b, top_c, top_d],
                [bottom_a, bottom_b, bottom_c],
                [bottom_b, bottom_d, bottom_c],
            ]
        )
        if row == 0 or not cell_valid[row - 1, column]:
            add_side((row, column + 1), (row, column))
        if row == row_count - 1 or not cell_valid[row + 1, column]:
            add_side((row + 1, column), (row + 1, column + 1))
        if column == 0 or not cell_valid[row, column - 1]:
            add_side((row, column), (row + 1, column))
        if column == column_count - 1 or not cell_valid[row, column + 1]:
            add_side((row + 1, column + 1), (row, column + 1))

    return numpy.asarray(vertices, dtype=numpy.float64), numpy.asarray(faces, dtype=numpy.int64)


def _bounded_grid_shape(
    grid_shape: tuple[int, int, int] | None,
    payload: CoverageRequest,
) -> tuple[int, int, int]:
    """Resolve payload preview resolution while preserving explicit test shapes."""
    requested = (
        (
            max(payload.advanced.voxel_grid_size, MIN_PREVIEW_GRID_SIZE),
            max(payload.advanced.voxel_grid_size, MIN_PREVIEW_GRID_SIZE),
            max(
                payload.advanced.voxel_vertical_levels,
                MIN_PREVIEW_VERTICAL_LEVELS,
            ),
        )
        if grid_shape is None
        else grid_shape
    )
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
        raise ValueError(
            "Radar occupancy does not contain an extractable surface"
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
    if len(vertices) == 0 or len(faces) == 0:
        raise ValueError("Radar occupancy produced a degenerate surface")
    return vertices, numpy.asarray(faces, dtype=numpy.int64)


def _terrain_contact_segments(
    vertices: numpy.ndarray,
    faces: numpy.ndarray,
    terrain_grid: numpy.ndarray,
    min_height_grid: numpy.ndarray,
    valid_horizontal: numpy.ndarray,
    *,
    origin: tuple[float, float],
    pitch: tuple[float, float, float],
) -> numpy.ndarray:
    if len(vertices) == 0 or len(faces) == 0:
        return numpy.empty((0, 2, 3), dtype=numpy.float64)
    terrain_height, terrain_valid = _interpolate_height_field(
        vertices,
        terrain_grid,
        valid_horizontal,
        origin=origin,
        pitch=pitch[:2],
    )
    clearance = vertices[:, 2] - terrain_height
    tolerance = max(1e-9, numpy.finfo(numpy.float64).eps * max(1.0, pitch[2]))
    segments: list[numpy.ndarray] = []
    for face in faces:
        if not terrain_valid[face].all():
            continue
        face_clearance = clearance[face]
        if numpy.all(numpy.abs(face_clearance) <= tolerance):
            continue
        intersections: list[numpy.ndarray] = []
        for first, second in ((0, 1), (1, 2), (2, 0)):
            first_clearance = face_clearance[first]
            second_clearance = face_clearance[second]
            first_vertex = vertices[face[first]]
            second_vertex = vertices[face[second]]
            if abs(first_clearance) <= tolerance:
                intersections.append(first_vertex)
            if abs(second_clearance) <= tolerance:
                intersections.append(second_vertex)
            if first_clearance * second_clearance < 0:
                fraction = first_clearance / (first_clearance - second_clearance)
                intersections.append(
                    first_vertex + fraction * (second_vertex - first_vertex)
                )
        unique_points: list[numpy.ndarray] = []
        for point in intersections:
            if not any(
                numpy.linalg.norm(point - existing) <= tolerance
                for existing in unique_points
            ):
                unique_points.append(point)
        if len(unique_points) == 2:
            segment = numpy.asarray(unique_points, dtype=numpy.float64)
            if numpy.linalg.norm(segment[1] - segment[0]) > tolerance:
                segments.append(segment)
    if not segments:
        return numpy.empty((0, 2, 3), dtype=numpy.float64)
    result = numpy.asarray(segments, dtype=numpy.float64)
    dedupe_tolerance = max(tolerance, min(pitch) * 1e-9)
    quantized = numpy.rint(result / dedupe_tolerance).astype(numpy.int64)
    canonical = numpy.asarray(
        [
            (*min(map(tuple, segment)), *max(map(tuple, segment)))
            for segment in quantized
        ],
        dtype=numpy.int64,
    )
    _, unique_index = numpy.unique(
        canonical,
        axis=0,
        return_index=True,
    )
    return result[numpy.sort(unique_index)]


def _interpolate_height_field(
    vertices: numpy.ndarray,
    height: numpy.ndarray,
    valid: numpy.ndarray,
    *,
    origin: tuple[float, float],
    pitch: tuple[float, float],
) -> tuple[numpy.ndarray, numpy.ndarray]:
    x = numpy.clip((vertices[:, 0] - origin[0]) / pitch[0], 0, height.shape[1] - 1)
    y = numpy.clip((vertices[:, 1] - origin[1]) / pitch[1], 0, height.shape[0] - 1)
    x0 = numpy.floor(x).astype(int)
    y0 = numpy.floor(y).astype(int)
    x1 = numpy.minimum(x0 + 1, height.shape[1] - 1)
    y1 = numpy.minimum(y0 + 1, height.shape[0] - 1)
    x_fraction = x - x0
    y_fraction = y - y0
    sampled = (
        height[y0, x0] * (1 - x_fraction) * (1 - y_fraction)
        + height[y0, x1] * x_fraction * (1 - y_fraction)
        + height[y1, x0] * (1 - x_fraction) * y_fraction
        + height[y1, x1] * x_fraction * y_fraction
    )
    sampled_valid = (
        valid[y0, x0] & valid[y0, x1] & valid[y1, x0] & valid[y1, x1]
    )
    return sampled, sampled_valid


def _unknown_boundary_segments(
    valid_horizontal: numpy.ndarray,
    terrain_grid: numpy.ndarray,
    min_height_grid: numpy.ndarray,
    radar_z: float,
    *,
    origin: tuple[float, float],
    pitch: tuple[float, float],
    radar_xy: tuple[float, float],
    effective_range_m: float,
    payload: CoverageRequest,
) -> numpy.ndarray:
    contours = measure.find_contours(valid_horizontal.astype(numpy.float32), 0.5)
    segments: list[numpy.ndarray] = []
    for contour in contours:
        if len(contour) < 2:
            continue
        points = numpy.empty((len(contour), 3), dtype=numpy.float64)
        points[:, 0] = origin[0] + contour[:, 1] * pitch[0]
        points[:, 1] = origin[1] + contour[:, 0] * pitch[1]
        points[:, 2] = [
            _nearest_valid_height(
                row,
                column,
                valid_horizontal,
                terrain_grid,
                numpy.nan,
            )
            for row, column in contour
        ]
        segments.extend(numpy.stack((points[:-1], points[1:]), axis=1))
    if not segments:
        return numpy.empty((0, 2, 3), dtype=numpy.float64)
    result = numpy.asarray(segments, dtype=numpy.float64)
    finite_height = numpy.isfinite(result[:, :, 2]).all(axis=1)
    dx = result[:, :, 0] - radar_xy[0]
    dy = result[:, :, 1] - radar_xy[1]
    inside_range = dx * dx + dy * dy <= effective_range_m * effective_range_m
    inside_sector = _sector_mask(dx, dy, payload)
    return result[finite_height & (inside_range & inside_sector).all(axis=1)]


def _terrain_shadow_boundary_segments(
    min_height_grid: numpy.ndarray,
    terrain_grid: numpy.ndarray,
    valid_horizontal: numpy.ndarray,
    *,
    origin: tuple[float, float],
    pitch: tuple[float, float],
) -> numpy.ndarray:
    shadow = min_height_grid > 1e-6
    contours = measure.find_contours(
        shadow.astype(numpy.float32),
        0.5,
        mask=valid_horizontal,
    )
    segments: list[numpy.ndarray] = []
    for contour in contours:
        if len(contour) < 2:
            continue
        points = numpy.empty((len(contour), 3), dtype=numpy.float64)
        points[:, 0] = origin[0] + contour[:, 1] * pitch[0]
        points[:, 1] = origin[1] + contour[:, 0] * pitch[1]
        points[:, 2] = [
            _nearest_valid_height(
                row,
                column,
                valid_horizontal,
                terrain_grid,
                numpy.nan,
            )
            for row, column in contour
        ]
        contour_segments = numpy.stack((points[:-1], points[1:]), axis=1)
        finite = numpy.isfinite(contour_segments).all(axis=(1, 2))
        segments.extend(contour_segments[finite])
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
