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
HIGH_TRAJECTORY_MATERIAL = MaterialSpec(
    "artillery_trajectory_high",
    (6, 182, 212, 255),
    shading="unlit",
    emissive_rgb=(3, 91, 106),
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
    trajectories: list[dict],
) -> dict:
    if not trajectories:
        raise ValueError("Artillery trajectory requires at least one solution")
    all_points = [point for solution in trajectories for point in solution["points"]]
    values = numpy.asarray([battery, target, *all_points], dtype=numpy.float64)
    if values.shape != (len(all_points) + 2, 3) or not numpy.isfinite(values).all():
        raise ValueError("Artillery trajectory requires finite projected XYZ points")
    if any(len(solution["points"]) < 2 for solution in trajectories):
        raise ValueError("Artillery trajectory requires at least two points")

    frame = SceneFrame.from_projected_points(
        target_epsg,
        [tuple(point) for point in values],
        axes="z_up",
    )
    tube_radius = max(1.5, min(12.0, float(numpy.ptp(values[:, :2], axis=0).max() * 0.01)))
    trajectory_nodes = []
    for solution in trajectories:
        kind = str(solution["kind"])
        trajectory_nodes.append(SceneNode(
            name=f"artillery_result/trajectory_{kind}",
            mesh=continuous_tube_mesh(
                [frame.to_gltf(point) for point in solution["points"]],
                radius_m=tube_radius,
                sections=8,
            ),
            material=HIGH_TRAJECTORY_MATERIAL if kind == "high" else TRAJECTORY_MATERIAL,
            extras={"kind": "artillery_trajectory", "trajectory_kind": kind, "elevation_deg": float(solution["elevation_deg"])},
        ))

    marker_radius = max(5.0, min(24.0, float(numpy.ptp(values[:, :2], axis=0).max() * 0.02)))
    battery_mesh = trimesh.creation.icosphere(subdivisions=2, radius=marker_radius)
    battery_mesh.apply_translation(frame.to_gltf(battery))
    target_mesh = trimesh.creation.icosphere(subdivisions=2, radius=marker_radius)
    target_mesh.apply_translation(frame.to_gltf(target))

    root = SceneNode(
        name="artillery_result",
        extras={"kind": "artillery_trajectory"},
        children=[
            *trajectory_nodes,
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
                "count": len(trajectories),
                "solutions": [
                    {"kind": str(solution["kind"]), "elevation_deg": float(solution["elevation_deg"]), "point_count": len(solution["points"])}
                    for solution in trajectories
                ],
                "battery_projected_xyz": list(battery),
                "target_projected_xyz": list(target),
            }
        }
    )
    export_glb(path, [root], scene_metadata=metadata, include_normals=False)
    return metadata
