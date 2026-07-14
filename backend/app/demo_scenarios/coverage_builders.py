from math import atan2, cos, degrees, radians, sin
from typing import Callable

from app.demo_scenarios.models import ScenarioEnvelope
from app.demo_scenarios.terrain import TerrainGrid


def _heading(left: tuple[float, float], right: tuple[float, float]) -> float:
    lon1, lat1, lon2, lat2 = map(radians, (*left, *right))
    value = atan2(
        sin(lon2 - lon1) * cos(lat2),
        cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(lon2 - lon1),
    )
    return (degrees(value) + 360) % 360


def _route_headings(route: list[tuple[float, float]]) -> list[float]:
    headings: list[float] = []
    for index, point in enumerate(route):
        if index < len(route) - 1:
            headings.append(_heading(point, route[index + 1]))
        else:
            headings.append(_heading(route[index - 1], point))
    return headings


def build_uav(
    terrain: TerrainGrid,
    dem_id: str,
    candidate_index: int,
) -> ScenarioEnvelope:
    offsets = [(-8, -12), (-5, -7), (-2, -2), (2, 3), (5, 8), (8, 12)]
    route = terrain.route(
        terrain.select(
            "rough",
            candidate_index,
            margin=14,
            required_offsets=offsets,
        ),
        offsets,
    )
    headings = _route_headings(route)
    waypoints = [
        {
            "lon": point[0],
            "lat": point[1],
            "altitude_m": 350 + index * 60,
            "altitude_mode": "agl",
            "heading_deg": headings[index],
            "pitch_deg": 2 if index % 2 else 0,
            "roll_deg": 0,
        }
        for index, point in enumerate(route)
    ]
    request = {
        "dem_id": dem_id,
        "uav": waypoints[0],
        "route": {"waypoints": waypoints, "sample_interval_m": 1000},
        "sensor": {
            "sensor_type": "thermal",
            "h_fov_deg": 70,
            "v_fov_deg": 45,
            "max_range_m": 6000,
            "min_range_m": 100,
            "ground_resolution_m": 5,
        },
        "analysis": {
            "target_height_m": 1.7,
            "use_terrain_occlusion": True,
            "sample_resolution_m": 120,
            "output_simplify_tolerance_m": 30,
        },
    }
    return ScenarioEnvelope(
        "uav-recon",
        "uav",
        1,
        dem_id,
        candidate_index,
        request,
    )


def build_watchpost(
    terrain: TerrainGrid,
    dem_id: str,
    candidate_index: int,
) -> ScenarioEnvelope:
    lon, lat = terrain.lonlat(*terrain.select("ridge", candidate_index))
    request = {
        "dem_id": dem_id,
        "observer": {"lon": lon, "lat": lat, "height_m": 8},
        "target": {"height_m": 1.7},
        "coverage": {
            "max_range_m": 12000,
            "scan_mode": "sector",
            "azimuth_deg": 135,
            "view_angle_deg": 120,
        },
        "analysis": {
            "use_curvature": True,
            "curvature_coeff": 0.75,
            "output_simplify_tolerance_m": 30,
        },
    }
    return ScenarioEnvelope(
        "watchpost-detection",
        "watchpost",
        1,
        dem_id,
        candidate_index,
        request,
    )


def build_artillery(
    terrain: TerrainGrid,
    dem_id: str,
    candidate_index: int,
) -> ScenarioEnvelope:
    lon, lat = terrain.lonlat(*terrain.select("flat", candidate_index))
    request = {
        "dem_id": dem_id,
        "battery": {
            "lon": lon,
            "lat": lat,
            "height_m": 0,
            "altitude_mode": "agl",
        },
        "target": {"target_height_m": 0},
        "weapon": {
            "min_range_m": 2000,
            "max_range_m": 12000,
            "azimuth_deg": 90,
            "traverse_deg": 120,
            "muzzle_velocity_mps": 420,
            "elevation_deg": 35,
        },
        "munition": {
            "munition_type": "generic",
            "lethal_radius_m": 50,
            "effective_radius_m": 120,
        },
        "analysis": {
            "use_dem_elevation": True,
            "use_terrain_masking": True,
            "sample_resolution_m": 250,
            "trajectory_samples": 80,
            "clearance_margin_m": 0,
            "output_simplify_tolerance_m": 30,
        },
    }
    return ScenarioEnvelope(
        "artillery-coverage",
        "artillery",
        1,
        dem_id,
        candidate_index,
        request,
    )


def build_recon_vehicle(
    terrain: TerrainGrid,
    dem_id: str,
    candidate_index: int,
) -> ScenarioEnvelope:
    offsets = [(-4, -6), (-2, -3), (0, 0), (2, 3), (4, 6)]
    route = terrain.route(
        terrain.select(
            "valley",
            candidate_index,
            margin=8,
            required_offsets=offsets,
        ),
        offsets,
    )
    headings = _route_headings(route)
    waypoints = [
        {
            "lon": point[0],
            "lat": point[1],
            "heading_deg": headings[index],
            "mast_height_m": 5,
        }
        for index, point in enumerate(route)
    ]
    request = {
        "dem_id": dem_id,
        "vehicle": waypoints[0],
        "route": {"waypoints": waypoints, "sample_interval_m": 750},
        "sensor": {
            "sensor_type": "optical",
            "max_range_m": 5000,
            "min_range_m": 100,
            "scan_mode": "sector",
            "view_angle_deg": 140,
        },
        "target": {"height_m": 1.7},
        "analysis": {
            "use_terrain_occlusion": True,
            "use_curvature": True,
            "curvature_coeff": 0.75,
            "output_simplify_tolerance_m": 30,
        },
    }
    return ScenarioEnvelope(
        "recon-vehicle",
        "recon_vehicle",
        1,
        dem_id,
        candidate_index,
        request,
    )


Builder = Callable[[TerrainGrid, str, int], ScenarioEnvelope]
BUILDERS: dict[str, Builder] = {
    "uav": build_uav,
    "watchpost": build_watchpost,
    "artillery": build_artillery,
    "recon_vehicle": build_recon_vehicle,
}
