import numpy
import pytest
from rasterio.transform import from_origin

from app.schemas.artillery import ArtilleryCoverageRequest
from app.workers.artillery_task import _trajectory_clearance


def test_trajectory_clearance_reports_terrain_masking() -> None:
    dem = numpy.zeros((20, 20), dtype=numpy.float32)
    dem[10, 10] = 300
    transform = from_origin(0, 2000, 100, 100)
    payload = ArtilleryCoverageRequest(
        dem_id="dem_a",
        weapon={"muzzle_velocity_mps": 140, "elevation_deg": 10, "min_range_m": 100, "max_range_m": 2000},
        analysis={"trajectory_samples": 20},
    )

    result = _trajectory_clearance(dem, transform, None, 50, 950, 0, 1950, 950, 0, payload)

    assert result["is_clear"] is False
    assert result["min_clearance_m"] < 0
    assert result["masking_distance_m"] is not None


def test_trajectory_clearance_reports_clear_path() -> None:
    dem = numpy.zeros((20, 20), dtype=numpy.float32)
    transform = from_origin(0, 2000, 100, 100)
    payload = ArtilleryCoverageRequest(
        dem_id="dem_a",
        weapon={"muzzle_velocity_mps": 300, "elevation_deg": 35, "min_range_m": 100, "max_range_m": 2000},
        analysis={"trajectory_samples": 20},
    )

    result = _trajectory_clearance(dem, transform, None, 50, 950, 0, 1950, 950, 0, payload)

    assert result["is_clear"] is True
    assert result["min_clearance_m"] >= 0
    assert result["masking_distance_m"] is None


def test_trajectory_clearance_returns_sampled_path_for_visualization() -> None:
    dem = numpy.zeros((20, 20), dtype=numpy.float32)
    transform = from_origin(0, 2000, 100, 100)
    payload = ArtilleryCoverageRequest(
        dem_id="dem_a",
        weapon={"muzzle_velocity_mps": 300, "elevation_deg": 35, "min_range_m": 100, "max_range_m": 2000},
        analysis={"trajectory_samples": 8},
    )

    result = _trajectory_clearance(dem, transform, None, 50, 950, 0, 1950, 950, 0, payload)

    assert len(result["trajectory"]) == 9
    assert result["trajectory"][0] == {"x": 50.0, "y": 950.0, "z": 0.0, "terrain_m": 0.0, "clearance_m": 0.0}
    assert result["trajectory"][-1]["x"] == 1950.0
    assert result["trajectory"][-1]["z"] == 0.0
    assert result["time_of_flight_s"] > 0


def test_artillery_target_coordinates_are_pairwise_and_optional() -> None:
    payload = ArtilleryCoverageRequest(
        dem_id="dem_a",
        target={"lon": 79.9, "lat": 31.5, "target_height_m": 20},
    )

    assert payload.target.lon == 79.9
    assert payload.target.lat == 31.5
    assert ArtilleryCoverageRequest(dem_id="dem_a").target.lon is None
    with pytest.raises(ValueError):
        ArtilleryCoverageRequest(dem_id="dem_a", target={"lon": 79.9})
