from pathlib import Path

from app.demo_scenarios.route_builders import (
    build_air_corridor,
    build_mobility,
    spatial_artifacts,
)
from app.demo_scenarios.terrain import TerrainGrid
from app.schemas.air_corridor import AirCorridorPlanningRequest
from app.schemas.mobility import MobilityAccessibilityRequest
from tests.demo_scenario_helpers import write_dem


def test_mobility_contains_three_synthetic_road_classes(tmp_path: Path) -> None:
    path = tmp_path / "dem.tif"
    write_dem(path)
    scenario = build_mobility(TerrainGrid.load(path, 80), "dem_a", 0)

    MobilityAccessibilityRequest.model_validate(scenario.request)
    features = scenario.request["road_network"]["geojson"]["features"]

    assert {item["properties"]["road_class"] for item in features} == {
        "main",
        "branch",
        "trail",
    }
    assert all(item["properties"]["synthetic"] is True for item in features)
    assert set(spatial_artifacts(scenario)) == {"road-network.geojson"}
    assert scenario.request["vehicles"]["wheeled"]["max_slope_deg"] == 60
    assert scenario.request["vehicles"]["tracked"]["max_slope_deg"] == 60
    assert abs(scenario.request["start"]["lon"] - scenario.request["end"]["lon"]) < 0.04


def test_air_corridor_contains_three_threats_and_altitude_layers(
    tmp_path: Path,
) -> None:
    path = tmp_path / "dem.tif"
    write_dem(path)
    scenario = build_air_corridor(TerrainGrid.load(path, 80), "dem_a", 0)

    AirCorridorPlanningRequest.model_validate(scenario.request)

    assert len(scenario.request["threats"]) == 3
    assert all(threat["min_range_m"] == 0 for threat in scenario.request["threats"])
    assert scenario.request["planning"]["threat_weight"] == 20
    assert scenario.request["planning"]["altitude_change_weight"] == 0.01
    assert scenario.request["altitude_layers_m"] == sorted(
        scenario.request["altitude_layers_m"]
    )
    artifacts = spatial_artifacts(scenario)
    assert set(artifacts) == {"air-defense-threats.geojson"}
    assert all(
        feature["properties"]["synthetic"] is True
        for feature in artifacts["air-defense-threats.geojson"]["features"]
    )
