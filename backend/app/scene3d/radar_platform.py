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


SCAN_PERIOD_S = 8.0
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
) -> dict:
    ground_m = _radar_ground_elevation(prepared)
    frame = SceneFrame.from_projected_points(
        prepared.target_epsg,
        [
            (prepared.radar_x, prepared.radar_y, ground_m),
            (prepared.radar_x, prepared.radar_y, ground_m + 12.5),
        ],
    )
    base = frame.to_gltf((prepared.radar_x, prepared.radar_y, ground_m))

    cabinet = trimesh.creation.box(extents=[4.8, 2.6, 3.2])
    cabinet.apply_translation(base + numpy.asarray([0, 1.3, 0]))

    pedestal = _cylinder_y(radius=1.05, height=3.2, center_y=4.2)
    pedestal.apply_translation(base)

    turntable = trimesh.util.concatenate(
        [
            _cylinder_y(radius=1.65, height=0.7, center_y=6.0),
            _cylinder_y(radius=0.34, height=3.3, center_y=7.85),
        ]
    )
    turntable.apply_translation(base)

    dish = _parabolic_dish_mesh(
        center=numpy.asarray([0, 9.6, 0], dtype=numpy.float64),
        radius_m=2.75,
        depth_m=0.9,
    )
    dish.apply_translation(base)

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
    feed_arm.apply_translation(base)

    rotating_names = [
        "radar_platform/azimuth_turntable",
        "radar_platform/antenna_dish",
        "radar_platform/feed_arm",
    ]
    root = SceneNode(
        name="radar_platform",
        extras={"kind": "radar_platform", "display_scale": 1.0},
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
    times = numpy.asarray([0, 2, 4, 6, 8], dtype=numpy.float32)
    angles = numpy.radians([0, 90, 180, 270, 360]) / 2
    rotations = numpy.column_stack(
        [
            numpy.zeros(len(angles)),
            numpy.sin(angles),
            numpy.zeros(len(angles)),
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
            "dimensions_m": {"width": 5.5, "depth": 5.5, "height": 12.35},
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
