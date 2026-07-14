from pathlib import Path

from app.demo_scenarios.terrain import TerrainGrid
from tests.demo_scenario_helpers import write_dem


def test_candidate_selection_is_deterministic_and_spaced(tmp_path: Path) -> None:
    path = tmp_path / "dem.tif"
    write_dem(path)
    first = TerrainGrid.load(path, max_dimension=80)
    second = TerrainGrid.load(path, max_dimension=80)

    assert first.select("ridge", 0) == second.select("ridge", 0)
    assert first.select("valley", 1) == second.select("valley", 1)
    assert first.select("valley", 0) != first.select("valley", 1)


def test_route_returns_valid_lon_lat_points(tmp_path: Path) -> None:
    path = tmp_path / "dem.tif"
    write_dem(path)
    terrain = TerrainGrid.load(path, max_dimension=80)
    anchor = terrain.select("valley", 0)

    route = terrain.route(anchor, [(-3, -4), (0, 0), (3, 4)])

    assert len(route) == 3
    assert all(79.0 <= lon <= 79.4 and 31.6 <= lat <= 32.0 for lon, lat in route)


def test_candidate_selection_can_require_all_route_offsets_to_be_valid(
    tmp_path: Path,
) -> None:
    path = tmp_path / "dem.tif"
    write_dem(path)
    terrain = TerrainGrid.load(path, max_dimension=80)
    offsets = [(-8, -12), (-5, -7), (0, 0), (5, 8), (8, 12)]

    anchor = terrain.select(
        "rough",
        0,
        margin=14,
        required_offsets=offsets,
    )

    assert len(terrain.route(anchor, offsets)) == len(offsets)
