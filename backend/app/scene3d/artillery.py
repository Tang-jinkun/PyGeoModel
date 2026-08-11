from pathlib import Path

import numpy
import trimesh

from .exporter import MaterialSpec, SceneNode, export_glb
from .frame import SceneFrame
from .primitives import continuous_tube_mesh


TRAJECTORY_MATERIAL = MaterialSpec(
    "artillery_trajectory",
    (34, 197, 94, 255),
    shading="unlit",
    emissive_rgb=(17, 98, 47),
)
BATTERY_MATERIAL = MaterialSpec(
    "artillery_battery",
    (59, 130, 246, 255),
    shading="unlit",
    emissive_rgb=(29, 65, 123),
)
TARGET_MATERIAL = MaterialSpec(
    "artillery_target",
    (239, 68, 68, 255),
    shading="unlit",
    emissive_rgb=(119, 34, 34),
)


def write_artillery_trajectory_glb(
    path: Path,
    *,
    task_id: str,
    target_epsg: int,
    battery: tuple[float, float, float],
    target: tuple[float, float, float],
    trajectory: list[tuple[float, float, float]],
) -> dict:
    values = numpy.asarray([battery, target, *trajectory], dtype=numpy.float64)
    if values.shape != (len(trajectory) + 2, 3) or not numpy.isfinite(values).all():
        raise ValueError("Artillery trajectory requires finite projected XYZ points")
    if len(trajectory) < 2:
        raise ValueError("Artillery trajectory requires at least two points")

    frame = SceneFrame.from_projected_points(
        target_epsg,
        [tuple(point) for point in values],
        axes="z_up",
    )
    local_trajectory = [frame.to_gltf(point) for point in trajectory]
    trajectory_mesh = continuous_tube_mesh(
        local_trajectory,
        radius_m=max(1.5, min(12.0, float(numpy.ptp(values[:, :2], axis=0).max() * 0.01))),
        sections=8,
    )

    marker_radius = max(5.0, min(24.0, float(numpy.ptp(values[:, :2], axis=0).max() * 0.02)))
    battery_mesh = trimesh.creation.icosphere(subdivisions=2, radius=marker_radius)
    battery_mesh.apply_translation(frame.to_gltf(battery))
    target_mesh = trimesh.creation.icosphere(subdivisions=2, radius=marker_radius)
    target_mesh.apply_translation(frame.to_gltf(target))

    root = SceneNode(
        name="artillery_result",
        extras={"kind": "artillery_trajectory"},
        children=[
            SceneNode(
                name="artillery_result/trajectory",
                mesh=trajectory_mesh,
                material=TRAJECTORY_MATERIAL,
                extras={"kind": "artillery_trajectory"},
            ),
            SceneNode(
                name="artillery_result/battery",
                mesh=battery_mesh,
                material=BATTERY_MATERIAL,
                extras={"kind": "artillery_battery"},
            ),
            SceneNode(
                name="artillery_result/target",
                mesh=target_mesh,
                material=TARGET_MATERIAL,
                extras={"kind": "artillery_target"},
            ),
        ],
    )
    metadata = frame.metadata(task_id, "artillery")
    metadata.update(
        {
            "trajectory": {
                "point_count": len(trajectory),
                "battery_projected_xyz": list(battery),
                "target_projected_xyz": list(target),
            }
        }
    )
    export_glb(path, [root], scene_metadata=metadata, include_normals=False)
    return metadata
