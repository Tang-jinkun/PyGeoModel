from pathlib import Path

import numpy
from pyproj import Transformer
import trimesh

from app.schemas.air_corridor import AirCorridorPlanningRequest
from app.scene3d.exporter import MaterialSpec, SceneNode, export_glb
from app.scene3d.frame import ProjectedPoint, SceneFrame
from app.scene3d.primitives import (
    marker_mesh,
    ribbon_mesh,
    tube_mesh,
)
from app.scene3d.tactical_glyphs import ALLOWED_LABEL_CHARACTERS
from app.scene3d.units import (
    InfluenceZoneSpec,
    UnitSpec,
    build_unit_nodes,
)


PATH = MaterialSpec(
    "corridor_path",
    (36, 144, 95, 255),
    shading="unlit",
    emissive_rgb=(18, 72, 48),
)
RIBBON = MaterialSpec(
    "corridor_ribbon",
    (45, 123, 170, 88),
    shading="unlit",
    emissive_rgb=(23, 62, 85),
)
RISK_LOW = MaterialSpec(
    "risk_low",
    (36, 144, 95, 255),
    shading="unlit",
    emissive_rgb=(18, 72, 48),
)
RISK_MEDIUM = MaterialSpec(
    "risk_medium",
    (233, 162, 43, 255),
    shading="unlit",
    emissive_rgb=(117, 81, 22),
)
RISK_HIGH = MaterialSpec(
    "risk_high",
    (201, 73, 73, 255),
    shading="unlit",
    emissive_rgb=(101, 37, 37),
)
START = MaterialSpec(
    "start",
    (235, 240, 245, 255),
    shading="unlit",
    emissive_rgb=(118, 120, 123),
)
END = MaterialSpec(
    "end",
    (43, 55, 70, 255),
    shading="unlit",
    emissive_rgb=(22, 28, 35),
)


def write_air_corridor_glb(
    path: Path,
    *,
    task_id: str,
    target_epsg: int,
    path_points: list[ProjectedPoint],
    sample_features: list[dict],
    prepared_threat_xy: dict[str, tuple[float, float]],
    threat_ground_elevations_m: dict[str, float | None],
    start_ground_elevation_m: float,
    end_ground_elevation_m: float,
    payload: AirCorridorPlanningRequest,
    route_found: bool,
) -> dict:
    to_target = Transformer.from_crs(
        "EPSG:4326",
        f"EPSG:{target_epsg}",
        always_xy=True,
    )
    start_xy = to_target.transform(payload.start.lon, payload.start.lat)
    end_xy = to_target.transform(payload.end.lon, payload.end.lat)
    start_altitude = _terminal_altitude(
        payload.start.altitude_m,
        payload.start.altitude_mode,
        start_ground_elevation_m,
    )
    end_altitude = _terminal_altitude(
        payload.end.altitude_m,
        payload.end.altitude_mode,
        end_ground_elevation_m,
    )
    start_point = (float(start_xy[0]), float(start_xy[1]), start_altitude)
    end_point = (float(end_xy[0]), float(end_xy[1]), end_altitude)

    frame_points = [start_point, end_point, *path_points]
    for threat in payload.threats:
        if threat.id not in prepared_threat_xy:
            raise ValueError(f"Missing projected threat coordinate: {threat.id}")
        threat_x, threat_y = prepared_threat_xy[threat.id]
        frame_points.extend(
            [
                (threat_x, threat_y, threat.min_altitude_m),
                (threat_x, threat_y, threat.max_altitude_m),
            ]
        )
        ground_elevation = threat_ground_elevations_m.get(threat.id)
        if ground_elevation is not None and numpy.isfinite(ground_elevation):
            frame_points.append((threat_x, threat_y, float(ground_elevation)))
    frame = SceneFrame.from_projected_points(target_epsg, frame_points)

    nodes: list[SceneNode] = []
    marker_radius = max(30.0, payload.planning.corridor_width_m * 0.08)
    gltf_path = numpy.asarray(
        [frame.to_gltf(point) for point in path_points],
        dtype=numpy.float64,
    )
    if route_found:
        if len(gltf_path) < 2:
            raise ValueError("A found corridor route requires at least two path points")
        route_radius = max(20.0, payload.planning.corridor_width_m * 0.04)
        nodes.append(
            SceneNode(
                name="corridor_path",
                mesh=tube_mesh(gltf_path, radius_m=route_radius),
                material=PATH,
                extras={
                    "kind": "corridor_path",
                    "point_count": len(gltf_path),
                    "radius_m": route_radius,
                },
            )
        )
        nodes.append(
            SceneNode(
                name="corridor_ribbon",
                mesh=ribbon_mesh(
                    gltf_path,
                    width_m=payload.planning.corridor_width_m,
                ),
                material=RIBBON,
                extras={
                    "kind": "corridor_ribbon",
                    "width_m": payload.planning.corridor_width_m,
                },
            )
        )
        _add_risk_meshes(
            nodes,
            frame,
            sample_features,
            marker_radius,
        )
    start_marker = frame.to_gltf(start_point)
    end_marker = frame.to_gltf(end_point)

    nodes.extend(
        [
            SceneNode(
                name="start",
                mesh=marker_mesh(start_marker, marker_radius * 1.2),
                material=START,
                extras={
                    "kind": "terminal",
                    "role": "start",
                    "altitude_amsl_m": start_altitude,
                },
            ),
            SceneNode(
                name="end",
                mesh=marker_mesh(end_marker, marker_radius * 1.2),
                material=END,
                extras={
                    "kind": "terminal",
                    "role": "end",
                    "altitude_amsl_m": end_altitude,
                },
            ),
        ]
    )
    unit_specs = [
        _threat_unit_spec(
            threat,
            index,
            prepared_threat_xy[threat.id],
            threat_ground_elevations_m.get(threat.id),
            payload.planning.corridor_width_m,
        )
        for index, threat in enumerate(payload.threats)
    ]
    unit_nodes, omissions = build_unit_nodes(unit_specs, frame)
    nodes.extend(unit_nodes)
    serialized_omissions = [
        {"unit_id": omission.unit_id, "reason": omission.reason}
        for omission in omissions
    ]

    scene_metadata = frame.metadata(task_id, "air_corridor")
    scene_metadata.update(
        {
            "route_found": route_found,
            "risk_sample_count": len(sample_features),
            "threat_count": len(payload.threats),
            "corridor_width_m": payload.planning.corridor_width_m,
            "tactical_unit_count": len(unit_nodes),
            "omitted_units": serialized_omissions,
        }
    )
    export_glb(
        path,
        nodes,
        scene_metadata=scene_metadata,
    )
    return scene_metadata


def _terminal_altitude(
    altitude_m: float,
    altitude_mode: str,
    ground_elevation_m: float,
) -> float:
    return float(
        altitude_m
        if altitude_mode == "amsl"
        else ground_elevation_m + altitude_m
    )


def _add_risk_meshes(
    nodes: list[SceneNode],
    frame: SceneFrame,
    sample_features: list[dict],
    marker_radius: float,
) -> None:
    samples = []
    for feature in sample_features:
        geometry = feature.get("geometry")
        properties = feature.get("properties", {})
        risk = float(properties.get("risk", 0))
        altitude = float(properties["altitude_amsl_m"])
        if geometry is None or not numpy.isfinite([geometry.x, geometry.y, risk, altitude]).all():
            raise ValueError("Risk sample contains invalid geometry or values")
        samples.append((frame.to_gltf((geometry.x, geometry.y, altitude)), risk))
    max_risk = max((risk for _point, risk in samples), default=0.0)
    groups: dict[str, list[tuple[numpy.ndarray, float]]] = {
        "risk_low": [],
        "risk_medium": [],
        "risk_high": [],
    }
    for point, risk in samples:
        normalized = risk / max_risk if max_risk > 0 else 0.0
        name = (
            "risk_low"
            if normalized <= 0.33
            else "risk_medium"
            if normalized <= 0.66
            else "risk_high"
        )
        groups[name].append((point, risk))
    materials = {
        "risk_low": RISK_LOW,
        "risk_medium": RISK_MEDIUM,
        "risk_high": RISK_HIGH,
    }
    for name, grouped_samples in groups.items():
        if not grouped_samples:
            continue
        risks = [risk for _point, risk in grouped_samples]
        nodes.append(
            SceneNode(
                name=name,
                mesh=trimesh.util.concatenate(
                    [
                        marker_mesh(point, marker_radius * 0.7)
                        for point, _risk in grouped_samples
                    ]
                ),
                material=materials[name],
                extras={
                    "kind": "risk_samples",
                    "class": name.removeprefix("risk_"),
                    "sample_count": len(grouped_samples),
                    "risk_min": min(risks),
                    "risk_max": max(risks),
                },
            )
        )


def _threat_unit_spec(
    threat,
    index: int,
    position: tuple[float, float],
    ground_elevation_m: float | None,
    corridor_width_m: float,
) -> UnitSpec:
    short_label = None
    if threat.name is not None and len(threat.name) <= 8:
        short_label = "".join(
            character
            for character in threat.name.upper()
            if character in ALLOWED_LABEL_CHARACTERS
        ) or None
    return UnitSpec(
        unit_id=threat.id,
        unit_type="air_defense",
        position=position,
        altitude_amsl_m=(
            ground_elevation_m
            if ground_elevation_m is not None
            else float("nan")
        ),
        heading_deg=0,
        status="active",
        short_label=short_label or f"AD-{index + 1:02d}",
        display_scale_m=min(1200.0, max(400.0, corridor_width_m)),
        warning_zone=InfluenceZoneSpec(
            threat.min_range_m,
            threat.warning_zone_radius_m or threat.max_range_m,
            threat.min_altitude_m,
            threat.max_altitude_m,
        ),
        kill_zone=InfluenceZoneSpec(
            threat.min_range_m,
            threat.kill_zone_radius_m or threat.max_range_m * 0.7,
            threat.min_altitude_m,
            threat.max_altitude_m,
        ),
        source=threat.model_dump(),
    )
