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
from .primitives import continuous_tube_mesh
from .radar_volume import RadarVisibilityVolume, build_radar_visibility_envelope


EARTH_RADIUS_M = 6_371_000.0
AZIMUTH_STEP_DEG = 1.5
ELEVATION_STEP_DEG = 1.5
SCAN_PERIOD_S = 20.0
VISUAL_DOME_ELEVATION_STEP_DEG = 5.0
VISUAL_DOME_VERTICAL_RATIO = 1.0
DIAGNOSTIC_MAX_MARKERS = 256
ENVELOPE_GRID_SIZE = 256
BLOCKED_GROUND_OFFSET_M = 2.0

SHELL_MATERIAL = MaterialSpec(
    "radar_detectable_shell",
    (41, 74, 53, 34),
    shading="unlit",
    emissive_rgb=(20, 44, 30),
)
DETECTION_FLOOR_MATERIAL = MaterialSpec(
    "radar_detection_floor",
    (20, 73, 48, 210),
    shading="unlit",
    emissive_rgb=(10, 38, 24),
)
BLOCKED_VOLUME_MATERIAL = MaterialSpec(
    "radar_terrain_blocked_volume",
    (55, 60, 58, 48),
    shading="unlit",
    emissive_rgb=(25, 28, 27),
)
BLOCKED_GROUND_MATERIAL = MaterialSpec(
    "radar_terrain_blocked_ground",
    (44, 48, 46, 150),
    shading="unlit",
    emissive_rgb=(22, 24, 23),
)
BLOCKED_CONTACT_MATERIAL = MaterialSpec(
    "radar_terrain_blocked_contact",
    (224, 76, 48, 255),
    shading="unlit",
    emissive_rgb=(150, 34, 20),
)
GRID_MATERIAL = MaterialSpec(
    "radar_shell_grid",
    (255, 255, 255, 255),
    shading="unlit",
    emissive_rgb=(180, 180, 180),
)
FLOOR_BOUNDARY_MATERIAL = MaterialSpec(
    "radar_detection_floor_boundary",
    (255, 176, 32, 255),
    shading="unlit",
    emissive_rgb=(180, 96, 0),
)
SCAN_MATERIAL = MaterialSpec(
    "radar_active_scan",
    (69, 166, 107, 104),
    shading="unlit",
    emissive_rgb=(35, 92, 56),
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
GROUND_CONTACT_MATERIAL = MaterialSpec(
    "radar_ground_contact",
    (244, 48, 48, 255),
    shading="unlit",
    emissive_rgb=(180, 18, 18),
)
UNKNOWN_BOUNDARY_MATERIAL = MaterialSpec(
    "radar_unknown_boundary",
    (112, 119, 124, 255),
    shading="unlit",
    emissive_rgb=(56, 60, 62),
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
    min_visible_height: Path | None = None,
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

    visual_grid, visual_ray_grid, visual_radius_profile = _visual_dome_grid(
        prepared,
        azimuths,
        radar_altitude_m,
        effective_range_m,
    )
    visibility_volume = (
        build_radar_visibility_envelope(
            prepared,
            payload,
            min_visible_height,
            grid_shape=(ENVELOPE_GRID_SIZE, ENVELOPE_GRID_SIZE, 2),
        )
        if min_visible_height is not None
        else None
    )
    all_points = [
        (prepared.radar_x, prepared.radar_y, radar_altitude_m),
        *(result.point for row in ray_grid for result in row),
        *(point for row in visual_grid for point in row),
        *(
            (tuple(point) for point in visibility_volume.vertices)
            if visibility_volume is not None
            else ()
        ),
        *(
            (
                tuple(point)
                for point in visibility_volume.blocked_vertices
            )
            if visibility_volume is not None
            and visibility_volume.blocked_vertices is not None
            else ()
        ),
        *(
            (
                tuple(point)
                for segments in (
                    visibility_volume.terrain_segments,
                    visibility_volume.unknown_segments,
                )
                for segment in segments
                for point in segment
            )
            if visibility_volume is not None
            else ()
        )
    ]
    frame = SceneFrame.from_projected_points(prepared.target_epsg, all_points)
    actual_local_grid = [
        [frame.to_gltf(result.point) for result in row]
        for row in ray_grid
    ]
    local_grid = [
        [frame.to_gltf(point) for point in row]
        for row in visual_grid
    ]
    wrap = payload.coverage.scan_mode == "omni"
    shell = (
        _visibility_volume_mesh(visibility_volume, frame)
        if visibility_volume is not None
        else _shell_mesh(local_grid, visual_ray_grid, wrap)
    )
    detection_floor = (
        _visibility_floor_mesh(visibility_volume, frame)
        if visibility_volume is not None
        else None
    )
    blocked_volume = (
        _blocked_volume_mesh(visibility_volume, frame)
        if visibility_volume is not None
        else None
    )
    blocked_ground = (
        _blocked_ground_mesh(
            visibility_volume,
            frame,
            altitude_offset_m=BLOCKED_GROUND_OFFSET_M,
        )
        if visibility_volume is not None
        else None
    )
    grid = _grid_mesh(
        actual_local_grid,
        ray_grid,
        wrap,
        radius_m=max(3.0, min(45.0, effective_range_m * 0.0008)),
    )
    floor_boundary = (
        _lower_surface_boundary_mesh(
            visibility_volume,
            frame,
            radius_m=max(10.0, min(120.0, effective_range_m * 0.002)),
        )
        if visibility_volume is not None
        else None
    )
    contact_radius_m = max(10.0, min(40.0, effective_range_m * 0.0007))
    blocked_contact = (
        _visibility_segment_mesh(
            visibility_volume.blocked_contact_segments,
            frame,
            radius_m=max(12.0, min(50.0, effective_range_m * 0.0008)),
            altitude_offset_m=BLOCKED_GROUND_OFFSET_M,
        )
        if visibility_volume is not None
        and visibility_volume.blocked_contact_segments is not None
        else None
    )
    terrain_contact = (
        _visibility_segment_mesh(
            visibility_volume.terrain_segments,
            frame,
            radius_m=contact_radius_m,
        )
        if visibility_volume is not None
        else None
    )
    unknown_boundary = (
        _visibility_segment_mesh(
            visibility_volume.unknown_segments,
            frame,
            radius_m=contact_radius_m,
        )
        if visibility_volume is not None
        else None
    )
    ground_contact = (
        None
        if visibility_volume is not None
        else _ground_contact_mesh(
            local_grid,
            visual_ray_grid,
            wrap,
            radius_m=contact_radius_m,
        )
    )
    origin = frame.to_gltf(
        (prepared.radar_x, prepared.radar_y, radar_altitude_m)
    )
    origin_mesh = trimesh.creation.icosphere(
        subdivisions=2,
        radius=max(10.0, min(60.0, effective_range_m * 0.002)),
    )
    origin_mesh.apply_translation(origin)
    interior_sample_count = 0
    scan_nodes, scan_ranges_m, scan_animation = _scan_slice_nodes(
        origin,
        actual_local_grid,
        ray_grid,
        wrap=wrap,
    )
    diagnostic_mesh = _diagnostic_mesh(
        actual_local_grid,
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
            *(
                [
                    SceneNode(
                        name="radar_result/detection_floor",
                        mesh=detection_floor,
                        material=DETECTION_FLOOR_MATERIAL,
                        extras={"kind": "detection_floor"},
                    )
                ]
                if detection_floor is not None
                else []
            ),
            *(
                [
                    SceneNode(
                        name="radar_result/terrain_blocked_volume",
                        mesh=blocked_volume,
                        material=BLOCKED_VOLUME_MATERIAL,
                        extras={"kind": "terrain_blocked_volume"},
                    )
                ]
                if blocked_volume is not None
                else []
            ),
            *(
                [
                    SceneNode(
                        name="radar_result/terrain_blocked_ground",
                        mesh=blocked_ground,
                        material=BLOCKED_GROUND_MATERIAL,
                        extras={"kind": "terrain_blocked_ground"},
                    )
                ]
                if blocked_ground is not None
                else []
            ),
            SceneNode(
                name="radar_result/shell_grid",
                mesh=grid,
                material=GRID_MATERIAL,
                extras={"kind": "shell_grid"},
            ),
            *(
                [
                    SceneNode(
                        name="radar_result/detection_floor_boundary",
                        mesh=floor_boundary,
                        material=FLOOR_BOUNDARY_MATERIAL,
                        extras={"kind": "detection_floor_boundary"},
                    )
                ]
                if floor_boundary is not None
                else []
            ),
            *(
                [
                    SceneNode(
                        name="radar_result/terrain_contact",
                        mesh=terrain_contact,
                        material=GROUND_CONTACT_MATERIAL,
                        extras={"kind": "terrain_contact"},
                    )
                ]
                if terrain_contact is not None
                else []
            ),
            *(
                [
                    SceneNode(
                        name="radar_result/terrain_blocked_contact",
                        mesh=blocked_contact,
                        material=BLOCKED_CONTACT_MATERIAL,
                        extras={"kind": "terrain_blocked_contact"},
                    )
                ]
                if blocked_contact is not None
                else []
            ),
            *(
                [
                    SceneNode(
                        name="radar_result/unknown_boundary",
                        mesh=unknown_boundary,
                        material=UNKNOWN_BOUNDARY_MATERIAL,
                        extras={"kind": "unknown_boundary"},
                    )
                ]
                if unknown_boundary is not None
                else []
            ),
            *(
                [
                    SceneNode(
                        name="radar_result/ground_contact",
                        mesh=ground_contact,
                        material=GROUND_CONTACT_MATERIAL,
                        extras={"kind": "ground_contact"},
                    )
                ]
                if ground_contact is not None
                else []
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
            "visual_dome": {
                "terrain_conforming": False,
                "vertical_ratio": VISUAL_DOME_VERTICAL_RATIO,
                "ground_contact": False,
                "radius_m": visual_radius_profile,
            },
            "stage2_target_evaluation": {
                "status": "available",
                "endpoint": f"/api/radar/coverage/{task_id}/evaluate-target",
                "coordinates": {
                    "x": "longitude_deg_wgs84",
                    "y": "latitude_deg_wgs84",
                    "z": "altitude_m_amsl",
                },
                "target_type_optional": True,
            },
        }
    )
    if visibility_volume is not None:
        lower_faces = _lower_face_mask(visibility_volume.faces)
        blocked_faces = (
            visibility_volume.blocked_faces
            if visibility_volume.blocked_faces is not None
            else numpy.empty((0, 3), dtype=numpy.int64)
        )
        blocked_lower_faces = _lower_face_mask(blocked_faces)
        metadata["visibility_volume"] = {
            "method": "dem_height_field_envelope",
            "nominal_elevation_deg": [0, 90],
            "scan_elevation_deg": [
                payload.advanced.min_elevation_deg,
                payload.advanced.max_elevation_deg,
            ],
            "grid_shape": list(visibility_volume.grid_shape),
            "occupied_voxel_count": visibility_volume.occupied_voxel_count,
            "face_count": len(visibility_volume.faces),
            "shell_face_count": int(numpy.count_nonzero(~lower_faces)),
            "floor_face_count": int(numpy.count_nonzero(lower_faces)),
            "blocked_face_count": int(
                numpy.count_nonzero(~blocked_lower_faces)
            ),
            "blocked_ground_face_count": int(
                numpy.count_nonzero(blocked_lower_faces)
            ),
            "blocked_contact_segment_count": (
                len(visibility_volume.blocked_contact_segments)
                if visibility_volume.blocked_contact_segments is not None
                else 0
            ),
            "terrain_segment_count": len(visibility_volume.terrain_segments),
            "unknown_segment_count": len(visibility_volume.unknown_segments),
        }
    export_glb(
        path,
        [root],
        scene_metadata=metadata,
        animations=[scan_animation],
        include_normals=False,
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


def _visibility_volume_mesh(
    volume: RadarVisibilityVolume,
    frame: SceneFrame,
) -> trimesh.Trimesh:
    faces = volume.faces[~_lower_face_mask(volume.faces)]
    return _indexed_projected_mesh(volume.vertices, faces, frame)


def _visibility_floor_mesh(
    volume: RadarVisibilityVolume,
    frame: SceneFrame,
) -> trimesh.Trimesh | None:
    floor_faces = volume.faces[_lower_face_mask(volume.faces)]
    if len(floor_faces) == 0:
        return None
    return _indexed_projected_mesh(volume.vertices, floor_faces, frame)


def _blocked_volume_mesh(
    volume: RadarVisibilityVolume,
    frame: SceneFrame,
) -> trimesh.Trimesh | None:
    if volume.blocked_vertices is None or volume.blocked_faces is None:
        return None
    faces = volume.blocked_faces[~_lower_face_mask(volume.blocked_faces)]
    if len(volume.blocked_vertices) == 0 or len(faces) == 0:
        return None
    return _indexed_projected_mesh(volume.blocked_vertices, faces, frame)


def _blocked_ground_mesh(
    volume: RadarVisibilityVolume,
    frame: SceneFrame,
    *,
    altitude_offset_m: float,
) -> trimesh.Trimesh | None:
    if volume.blocked_vertices is None or volume.blocked_faces is None:
        return None
    faces = volume.blocked_faces[_lower_face_mask(volume.blocked_faces)]
    if len(faces) == 0:
        return None
    return _indexed_projected_mesh(
        volume.blocked_vertices,
        faces,
        frame,
        altitude_offset_m=altitude_offset_m,
    )


def _indexed_projected_mesh(
    projected_vertices: numpy.ndarray,
    faces: numpy.ndarray,
    frame: SceneFrame,
    *,
    altitude_offset_m: float = 0.0,
) -> trimesh.Trimesh:
    used = numpy.unique(faces)
    selected = numpy.asarray(projected_vertices[used], dtype=numpy.float64).copy()
    selected[:, 2] += altitude_offset_m
    remap = numpy.full(len(projected_vertices), -1, dtype=numpy.int64)
    remap[used] = numpy.arange(len(used), dtype=numpy.int64)
    vertices = numpy.asarray(
        [frame.to_gltf(tuple(point)) for point in selected],
        dtype=numpy.float64,
    )
    return trimesh.Trimesh(
        vertices=vertices,
        faces=remap[faces],
        process=False,
    )


def _lower_face_mask(faces: numpy.ndarray) -> numpy.ndarray:
    if len(faces) == 0:
        return numpy.empty(0, dtype=bool)
    return numpy.all(numpy.asarray(faces) % 2 == 0, axis=1)


def _lower_surface_boundary_mesh(
    volume: RadarVisibilityVolume,
    frame: SceneFrame,
    *,
    radius_m: float,
) -> trimesh.Trimesh | None:
    return _lower_face_boundary_mesh(
        volume.vertices,
        volume.faces,
        frame,
        radius_m=radius_m,
    )


def _lower_face_boundary_mesh(
    vertices: numpy.ndarray,
    faces: numpy.ndarray,
    frame: SceneFrame,
    *,
    radius_m: float,
    altitude_offset_m: float = 0.0,
) -> trimesh.Trimesh | None:
    edge_counts: dict[tuple[int, int], int] = {}
    for face in faces:
        indices = [int(index) for index in face]
        if any(index % 2 for index in indices):
            continue
        for first, second in ((indices[0], indices[1]), (indices[1], indices[2]), (indices[2], indices[0])):
            edge = tuple(sorted((first, second)))
            edge_counts[edge] = edge_counts.get(edge, 0) + 1

    meshes = []
    for (first, second), count in edge_counts.items():
        if count != 1:
            continue
        path = numpy.asarray(
            [
                frame.to_gltf(
                    tuple(vertices[first] + (0.0, 0.0, altitude_offset_m))
                ),
                frame.to_gltf(
                    tuple(vertices[second] + (0.0, 0.0, altitude_offset_m))
                ),
            ],
            dtype=numpy.float64,
        )
        if numpy.linalg.norm(path[1] - path[0]) > 0:
            meshes.append(
                continuous_tube_mesh(path, radius_m=radius_m, sections=6)
            )
    if not meshes:
        return None
    return trimesh.util.concatenate(meshes)


def _visibility_segment_mesh(
    segments: numpy.ndarray,
    frame: SceneFrame,
    *,
    radius_m: float,
    altitude_offset_m: float = 0.0,
) -> trimesh.Trimesh | None:
    meshes: list[trimesh.Trimesh] = []
    for segment in segments:
        path = numpy.asarray(
            [
                frame.to_gltf(
                    tuple(point + (0.0, 0.0, altitude_offset_m))
                )
                for point in segment
            ],
            dtype=numpy.float64,
        )
        meshes.append(continuous_tube_mesh(path, radius_m=radius_m, sections=6))
    if not meshes:
        return None
    return trimesh.util.concatenate(meshes)


def _visual_dome_grid(
    prepared,
    azimuths,
    radar_altitude_m,
    effective_range_m,
):
    radius_profile = [float(effective_range_m)] * len(azimuths)
    visual_angles = numpy.arange(
        0,
        90 + VISUAL_DOME_ELEVATION_STEP_DEG,
        VISUAL_DOME_ELEVATION_STEP_DEG,
    )
    projected_grid = []
    result_grid = []
    for visual_angle_deg in visual_angles:
        angle = math.radians(float(visual_angle_deg))
        points = []
        results = []
        for azimuth_deg in azimuths:
            azimuth = math.radians(azimuth_deg)
            horizontal = effective_range_m * math.cos(angle)
            x = prepared.radar_x + horizontal * math.sin(azimuth)
            y = prepared.radar_y + horizontal * math.cos(azimuth)
            altitude = radar_altitude_m + effective_range_m * math.sin(angle)
            point = (x, y, altitude)
            points.append(point)
            results.append(
                RayResult(
                    radius_m=effective_range_m,
                    point=point,
                    termination="nominal",
                    closed=True,
                )
            )
        projected_grid.append(points)
        result_grid.append(results)
    return projected_grid, result_grid, radius_profile


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


def _ground_contact_mesh(local_grid, ray_grid, wrap: bool, *, radius_m: float):
    points = list(local_grid[0])
    results = list(ray_grid[0])
    if wrap:
        points.append(points[0])
        results.append(results[0])
    paths: list[numpy.ndarray] = []
    _append_closed_paths(paths, points, results)
    if not paths:
        raise ValueError("Radar visual dome produced no ground contact line")
    return trimesh.util.concatenate(
        [
            continuous_tube_mesh(path, radius_m=radius_m, sections=8)
            for path in paths
        ]
    )


def _grid_strides() -> tuple[int, int]:
    return (
        max(1, round(6 / AZIMUTH_STEP_DEG)),
        max(1, round(5 / ELEVATION_STEP_DEG)),
    )


def _grid_mesh(
    local_grid,
    ray_grid,
    wrap: bool,
    *,
    radius_m: float = 2.0,
) -> trimesh.Trimesh:
    paths: list[numpy.ndarray] = []
    azimuth_count = len(local_grid[0])
    azimuth_stride, elevation_stride = _grid_strides()
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
    meshes = [
        continuous_tube_mesh(path, radius_m=radius_m, sections=6)
        for path in paths
    ]
    if not meshes:
        raise ValueError("Radar ray grid produced no shell grid lines")
    return trimesh.util.concatenate(meshes)


def _append_closed_paths(paths, points, results) -> None:
    current: list[numpy.ndarray] = []
    for point, result in zip(points, results):
        if result.closed and result.radius_m > 0:
            current.append(point)
        else:
            _append_distinct_path(paths, current)
            current = []
    _append_distinct_path(paths, current)


def _append_distinct_path(paths, points) -> None:
    if len(points) < 2:
        return
    values = numpy.asarray(points)
    if numpy.any(numpy.linalg.norm(numpy.diff(values, axis=0), axis=1) > 1e-9):
        paths.append(values)


def _diagnostic_mesh(local_grid, ray_grid, *, fallback, radius):
    points = [
        local_grid[elevation_index][azimuth_index]
        for elevation_index, row in enumerate(ray_grid)
        for azimuth_index, result in enumerate(row)
        if result.termination == "terrain" and result.radius_m > 0
    ]
    if not points:
        points = [fallback]
    elif len(points) > DIAGNOSTIC_MAX_MARKERS:
        indices = numpy.linspace(
            0,
            len(points) - 1,
            DIAGNOSTIC_MAX_MARKERS,
            dtype=numpy.int64,
        )
        points = [points[index] for index in indices]
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
    tracks = []
    phase_duration_s = SCAN_PERIOD_S / len(nodes)
    for node_index, node in enumerate(nodes):
        active_phases = {node_index, (node_index + 1) % len(nodes)}
        states = [0 in active_phases]
        times = [0.0]
        for phase in range(1, len(nodes)):
            active = phase in active_phases
            if active != states[-1]:
                times.append(phase * phase_duration_s)
                states.append(active)
        times.append(SCAN_PERIOD_S)
        states.append(0 in active_phases)
        values = numpy.repeat(
            numpy.asarray(states, dtype=numpy.float32)[:, numpy.newaxis],
            3,
            axis=1,
        )
        tracks.append(
            AnimationTrack(
                node_name=node.name,
                path="scale",
                times=numpy.asarray(times, dtype=numpy.float32),
                values=values,
                interpolation="STEP",
            )
        )
    return nodes, ranges_m, AnimationSpec("radar_detection_scan", tracks)


def _scan_slice_mesh(origin, local_grid, ray_grid, azimuth_index, next_azimuth):
    profile = [numpy.asarray(row[azimuth_index]) for row in local_grid]
    vertices = numpy.vstack([origin, *profile])
    faces = []
    for elevation_index in range(len(profile) - 1):
        current = ray_grid[elevation_index][azimuth_index]
        following = ray_grid[elevation_index + 1][azimuth_index]
        if current.closed and following.closed:
            faces.append([0, 1 + elevation_index, 2 + elevation_index])
    if not faces:
        return None
    return trimesh.Trimesh(
        vertices=vertices,
        faces=numpy.asarray(faces, dtype=numpy.int64),
        process=False,
    )
