from pathlib import Path

import pytest

from app.demo_scenarios.coverage_builders import BUILDERS
from app.demo_scenarios.terrain import TerrainGrid
from app.schemas.artillery import ArtilleryCoverageRequest
from app.schemas.recon_vehicle import ReconVehicleCoverageRequest
from app.schemas.uav import UavReconRequest
from app.schemas.watchpost import WatchpostDetectionRequest
from tests.demo_scenario_helpers import write_dem


@pytest.mark.parametrize(
    ("model_id", "schema"),
    [
        ("uav", UavReconRequest),
        ("watchpost", WatchpostDetectionRequest),
        ("artillery", ArtilleryCoverageRequest),
        ("recon_vehicle", ReconVehicleCoverageRequest),
    ],
)
def test_coverage_builder_creates_valid_native_request(
    tmp_path: Path,
    model_id: str,
    schema: type,
) -> None:
    dem_path = tmp_path / "dem.tif"
    write_dem(dem_path)
    terrain = TerrainGrid.load(dem_path, max_dimension=80)

    envelope = BUILDERS[model_id](terrain, "dem_a", 0)

    schema.model_validate(envelope.request)
    assert envelope.model_id == model_id
    assert envelope.to_dict()["scenario"]["synthetic"] is True
    assert "synthetic" not in envelope.request


def test_uav_and_recon_build_routes_with_multiple_waypoints(tmp_path: Path) -> None:
    dem_path = tmp_path / "dem.tif"
    write_dem(dem_path)
    terrain = TerrainGrid.load(dem_path, max_dimension=80)

    uav = BUILDERS["uav"](terrain, "dem_a", 0)
    recon = BUILDERS["recon_vehicle"](terrain, "dem_a", 0)

    assert len(uav.request["route"]["waypoints"]) >= 6
    assert len(recon.request["route"]["waypoints"]) >= 5
    assert len({point["heading_deg"] for point in uav.request["route"]["waypoints"]}) > 1
