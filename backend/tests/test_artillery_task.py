import numpy
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
