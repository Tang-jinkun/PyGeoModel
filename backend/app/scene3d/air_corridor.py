from pathlib import Path
import re

import numpy
from pyproj import Transformer
import trimesh

from app.schemas.air_corridor import AirCorridorPlanningRequest
from app.scene3d.exporter import MaterialSpec, export_glb
from app.scene3d.frame import ProjectedPoint, SceneFrame
from app.scene3d.primitives import (
    annular_prism_mesh,
    marker_mesh,
    ribbon_mesh,
    tube_mesh,
)


PATH = MaterialSpec("corridor_path", (36, 144, 95, 255))
RIBBON = MaterialSpec("corridor_ribbon", (45, 123, 170, 88))
RISK_LOW = MaterialSpec("risk_low", (36, 144, 95, 255))
RISK_MEDIUM = MaterialSpec("risk_medium", (233, 162, 43, 255))
RISK_HIGH = MaterialSpec("risk_high", (201, 73, 73, 255))
WARNING = MaterialSpec("threat_warning", (225, 126, 52, 72))
KILL = MaterialSpec("threat_kill", (201, 73, 73, 96))
START = MaterialSpec("start", (235, 240, 245, 255))
END = MaterialSpec("end", (43, 55, 70, 255))


def write_air_corridor_glb(
    path: Path,
    *,
    task_id: str,
    target_epsg: int,
    path_points: list[ProjectedPoint],
    sample_features: list[dict],
    prepared_threat_xy: dict[str, tuple[float, float]],
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
    frame = SceneFrame.from_projected_points(target_epsg, frame_points)

    meshes: dict[str, tuple[trimesh.Trimesh, MaterialSpec]] = {}
    node_metadata: dict[str, dict] = {}
    marker_radius = max(30.0, payload.planning.corridor_width_m * 0.08)
    gltf_path = numpy.asarray(
        [frame.to_gltf(point) for point in path_points],
        dtype=numpy.float64,
    )
    if route_found:
        if len(gltf_path) < 2:
            raise ValueError("A found corridor route requires at least two path points")
        route_radius = max(20.0, payload.planning.corridor_width_m * 0.04)
        meshes["corridor_path"] = (
            tube_mesh(gltf_path, radius_m=route_radius),
            PATH,
        )
        node_metadata["corridor_path"] = {
            "kind": "corridor_path",
            "point_count": len(gltf_path),
            "radius_m": route_radius,
        }
        meshes["corridor_ribbon"] = (
            ribbon_mesh(gltf_path, width_m=payload.planning.corridor_width_m),
            RIBBON,
        )
        node_metadata["corridor_ribbon"] = {
            "kind": "corridor_ribbon",
            "width_m": payload.planning.corridor_width_m,
        }
        _add_risk_meshes(
            meshes,
            node_metadata,
            frame,
            sample_features,
            marker_radius,
        )
    start_marker = frame.to_gltf(start_point)
    end_marker = frame.to_gltf(end_point)

    meshes["start"] = (marker_mesh(start_marker, marker_radius * 1.2), START)
    meshes["end"] = (marker_mesh(end_marker, marker_radius * 1.2), END)
    node_metadata["start"] = {
        "kind": "terminal",
        "role": "start",
        "altitude_amsl_m": start_altitude,
    }
    node_metadata["end"] = {
        "kind": "terminal",
        "role": "end",
        "altitude_amsl_m": end_altitude,
    }
    _add_threat_meshes(
        meshes,
        node_metadata,
        frame,
        prepared_threat_xy,
        payload,
    )

    scene_metadata = frame.metadata(task_id, "air_corridor")
    scene_metadata.update(
        {
            "route_found": route_found,
            "risk_sample_count": len(sample_features),
            "threat_count": len(payload.threats),
            "corridor_width_m": payload.planning.corridor_width_m,
        }
    )
    export_glb(
        path,
        meshes,
        scene_metadata=scene_metadata,
        node_metadata=node_metadata,
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
    meshes: dict[str, tuple[trimesh.Trimesh, MaterialSpec]],
    node_metadata: dict[str, dict],
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
        meshes[name] = (
            trimesh.util.concatenate(
                [
                    marker_mesh(point, marker_radius * 0.7)
                    for point, _risk in grouped_samples
                ]
            ),
            materials[name],
        )
        risks = [risk for _point, risk in grouped_samples]
        node_metadata[name] = {
            "kind": "risk_samples",
            "class": name.removeprefix("risk_"),
            "sample_count": len(grouped_samples),
            "risk_min": min(risks),
            "risk_max": max(risks),
        }


def _add_threat_meshes(
    meshes: dict[str, tuple[trimesh.Trimesh, MaterialSpec]],
    node_metadata: dict[str, dict],
    frame: SceneFrame,
    prepared_threat_xy: dict[str, tuple[float, float]],
    payload: AirCorridorPlanningRequest,
) -> None:
    used_names: set[str] = set()
    for threat in payload.threats:
        safe_id = re.sub(r"[^A-Za-z0-9_-]+", "_", threat.id).strip("_")
        if not safe_id or safe_id in used_names:
            raise ValueError(f"Threat id is not unique after normalization: {threat.id}")
        used_names.add(safe_id)
        x, y = prepared_threat_xy[threat.id]
        center = frame.to_gltf((x, y, threat.min_altitude_m))
        bottom_y = float(center[1])
        top_y = float(
            frame.to_gltf((x, y, threat.max_altitude_m))[1]
        )
        warning_radius = threat.warning_zone_radius_m or threat.max_range_m
        kill_radius = threat.kill_zone_radius_m or threat.max_range_m * 0.7
        for suffix, outer_radius, material in (
            ("warning", warning_radius, WARNING),
            ("kill", kill_radius, KILL),
        ):
            name = f"threat_{safe_id}_{suffix}"
            meshes[name] = (
                annular_prism_mesh(
                    center,
                    threat.min_range_m,
                    outer_radius,
                    bottom_y,
                    top_y,
                ),
                material,
            )
            node_metadata[name] = {
                "kind": "threat_volume",
                "zone": suffix,
                "threat_id": threat.id,
                "inner_radius_m": threat.min_range_m,
                "outer_radius_m": outer_radius,
                "min_altitude_m": threat.min_altitude_m,
                "max_altitude_m": threat.max_altitude_m,
            }
