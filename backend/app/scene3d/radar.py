from dataclasses import dataclass
import math
from pathlib import Path

import numpy
import rasterio
import trimesh

from app.schemas.radar import CoverageRequest
from app.services.coverage_model import PreparedCoverageDem
from app.services.coverage_range import effective_max_range, radar_equation_max_range

from .exporter import (
    AnimationSpec,
    AnimationTrack,
    MaterialSpec,
    SceneNode,
    export_glb,
)
from .frame import SceneFrame
from .primitives import tube_mesh


EARTH_RADIUS_M = 6_371_000.0
AZIMUTH_STEP_DEG = 3.0
ELEVATION_STEP_DEG = 3.0
SCAN_PERIOD_S = 8.0

SHELL_MATERIAL = MaterialSpec(
    "radar_detectable_shell",
    (35, 190, 176, 54),
    shading="unlit",
    emissive_rgb=(22, 93, 90),
)
GRID_MATERIAL = MaterialSpec(
    "radar_shell_grid",
    (207, 250, 242, 132),
    shading="unlit",
    emissive_rgb=(97, 123, 119),
)
FILL_MATERIAL = MaterialSpec(
    "radar_detectable_fill",
    (28, 224, 218, 72),
    shading="unlit",
    emissive_rgb=(14, 112, 109),
)
SCAN_MATERIAL = MaterialSpec(
    "radar_active_scan",
    (86, 242, 224, 108),
    shading="unlit",
    emissive_rgb=(43, 121, 112),
)
ORIGIN_MATERIAL = MaterialSpec(
    "radar_origin",
    (245, 247, 242, 255),
    shading="unlit",
    emissive_rgb=(123, 124, 121),
)
DIAGNOSTIC_MATERIAL = MaterialSpec(
    "radar_terrain_stop",
    (232, 105, 70, 230),
    shading="unlit",
    emissive_rgb=(116, 53, 35),
)


@dataclass(frozen=True)
class RayResult:
    radius_m: float
    point: tuple[float, float, float]
    termination: str
    closed: bool


def write_radar_coverage_glb(
    path: Path,
    *,
    task_id: str,
    prepared: PreparedCoverageDem,
    payload: CoverageRequest,
) -> dict:
    effective_range_m, radar_equation_range_m = effective_max_range(payload)
    range_basis = (
        "radar_equation" if radar_equation_range_m is not None else "nominal"
    )
    reference_rcs_m2 = payload.reserved_radar_params.target_rcs_m2 or 1.0
    azimuths = _azimuths(payload)
    elevations = _elevations(payload)

    with rasterio.open(prepared.projected_dem) as source:
        terrain = source.read(indexes=[1])[0]
        valid = source.read_masks(indexes=[1])[0] > 0
        transform = source.transform
        nodata = source.nodata

    if prepared.analysis_domain is not None:
        if prepared.analysis_domain.shape != terrain.shape:
            raise ValueError("Radar analysis domain does not match projected DEM")
        valid &= prepared.analysis_domain

    radar_ground_m = _sample_terrain(
        terrain,
        valid,
        transform,
        nodata,
        prepared.radar_x,
        prepared.radar_y,
    )
    if radar_ground_m is None:
        raise ValueError("Radar origin is outside valid DEM terrain")
    radar_altitude_m = radar_ground_m + payload.radar.height_m
    step_m = max(
        max(prepared.resolution_m),
        effective_range_m / 400.0,
        10.0,
    )

    ray_grid: list[list[RayResult]] = []
    terminations: dict[str, int] = {
        "performance": 0,
        "nominal": 0,
        "terrain": 0,
        "dem_boundary": 0,
        "nodata": 0,
        "horizon": 0,
    }
    for elevation_deg in elevations:
        row: list[RayResult] = []
        for azimuth_deg in azimuths:
            result = _trace_ray(
                terrain,
                valid,
                transform,
                nodata,
                prepared,
                payload,
                azimuth_deg,
                elevation_deg,
                radar_altitude_m,
                effective_range_m,
                range_basis,
                step_m,
            )
            row.append(result)
            terminations[result.termination] += 1
        ray_grid.append(row)

    all_points = [
        (prepared.radar_x, prepared.radar_y, radar_altitude_m),
        *(result.point for row in ray_grid for result in row),
    ]
    frame = SceneFrame.from_projected_points(prepared.target_epsg, all_points)
    local_grid = [
        [frame.to_gltf(result.point) for result in row]
        for row in ray_grid
    ]
    shell = _shell_mesh(local_grid, ray_grid, payload.coverage.scan_mode == "omni")
    grid = _grid_mesh(local_grid, ray_grid, payload.coverage.scan_mode == "omni")
    origin = frame.to_gltf(
        (prepared.radar_x, prepared.radar_y, radar_altitude_m)
    )
    origin_mesh = trimesh.creation.icosphere(
        subdivisions=2,
        radius=max(10.0, min(60.0, effective_range_m * 0.002)),
    )
    origin_mesh.apply_translation(origin)
    fill_mesh, interior_sample_count = _interior_fill_mesh(
        origin,
        local_grid,
        ray_grid,
        marker_radius_m=max(2.0, min(14.0, effective_range_m * 0.0003)),
    )
    scan_nodes, scan_ranges_m, scan_animation = _scan_slice_nodes(
        origin,
        local_grid,
        ray_grid,
        wrap=payload.coverage.scan_mode == "omni",
    )
    diagnostic_mesh = _diagnostic_mesh(
        local_grid,
        ray_grid,
        fallback=origin,
        radius=max(4.0, min(20.0, effective_range_m * 0.0004)),
    )

    root = SceneNode(
        name="radar_result",
        extras={"kind": "radar_detection_domain"},
        children=[
            SceneNode(
                name="radar_result/radar_origin",
                mesh=origin_mesh,
                material=ORIGIN_MATERIAL,
                extras={"kind": "radar_origin"},
            ),
            SceneNode(
                name="radar_result/detectable_shell",
                mesh=shell,
                material=SHELL_MATERIAL,
                extras={"kind": "detectable_shell"},
            ),
            SceneNode(
                name="radar_result/detectable_fill",
                mesh=fill_mesh,
                material=FILL_MATERIAL,
                extras={
                    "kind": "detectable_fill",
                    "sample_count": interior_sample_count,
                },
            ),
            SceneNode(
                name="radar_result/shell_grid",
                mesh=grid,
                material=GRID_MATERIAL,
                extras={"kind": "shell_grid"},
            ),
            SceneNode(
                name="radar_result/diagnostics",
                mesh=diagnostic_mesh,
                material=DIAGNOSTIC_MATERIAL,
                extras={
                    "kind": "diagnostics",
                    "terrain_stop_count": terminations["terrain"],
                },
            ),
            *scan_nodes,
        ],
    )
    metadata = frame.metadata(task_id, "radar")
    metadata.update(
        {
            "range_basis": range_basis,
            "reference_rcs_m2": reference_rcs_m2,
            "nominal_max_range_m": payload.coverage.max_range_m,
            "radar_equation_max_range_m": radar_equation_range_m,
            "effective_max_range_m": effective_range_m,
            "radar_ground_elevation_amsl_m": radar_ground_m,
            "radar_altitude_amsl_m": radar_altitude_m,
            "scan_mode": payload.coverage.scan_mode,
            "azimuth_deg": payload.coverage.azimuth_deg,
            "beam_width_deg": payload.coverage.beam_width_deg,
            "min_elevation_deg": payload.advanced.min_elevation_deg,
            "max_elevation_deg": payload.advanced.max_elevation_deg,
            "curvature": {
                "enabled": payload.advanced.use_curvature,
                "coefficient": payload.advanced.curvature_coeff,
            },
            "ray_grid": {
                "azimuth_count": len(azimuths),
                "elevation_count": len(elevations),
                "azimuth_deg": azimuths,
                "elevation_deg": elevations,
                "radius_m": [
                    [result.radius_m for result in row]
                    for row in ray_grid
                ],
                "termination": [
                    [result.termination for result in row]
                    for row in ray_grid
                ],
            },
            "terminations": terminations,
            "open_ray_count": terminations["dem_boundary"] + terminations["nodata"],
            "interior_sample_count": interior_sample_count,
            "scan_animation": {
                "period_s": SCAN_PERIOD_S,
                "slice_count": len(scan_nodes),
                "max_range_m": scan_ranges_m,
            },
            "stage2_target_evaluation": "not_implemented",
        }
    )
    export_glb(
        path,
        [root],
        scene_metadata=metadata,
        animations=[scan_animation],
    )
    return metadata


def _azimuths(payload: CoverageRequest) -> list[float]:
    if payload.coverage.scan_mode == "omni":
        return [float(value) for value in numpy.arange(0, 360, AZIMUTH_STEP_DEG)]
    half = payload.coverage.beam_width_deg / 2
    start = payload.coverage.azimuth_deg - half
    stop = payload.coverage.azimuth_deg + half
    values = list(numpy.arange(start, stop, AZIMUTH_STEP_DEG))
    values.append(stop)
    return [float(value % 360) for value in values]


def _elevations(payload: CoverageRequest) -> list[float]:
    start = payload.advanced.min_elevation_deg
    stop = payload.advanced.max_elevation_deg
    if math.isclose(start, stop):
        return [float(start)]
    values = list(numpy.arange(start, stop, ELEVATION_STEP_DEG))
    values.append(stop)
    return [float(value) for value in values]


def _trace_ray(
    terrain: numpy.ndarray,
    valid: numpy.ndarray,
    transform,
    nodata: float | None,
    prepared: PreparedCoverageDem,
    payload: CoverageRequest,
    azimuth_deg: float,
    elevation_deg: float,
    radar_altitude_m: float,
    effective_range_m: float,
    range_basis: str,
    step_m: float,
) -> RayResult:
    azimuth = math.radians(azimuth_deg)
    elevation = math.radians(elevation_deg)
    horizon_m = _horizon_range(payload, elevation_deg)
    limit_m = min(effective_range_m, horizon_m)
    limit_kind = "horizon" if horizon_m < effective_range_m else range_basis.replace(
        "radar_equation", "performance"
    )
    distance = step_m
    last_distance = 0.0
    while distance < limit_m:
        horizontal = distance * math.cos(elevation)
        x = prepared.radar_x + horizontal * math.sin(azimuth)
        y = prepared.radar_y + horizontal * math.cos(azimuth)
        altitude = radar_altitude_m + distance * math.sin(elevation)
        location = _terrain_index(transform, terrain.shape, x, y)
        if location is None:
            return _ray_result(
                last_distance,
                azimuth,
                elevation,
                prepared,
                radar_altitude_m,
                "dem_boundary",
                False,
            )
        row, col = location
        if not valid[row, col]:
            return _ray_result(
                last_distance,
                azimuth,
                elevation,
                prepared,
                radar_altitude_m,
                "nodata",
                False,
            )
        terrain_m = float(terrain[row, col])
        if not math.isfinite(terrain_m) or (
            nodata is not None and math.isclose(terrain_m, float(nodata))
        ):
            return _ray_result(
                last_distance,
                azimuth,
                elevation,
                prepared,
                radar_altitude_m,
                "nodata",
                False,
            )
        if altitude <= terrain_m:
            return _ray_result(
                distance,
                azimuth,
                elevation,
                prepared,
                radar_altitude_m,
                "terrain",
                True,
                altitude_m=terrain_m,
            )
        last_distance = distance
        distance += step_m
    return _ray_result(
        limit_m,
        azimuth,
        elevation,
        prepared,
        radar_altitude_m,
        limit_kind,
        True,
    )


def _horizon_range(payload: CoverageRequest, elevation_deg: float) -> float:
    if (
        not payload.advanced.use_curvature
        or payload.advanced.curvature_coeff <= 0
        or elevation_deg > 0
    ):
        return math.inf
    effective_radius = EARTH_RADIUS_M / payload.advanced.curvature_coeff
    return math.sqrt(2 * effective_radius * max(payload.radar.height_m, 0.0))


def _ray_result(
    distance: float,
    azimuth: float,
    elevation: float,
    prepared: PreparedCoverageDem,
    radar_altitude_m: float,
    termination: str,
    closed: bool,
    *,
    altitude_m: float | None = None,
) -> RayResult:
    horizontal = distance * math.cos(elevation)
    return RayResult(
        radius_m=float(distance),
        point=(
            prepared.radar_x + horizontal * math.sin(azimuth),
            prepared.radar_y + horizontal * math.cos(azimuth),
            altitude_m
            if altitude_m is not None
            else radar_altitude_m + distance * math.sin(elevation),
        ),
        termination=termination,
        closed=closed,
    )


def _terrain_index(transform, shape: tuple[int, int], x: float, y: float):
    col, row = ~transform * (x, y)
    row_index = int(math.floor(row))
    col_index = int(math.floor(col))
    if not (0 <= row_index < shape[0] and 0 <= col_index < shape[1]):
        return None
    return row_index, col_index


def _sample_terrain(terrain, valid, transform, nodata, x, y):
    location = _terrain_index(transform, terrain.shape, x, y)
    if location is None:
        return None
    row, col = location
    value = float(terrain[row, col])
    if not valid[row, col] or not math.isfinite(value):
        return None
    if nodata is not None and math.isclose(value, float(nodata)):
        return None
    return value


def _shell_mesh(local_grid, ray_grid, wrap: bool) -> trimesh.Trimesh:
    elevation_count = len(local_grid)
    azimuth_count = len(local_grid[0])
    vertices = numpy.asarray(
        [point for row in local_grid for point in row],
        dtype=numpy.float64,
    )
    faces: list[list[int]] = []
    azimuth_cells = azimuth_count if wrap else azimuth_count - 1
    for elevation_index in range(elevation_count - 1):
        for azimuth_index in range(azimuth_cells):
            next_azimuth = (azimuth_index + 1) % azimuth_count
            corners = [
                ray_grid[elevation_index][azimuth_index],
                ray_grid[elevation_index][next_azimuth],
                ray_grid[elevation_index + 1][azimuth_index],
                ray_grid[elevation_index + 1][next_azimuth],
            ]
            if not all(item.closed and item.radius_m > 0 for item in corners):
                continue
            termination_kinds = {item.termination for item in corners}
            if "terrain" in termination_kinds and len(termination_kinds) > 1:
                continue
            a = elevation_index * azimuth_count + azimuth_index
            b = elevation_index * azimuth_count + next_azimuth
            c = (elevation_index + 1) * azimuth_count + azimuth_index
            d = (elevation_index + 1) * azimuth_count + next_azimuth
            faces.extend([[a, c, b], [b, c, d]])
    if not faces:
        raise ValueError("Radar ray grid produced no closed shell faces")
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=False)


def _grid_mesh(local_grid, ray_grid, wrap: bool) -> trimesh.Trimesh:
    paths: list[numpy.ndarray] = []
    azimuth_count = len(local_grid[0])
    azimuth_stride = max(1, round(12 / AZIMUTH_STEP_DEG))
    elevation_stride = max(1, round(6 / ELEVATION_STEP_DEG))
    for azimuth_index in range(0, azimuth_count, azimuth_stride):
        _append_closed_paths(
            paths,
            [row[azimuth_index] for row in local_grid],
            [row[azimuth_index] for row in ray_grid],
        )
    for elevation_index in range(0, len(local_grid), elevation_stride):
        points = list(local_grid[elevation_index])
        results = list(ray_grid[elevation_index])
        if wrap:
            points.append(points[0])
            results.append(results[0])
        _append_closed_paths(paths, points, results)
    meshes = [tube_mesh(path, radius_m=2.0, sections=6) for path in paths]
    if not meshes:
        raise ValueError("Radar ray grid produced no shell grid lines")
    return trimesh.util.concatenate(meshes)


def _append_closed_paths(paths, points, results) -> None:
    current: list[numpy.ndarray] = []
    for point, result in zip(points, results):
        if result.closed and result.radius_m > 0:
            current.append(point)
        else:
            if len(current) >= 2:
                paths.append(numpy.asarray(current))
            current = []
    if len(current) >= 2:
        paths.append(numpy.asarray(current))


def _diagnostic_mesh(local_grid, ray_grid, *, fallback, radius):
    points = [
        local_grid[elevation_index][azimuth_index]
        for elevation_index, row in enumerate(ray_grid)
        for azimuth_index, result in enumerate(row)
        if result.termination == "terrain" and result.radius_m > 0
    ]
    if not points:
        points = [fallback]
    meshes = []
    for point in points:
        marker = trimesh.creation.icosphere(subdivisions=1, radius=radius)
        marker.apply_translation(point)
        meshes.append(marker)
    return trimesh.util.concatenate(meshes)


def _interior_fill_mesh(origin, local_grid, ray_grid, *, marker_radius_m):
    origin = numpy.asarray(origin, dtype=numpy.float64)
    centers = []
    for elevation_index in range(0, len(local_grid), 2):
        for azimuth_index in range(0, len(local_grid[elevation_index]), 2):
            result = ray_grid[elevation_index][azimuth_index]
            if not result.closed or result.radius_m <= 0:
                continue
            endpoint = numpy.asarray(
                local_grid[elevation_index][azimuth_index],
                dtype=numpy.float64,
            )
            for fraction in (0.2, 0.4, 0.6, 0.8):
                centers.append(origin + (endpoint - origin) * fraction)
    if not centers:
        centers = [origin]

    offsets = numpy.asarray(
        [
            [marker_radius_m, 0, 0],
            [-marker_radius_m, 0, 0],
            [0, marker_radius_m, 0],
            [0, -marker_radius_m, 0],
            [0, 0, marker_radius_m],
            [0, 0, -marker_radius_m],
        ],
        dtype=numpy.float64,
    )
    local_faces = numpy.asarray(
        [
            [0, 2, 4], [4, 2, 1], [1, 2, 5], [5, 2, 0],
            [4, 3, 0], [1, 3, 4], [5, 3, 1], [0, 3, 5],
        ],
        dtype=numpy.int64,
    )
    vertices = numpy.vstack([center + offsets for center in centers])
    faces = numpy.vstack(
        [local_faces + index * len(offsets) for index in range(len(centers))]
    )
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=False), len(centers)


def _scan_slice_nodes(origin, local_grid, ray_grid, *, wrap):
    origin = numpy.asarray(origin, dtype=numpy.float64)
    azimuth_count = len(local_grid[0])
    cell_count = azimuth_count if wrap else azimuth_count - 1
    nodes = []
    ranges_m = []
    for azimuth_index in range(cell_count):
        next_azimuth = (azimuth_index + 1) % azimuth_count
        mesh = _scan_slice_mesh(
            origin,
            local_grid,
            ray_grid,
            azimuth_index,
            next_azimuth,
        )
        if mesh is None:
            continue
        closed_ranges = [
            result.radius_m
            for row in ray_grid
            for result in (row[azimuth_index], row[next_azimuth])
            if result.closed and result.radius_m > 0
        ]
        name = f"radar_result/scan_slice_{len(nodes):03d}"
        nodes.append(
            SceneNode(
                name=name,
                mesh=mesh,
                material=SCAN_MATERIAL,
                extras={
                    "kind": "scan_slice",
                    "azimuth_index": azimuth_index,
                },
            )
        )
        ranges_m.append(float(max(closed_ranges)))

    if not nodes:
        raise ValueError("Radar ray grid produced no animated scan slices")
    times = numpy.linspace(0, SCAN_PERIOD_S, len(nodes) + 1, dtype=numpy.float32)
    tracks = []
    for node_index, node in enumerate(nodes):
        values = numpy.zeros((len(times), 3), dtype=numpy.float32)
        for frame_index in range(len(times)):
            phase = frame_index % len(nodes)
            if phase in {node_index, (node_index + 1) % len(nodes)}:
                values[frame_index] = 1
        tracks.append(
            AnimationTrack(
                node_name=node.name,
                path="scale",
                times=times,
                values=values,
                interpolation="STEP",
            )
        )
    return nodes, ranges_m, AnimationSpec("radar_detection_scan", tracks)


def _scan_slice_mesh(origin, local_grid, ray_grid, azimuth_index, next_azimuth):
    elevation_count = len(local_grid)
    side_a = [numpy.asarray(row[azimuth_index]) for row in local_grid]
    side_b = [numpy.asarray(row[next_azimuth]) for row in local_grid]
    vertices = numpy.vstack([origin, *side_a, *side_b])
    faces = []
    side_b_offset = 1 + elevation_count
    for elevation_index in range(elevation_count - 1):
        a0 = ray_grid[elevation_index][azimuth_index]
        a1 = ray_grid[elevation_index + 1][azimuth_index]
        b0 = ray_grid[elevation_index][next_azimuth]
        b1 = ray_grid[elevation_index + 1][next_azimuth]
        if a0.closed and a1.closed and a0.radius_m > 0 and a1.radius_m > 0:
            faces.append([0, 1 + elevation_index, 2 + elevation_index])
        if b0.closed and b1.closed and b0.radius_m > 0 and b1.radius_m > 0:
            faces.append([0, side_b_offset + elevation_index + 1, side_b_offset + elevation_index])
        corners = [a0, a1, b0, b1]
        termination_kinds = {item.termination for item in corners}
        if (
            all(item.closed and item.radius_m > 0 for item in corners)
            and not ("terrain" in termination_kinds and len(termination_kinds) > 1)
        ):
            a = 1 + elevation_index
            c = a + 1
            b = side_b_offset + elevation_index
            d = b + 1
            faces.extend([[a, c, b], [b, c, d]])
    if not faces:
        return None
    return trimesh.Trimesh(
        vertices=vertices,
        faces=numpy.asarray(faces, dtype=numpy.int64),
        process=False,
    )
