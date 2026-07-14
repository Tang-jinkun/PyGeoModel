from pathlib import Path

from shapely.geometry import Point
import trimesh

from app.scene3d.air_corridor import write_air_corridor_glb
from app.schemas.air_corridor import AirCorridorPlanningRequest


def sample_features(risks: list[float]) -> list[dict]:
    coordinates = [
        (500_000.0, 3_500_000.0, 6200.0),
        (501_000.0, 3_500_200.0, 6800.0),
        (502_000.0, 3_500_000.0, 6400.0),
    ]
    return [
        {
            "geometry": Point(x, y),
            "properties": {
                "index": index,
                "altitude_amsl_m": altitude,
                "risk": risk,
            },
        }
        for index, ((x, y, altitude), risk) in enumerate(zip(coordinates, risks))
    ]


def payload_with_two_threats() -> AirCorridorPlanningRequest:
    return AirCorridorPlanningRequest(
        dem_id="dem_a",
        start={"lon": 79.8, "lat": 31.48, "altitude_m": 6200, "altitude_mode": "amsl"},
        end={"lon": 79.82, "lat": 31.48, "altitude_m": 6400, "altitude_mode": "amsl"},
        threats=[
            {
                "id": "a",
                "lon": 79.81,
                "lat": 31.48,
                "min_range_m": 0,
                "max_range_m": 3000,
                "min_altitude_m": 5500,
                "max_altitude_m": 7200,
                "kill_zone_radius_m": 1200,
                "warning_zone_radius_m": 2400,
            },
            {
                "id": "b",
                "lon": 79.815,
                "lat": 31.481,
                "min_range_m": 300,
                "max_range_m": 3500,
                "min_altitude_m": 5700,
                "max_altitude_m": 7400,
                "kill_zone_radius_m": 1400,
                "warning_zone_radius_m": 2800,
            },
        ],
        planning={"corridor_width_m": 500},
    )


def payload_with_one_threat() -> AirCorridorPlanningRequest:
    return AirCorridorPlanningRequest(
        dem_id="dem_a",
        start={"lon": 79.8, "lat": 31.48, "altitude_m": 300, "altitude_mode": "agl"},
        end={"lon": 79.82, "lat": 31.48, "altitude_m": 400, "altitude_mode": "agl"},
        threats=[
            {
                "id": "a",
                "lon": 79.81,
                "lat": 31.48,
                "max_range_m": 3000,
                "min_altitude_m": 5500,
                "max_altitude_m": 7200,
                "kill_zone_radius_m": 1200,
                "warning_zone_radius_m": 2400,
            }
        ],
        planning={"corridor_width_m": 500},
    )


def test_air_corridor_scene_writes_semantic_nodes(tmp_path: Path) -> None:
    output = tmp_path / "air_corridor_result.glb"
    metadata = write_air_corridor_glb(
        output,
        task_id="air_corridor_task_a",
        target_epsg=32644,
        path_points=[
            (500_000, 3_500_000, 6200),
            (501_000, 3_500_200, 6800),
            (502_000, 3_500_000, 6400),
        ],
        sample_features=sample_features([0.0, 5.0, 10.0]),
        prepared_threat_xy={
            "a": (501_000, 3_500_000),
            "b": (501_500, 3_500_300),
        },
        start_ground_elevation_m=5900,
        end_ground_elevation_m=6000,
        payload=payload_with_two_threats(),
        route_found=True,
    )
    scene = trimesh.load(output, force="scene")
    names = set(scene.graph.nodes_geometry)

    assert {
        "corridor_path",
        "corridor_ribbon",
        "risk_low",
        "risk_medium",
        "risk_high",
        "start",
        "end",
    } <= names
    assert {
        "threat_a_warning",
        "threat_a_kill",
        "threat_b_warning",
        "threat_b_kill",
    } <= names
    assert metadata["route_found"] is True
    assert metadata["risk_sample_count"] == 3


def test_route_not_found_scene_contains_context_only(tmp_path: Path) -> None:
    output = tmp_path / "air_corridor_result.glb"
    write_air_corridor_glb(
        output,
        task_id="air_corridor_task_a",
        target_epsg=32644,
        path_points=[],
        sample_features=[],
        prepared_threat_xy={"a": (501_000, 3_500_000)},
        start_ground_elevation_m=5900,
        end_ground_elevation_m=6000,
        payload=payload_with_one_threat(),
        route_found=False,
    )
    names = set(trimesh.load(output, force="scene").graph.nodes_geometry)

    assert {"start", "end", "threat_a_warning", "threat_a_kill"} <= names
    assert "corridor_path" not in names
