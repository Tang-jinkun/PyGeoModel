from typing import Any

from app.demo_scenarios.models import ScenarioEnvelope
from app.demo_scenarios.terrain import TerrainGrid


def _line_feature(
    points: list[tuple[float, float]],
    road_class: str,
) -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": {"road_class": road_class, "synthetic": True},
        "geometry": {
            "type": "LineString",
            "coordinates": [list(point) for point in points],
        },
    }


def build_mobility(
    terrain: TerrainGrid,
    dem_id: str,
    candidate_index: int,
) -> ScenarioEnvelope:
    direct_offsets = [(-2, -3), (0, 0), (2, 3)]
    main_offsets = [(-2, -3), (-2, 0), (0, 3), (2, 3)]
    branch_offsets = [(-1, -2), (0, 0), (1, 2)]
    required_offsets = sorted(set(direct_offsets + main_offsets + branch_offsets))
    anchor = terrain.select(
        "valley",
        candidate_index,
        margin=5,
        required_offsets=required_offsets,
    )
    direct = terrain.route(anchor, direct_offsets)
    main = terrain.route(anchor, main_offsets)
    branch = terrain.route(anchor, branch_offsets)
    trail = terrain.route(anchor, direct_offsets)
    roads = {
        "type": "FeatureCollection",
        "synthetic": True,
        "features": [
            _line_feature(main, "main"),
            _line_feature(branch, "branch"),
            _line_feature(trail, "trail"),
        ],
    }
    request = {
        "dem_id": dem_id,
        "start": {"lon": direct[0][0], "lat": direct[0][1]},
        "end": {"lon": direct[-1][0], "lat": direct[-1][1]},
        "vehicles": {
            "wheeled": {
                "enabled": True,
                "base_speed_kph": 50,
                "max_slope_deg": 60,
                "slope_penalty": 2.4,
                "road_speed_multiplier": 1.7,
                "offroad_speed_multiplier": 0.5,
            },
            "tracked": {
                "enabled": True,
                "base_speed_kph": 32,
                "max_slope_deg": 60,
                "slope_penalty": 1.2,
                "road_speed_multiplier": 1.2,
                "offroad_speed_multiplier": 0.9,
            },
        },
        "road_network": {
            "geojson": roads,
            "road_buffer_m": 150,
            "road_classes": {"main": 1.8, "branch": 1.35, "trail": 1.05},
        },
        "analysis": {
            "allow_diagonal": True,
            "max_search_radius_m": 50000,
            "output_simplify_tolerance_m": 30,
        },
    }
    return ScenarioEnvelope(
        "mobility-accessibility",
        "mobility",
        1,
        dem_id,
        candidate_index,
        request,
        ("road-network.geojson",),
    )


def build_air_corridor(
    terrain: TerrainGrid,
    dem_id: str,
    candidate_index: int,
) -> ScenarioEnvelope:
    offsets = [(0, -22), (0, -7), (0, 0), (0, 7), (0, 22)]
    anchor = terrain.select(
        "rough",
        candidate_index,
        margin=24,
        required_offsets=offsets,
    )
    line = terrain.route(anchor, offsets)
    threats = []
    for index, (point, (row_offset, col_offset)) in enumerate(
        zip(line[1:4], offsets[1:4]),
        start=1,
    ):
        ground_elevation_m = float(
            terrain.elevation[
                anchor[0] + row_offset,
                anchor[1] + col_offset,
            ]
        )
        threats.append(
            {
                "id": f"demo-threat-{index}",
                "name": f"Synthetic threat {index}",
                "lon": point[0],
                "lat": point[1],
                "min_range_m": 0,
                "max_range_m": 5000 + index * 1000,
                "min_altitude_m": 0,
                "max_altitude_m": ground_elevation_m + 900 + index * 150,
                "threat_level": 4 + index * 2,
                "kill_zone_radius_m": 2000 + index * 300,
                "warning_zone_radius_m": 3500 + index * 500,
            }
        )
    request = {
        "dem_id": dem_id,
        "start": {
            "lon": line[0][0],
            "lat": line[0][1],
            "altitude_m": 600,
            "altitude_mode": "agl",
        },
        "end": {
            "lon": line[-1][0],
            "lat": line[-1][1],
            "altitude_m": 600,
            "altitude_mode": "agl",
        },
        "aircraft": {
            "cruise_speed_kph": 180,
            "min_agl_m": 100,
            "max_agl_m": 3000,
            "max_climb_rate_mps": 8,
            "max_descent_rate_mps": 10,
        },
        "altitude_layers_m": [300, 600, 900, 1200, 1800, 2400],
        "threats": threats,
        "planning": {
            "corridor_width_m": 500,
            "horizontal_resolution_m": 250,
            "allow_altitude_change": True,
            "threat_weight": 20,
            "distance_weight": 0.25,
            "altitude_change_weight": 0.01,
            "terrain_clearance_weight": 0.4,
            "output_simplify_tolerance_m": 30,
        },
    }
    return ScenarioEnvelope(
        "air-corridor",
        "air_corridor",
        1,
        dem_id,
        candidate_index,
        request,
        ("air-defense-threats.geojson",),
    )


def spatial_artifacts(envelope: ScenarioEnvelope) -> dict[str, dict[str, Any]]:
    if envelope.model_id == "mobility":
        return {
            "road-network.geojson": envelope.request["road_network"]["geojson"]
        }
    if envelope.model_id == "air_corridor":
        features = [
            {
                "type": "Feature",
                "properties": {**item, "synthetic": True},
                "geometry": {
                    "type": "Point",
                    "coordinates": [item["lon"], item["lat"]],
                },
            }
            for item in envelope.request["threats"]
        ]
        return {
            "air-defense-threats.geojson": {
                "type": "FeatureCollection",
                "synthetic": True,
                "features": features,
            }
        }
    return {}
