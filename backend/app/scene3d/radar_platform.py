import math
from pathlib import Path

import numpy
import rasterio
import trimesh
from rasterio.windows import Window

from app.schemas.radar import CoverageRequest
from app.services.coverage_model import PreparedCoverageDem

from .exporter import (
    AnimationSpec,
    AnimationTrack,
    MaterialSpec,
    SceneNode,
    export_glb,
)
from .frame import SceneFrame
from .primitives import tube_mesh
from .radar import SCAN_PERIOD_S, _azimuths


BASE_DISPLAY_SCALE = 100.0
DISPLAY_SCALE = 1000.0
DISPLAY_MAGNIFICATION = DISPLAY_SCALE / BASE_DISPLAY_SCALE
ANTENNA_PHASE_CENTER_HEIGHT_M = 9.6
EQUIPMENT_MATERIAL = MaterialSpec("radar_equipment_olive", (72, 82, 68, 255))
PEDESTAL_MATERIAL = MaterialSpec("radar_pedestal_metal", (70, 78, 80, 255))
TURNTABLE_MATERIAL = MaterialSpec("radar_turntable_metal", (47, 56, 60, 255))
DISH_MATERIAL = MaterialSpec("radar_dish", (199, 205, 198, 255))
FEED_MATERIAL = MaterialSpec("radar_feed", (145, 151, 148, 255))


def write_radar_platform_glb(
    path: Path,
    *,
    task_id: str,
    prepared: PreparedCoverageDem,
    payload: CoverageRequest,
    scan_azimuths_deg: list[float] | None = None,
) -> dict:
    if scan_azimuths_deg is None:
        azimuths = _azimuths(payload)
        scan_azimuths_deg = (
            azimuths
            if payload.coverage.scan_mode == "omni"
            else azimuths[:-1]
        )
    scan_azimuths = numpy.asarray(scan_azimuths_deg, dtype=numpy.float64)
    if len(scan_azimuths) == 0 or not numpy.isfinite(scan_azimuths).all():
        raise ValueError("Radar platform requires finite scan azimuths")

    ground_m = _radar_ground_elevation(prepared)
    frame = SceneFrame.from_projected_points(
        prepared.target_epsg,
        [
            (prepared.radar_x, prepared.radar_y, ground_m),
            (prepared.radar_x, prepared.radar_y, ground_m + 12.5),
        ],
        axes="z_up",
    )
    ground_offset = numpy.asarray([0.0, 0.0, ground_m - frame.origin_altitude_m])
    vertical_scale = max(
        payload.radar.height_m / ANTENNA_PHASE_CENTER_HEIGHT_M,
        0.01,
    )
    display_vertical_scale = vertical_scale * DISPLAY_MAGNIFICATION

    cabinet = trimesh.creation.box(extents=[4.8, 2.6, 3.2])
    cabinet.apply_translation([0, 1.3, 0])

    pedestal = _cylinder_y(radius=1.05, height=3.2, center_y=4.2)

    turntable = trimesh.util.concatenate(
        [
            _cylinder_y(radius=1.65, height=0.7, center_y=6.0),
            _cylinder_y(radius=0.34, height=3.3, center_y=7.85),
        ]
    )

    dish = _parabolic_dish_mesh(
        center=numpy.asarray([0, 9.6, 0], dtype=numpy.float64),
        radius_m=2.75,
        depth_m=0.9,
    )

    feed_arm = tube_mesh(
        numpy.asarray(
            [
                [-0.65, 9.6, 0],
                [1.1, 9.6, 0],
                [2.15, 9.6, 0],
            ],
            dtype=numpy.float64,
        ),
        radius_m=0.09,
        sections=8,
    )
    feed_horn = trimesh.creation.icosphere(subdivisions=2, radius=0.24)
    feed_horn.apply_translation([2.3, 9.6, 0])
    feed_arm = trimesh.util.concatenate([feed_arm, feed_horn])

    for mesh in (cabinet, pedestal, turntable, dish, feed_arm):
        mesh.apply_scale([DISPLAY_SCALE, display_vertical_scale, DISPLAY_SCALE])
        mesh.apply_transform(trimesh.transformations.rotation_matrix(numpy.pi / 2, [1, 0, 0]))
        mesh.apply_translation(ground_offset)

    rotating_names = [
        "radar_platform/azimuth_turntable",
        "radar_platform/antenna_dish",
        "radar_platform/feed_arm",
    ]
    root = SceneNode(
        name="radar_platform",
        extras={
            "kind": "radar_platform",
            "display_scale": DISPLAY_SCALE,
            "display_magnification": DISPLAY_MAGNIFICATION,
        },
        children=[
            SceneNode(
                name="radar_platform/equipment_cabinet",
                mesh=cabinet,
                material=EQUIPMENT_MATERIAL,
                extras={"kind": "platform_component", "role": "equipment_cabinet"},
            ),
            SceneNode(
                name="radar_platform/pedestal",
                mesh=pedestal,
                material=PEDESTAL_MATERIAL,
                extras={"kind": "platform_component", "role": "pedestal"},
            ),
            SceneNode(
                name=rotating_names[0],
                mesh=turntable,
                material=TURNTABLE_MATERIAL,
                extras={"kind": "platform_component", "role": "azimuth_turntable"},
            ),
            SceneNode(
                name=rotating_names[1],
                mesh=dish,
                material=DISH_MATERIAL,
                extras={"kind": "platform_component", "role": "antenna_dish"},
            ),
            SceneNode(
                name=rotating_names[2],
                mesh=feed_arm,
                material=FEED_MATERIAL,
                extras={"kind": "platform_component", "role": "feed_arm"},
            ),
        ],
    )
    times = numpy.linspace(0, SCAN_PERIOD_S, len(scan_azimuths) + 1, dtype=numpy.float32)
    scan_azimuths = numpy.append(scan_azimuths, scan_azimuths[0])
    angles = numpy.radians(90 - scan_azimuths) / 2
    rotations = numpy.column_stack(
        [
            numpy.zeros(len(angles)),
            numpy.zeros(len(angles)),
            numpy.sin(angles),
            numpy.cos(angles),
        ]
    ).astype(numpy.float32)
    animation = AnimationSpec(
        "radar_platform_scan",
        [
            AnimationTrack(
                node_name=name,
                path="rotation",
                times=times,
                values=rotations,
                interpolation="STEP",
            )
            for name in rotating_names
        ],
    )
    metadata = frame.metadata(task_id, "radar")
    metadata.update(
        {
            "asset_kind": "radar_platform",
            "radar_ground_elevation_amsl_m": ground_m,
            "analysis_origin_altitude_amsl_m": ground_m + payload.radar.height_m,
            "dimensions_m": {
                "width": 5.5 * DISPLAY_SCALE,
                "depth": 5.5 * DISPLAY_SCALE,
                "height": 12.35 * display_vertical_scale,
            },
            "display_magnification": DISPLAY_MAGNIFICATION,
            "antenna_phase_center": {
                "height_above_ground_m": payload.radar.height_m,
                "azimuth_deg": float(scan_azimuths[0]),
            },
            "animation": {"name": animation.name, "period_s": SCAN_PERIOD_S},
        }
    )
    export_glb(
        path,
        [root],
        scene_metadata=metadata,
        animations=[animation],
    )
    return metadata


def _radar_ground_elevation(prepared: PreparedCoverageDem) -> float:
    with rasterio.open(prepared.projected_dem) as source:
        row, col = source.index(prepared.radar_x, prepared.radar_y)
        if not (0 <= row < source.height and 0 <= col < source.width):
            raise ValueError("Radar platform origin is outside DEM terrain")
        window = Window(col, row, 1, 1)
        value = float(source.read(1, window=window).item())
        mask = int(source.read_masks(1, window=window).item())
        if mask == 0 or not math.isfinite(value):
            raise ValueError("Radar platform origin is outside valid DEM terrain")
        if source.nodata is not None and math.isclose(value, float(source.nodata)):
            raise ValueError("Radar platform origin is outside valid DEM terrain")
        return value


def _cylinder_y(*, radius: float, height: float, center_y: float) -> trimesh.Trimesh:
    mesh = trimesh.creation.cylinder(radius=radius, height=height, sections=32)
    mesh.apply_transform(
        trimesh.transformations.rotation_matrix(-numpy.pi / 2, [1, 0, 0])
    )
    mesh.apply_translation([0, center_y, 0])
    return mesh


def _parabolic_dish_mesh(*, center, radius_m, depth_m) -> trimesh.Trimesh:
    radial_steps = 12
    angular_steps = 48
    vertices = []
    for radial_index in range(radial_steps + 1):
        radius = radius_m * radial_index / radial_steps
        x = center[0] - depth_m * (1 - (radius / radius_m) ** 2)
        for angle in numpy.linspace(0, 2 * numpy.pi, angular_steps, endpoint=False):
            vertices.append(
                [
                    x,
                    center[1] + radius * numpy.cos(angle),
                    center[2] + radius * numpy.sin(angle),
                ]
            )
    faces = []
    for radial_index in range(radial_steps):
        for angular_index in range(angular_steps):
            nxt = (angular_index + 1) % angular_steps
            a = radial_index * angular_steps + angular_index
            b = radial_index * angular_steps + nxt
            c = (radial_index + 1) * angular_steps + angular_index
            d = (radial_index + 1) * angular_steps + nxt
            faces.extend([[a, c, b], [b, c, d]])
    return trimesh.Trimesh(
        vertices=numpy.asarray(vertices, dtype=numpy.float64),
        faces=numpy.asarray(faces, dtype=numpy.int64),
        process=False,
    )
