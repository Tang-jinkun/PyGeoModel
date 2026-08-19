from pathlib import Path

import numpy
import pytest
from rasterio.coords import BoundingBox
from rasterio.transform import from_origin

from app.schemas.artillery import ArtilleryCoverageRequest
from app.workers.artillery_task import (
    PreparedArtilleryDem,
    _compute_artillery_masks,
    _solve_ballistic_angles,
    _trajectory_clearance,
    _trajectory_solutions,
)


def test_automatic_ballistic_solver_returns_low_and_high_angles() -> None:
    angles = _solve_ballistic_angles(
        horizontal_distance_m=500,
        height_delta_m=0,
        muzzle_velocity_mps=100,
    )

    assert angles == pytest.approx([14.6812, 75.3188], abs=0.001)


def test_automatic_ballistic_solver_returns_no_solution_beyond_physical_range() -> None:
    assert _solve_ballistic_angles(
        horizontal_distance_m=2_000,
        height_delta_m=0,
        muzzle_velocity_mps=100,
    ) == []


def test_artillery_defaults_to_automatic_trajectory_mode() -> None:
    payload = ArtilleryCoverageRequest(dem_id="dem_a")

    assert payload.weapon.trajectory_mode == "auto"


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


def test_trajectory_clearance_accepts_a_solved_elevation_angle() -> None:
    dem = numpy.zeros((20, 20), dtype=numpy.float32)
    transform = from_origin(0, 2000, 100, 100)
    payload = ArtilleryCoverageRequest(
        dem_id="dem_a",
        weapon={"trajectory_mode": "auto", "muzzle_velocity_mps": 100, "min_range_m": 100, "max_range_m": 2000},
        analysis={"trajectory_samples": 20},
    )

    low, high = _solve_ballistic_angles(500, 0, 100)
    low_result = _trajectory_clearance(dem, transform, None, 50, 950, 0, 550, 950, 0, payload, elevation_deg=low)
    high_result = _trajectory_clearance(dem, transform, None, 50, 950, 0, 550, 950, 0, payload, elevation_deg=high)

    assert low_result["elevation_deg"] == pytest.approx(low)
    assert high_result["elevation_deg"] == pytest.approx(high)
    assert low_result["trajectory_peak_m"] < high_result["trajectory_peak_m"]


def test_automatic_trajectory_solutions_keep_high_path_when_low_path_is_masked() -> None:
    dem = numpy.zeros((40, 40), dtype=numpy.float32)
    dem[:, 10:12] = 100
    transform = from_origin(0, 1000, 25, 25)
    payload = ArtilleryCoverageRequest(
        dem_id="dem_a",
        weapon={"trajectory_mode": "auto", "muzzle_velocity_mps": 100, "min_range_m": 100, "max_range_m": 2000},
        analysis={"trajectory_samples": 80},
    )

    solutions = _trajectory_solutions(dem, transform, None, 25, 500, 0, 525, 500, 0, payload)

    assert [solution["kind"] for solution in solutions] == ["low", "high"]
    assert [solution["is_clear"] for solution in solutions] == [False, True]


def test_manual_trajectory_mode_returns_only_configured_angle() -> None:
    dem = numpy.zeros((40, 40), dtype=numpy.float32)
    transform = from_origin(0, 1000, 25, 25)
    payload = ArtilleryCoverageRequest(
        dem_id="dem_a",
        weapon={"trajectory_mode": "manual", "elevation_deg": 30, "muzzle_velocity_mps": 100, "min_range_m": 100, "max_range_m": 2000},
    )

    solutions = _trajectory_solutions(dem, transform, None, 25, 500, 0, 525, 500, 0, payload)

    assert len(solutions) == 1
    assert solutions[0]["kind"] == "manual"
    assert solutions[0]["elevation_deg"] == 30


def test_zero_distance_has_no_trajectory_solution() -> None:
    dem = numpy.zeros((4, 4), dtype=numpy.float32)
    transform = from_origin(0, 100, 25, 25)
    payload = ArtilleryCoverageRequest(
        dem_id="dem_a",
        weapon={"trajectory_mode": "manual", "elevation_deg": 30, "min_range_m": 0, "max_range_m": 2000},
    )

    solutions = _trajectory_solutions(dem, transform, None, 25, 75, 0, 25, 75, 0, payload)

    assert solutions == []


def test_automatic_mode_does_not_create_a_solution_beyond_physical_range() -> None:
    dem = numpy.zeros((40, 40), dtype=numpy.float32)
    transform = from_origin(0, 1000, 25, 25)
    payload = ArtilleryCoverageRequest(
        dem_id="dem_a",
        weapon={"trajectory_mode": "auto", "muzzle_velocity_mps": 100, "min_range_m": 0, "max_range_m": 5000},
        analysis={"use_terrain_masking": False},
    )

    solutions = _trajectory_solutions(dem, transform, None, 25, 500, 0, 2025, 500, 0, payload)

    assert solutions == []


@pytest.mark.parametrize("use_terrain_masking", [False, True])
def test_coverage_keeps_physically_unreachable_cells_out_of_terrain_masking(use_terrain_masking: bool) -> None:
    dem = numpy.zeros((20, 100), dtype=numpy.float32)
    transform = from_origin(0, 1000, 50, 50)
    prepared = PreparedArtilleryDem(
        projected_dem=Path("unused.tif"),
        target_epsg=32644,
        battery_x=25,
        battery_y=500,
        bounds=BoundingBox(0, 0, 5000, 1000),
        resolution_m=(50, 50),
    )
    payload = ArtilleryCoverageRequest(
        dem_id="dem_a",
        battery={"height_m": 0},
        weapon={"trajectory_mode": "auto", "muzzle_velocity_mps": 100, "min_range_m": 0, "max_range_m": 4500},
        analysis={"use_terrain_masking": use_terrain_masking, "sample_resolution_m": 50},
    )

    masks, _, _, metrics, _ = _compute_artillery_masks(dem, transform, None, prepared, payload)

    assert masks["reachable"].sum() < masks["theoretical"].sum()
    assert not masks["terrain_masked"].any()
    assert metrics.masked_sample_count == 0


def test_manual_trajectory_does_not_force_a_mismatched_angle_through_target() -> None:
    dem = numpy.zeros((40, 40), dtype=numpy.float32)
    transform = from_origin(0, 1000, 25, 25)
    payload = ArtilleryCoverageRequest(
        dem_id="dem_a",
        weapon={"trajectory_mode": "manual", "elevation_deg": 30, "muzzle_velocity_mps": 100, "min_range_m": 0, "max_range_m": 2000},
    )

    solution = _trajectory_solutions(dem, transform, None, 25, 500, 0, 525, 500, 0, payload)[0]

    assert solution["hits_target"] is False
    assert solution["is_clear"] is False
    assert solution["impact_height_error_m"] == pytest.approx(125.2, abs=0.2)
    assert solution["trajectory"][-1]["z"] == pytest.approx(125.2, abs=0.2)


def test_manual_trajectory_can_hit_target_with_a_solved_angle() -> None:
    dem = numpy.zeros((40, 40), dtype=numpy.float32)
    transform = from_origin(0, 1000, 25, 25)
    low_angle = _solve_ballistic_angles(500, 0, 100)[0]
    payload = ArtilleryCoverageRequest(
        dem_id="dem_a",
        weapon={"trajectory_mode": "manual", "elevation_deg": low_angle, "muzzle_velocity_mps": 100, "min_range_m": 0, "max_range_m": 2000},
    )

    solution = _trajectory_solutions(dem, transform, None, 25, 500, 0, 525, 500, 0, payload)[0]

    assert solution["hits_target"] is True
    assert solution["is_clear"] is True


def test_trajectory_crossing_nodata_is_not_considered_clear() -> None:
    dem = numpy.zeros((40, 40), dtype=numpy.float32)
    dem[:, 10:12] = numpy.nan
    transform = from_origin(0, 1000, 25, 25)
    payload = ArtilleryCoverageRequest(
        dem_id="dem_a",
        weapon={"trajectory_mode": "auto", "muzzle_velocity_mps": 100, "min_range_m": 0, "max_range_m": 2000},
        analysis={"trajectory_samples": 80, "use_terrain_masking": True},
    )

    solutions = _trajectory_solutions(dem, transform, None, 25, 500, 0, 525, 500, 0, payload)

    assert solutions
    assert all(solution["terrain_data_complete"] is False for solution in solutions)
    assert all(solution["is_clear"] is False for solution in solutions)


def test_downhill_single_positive_solution_is_named_high() -> None:
    dem = numpy.zeros((80, 80), dtype=numpy.float32)
    transform = from_origin(0, 2000, 25, 25)
    payload = ArtilleryCoverageRequest(
        dem_id="dem_a",
        weapon={"trajectory_mode": "auto", "muzzle_velocity_mps": 100, "min_range_m": 0, "max_range_m": 2000},
    )

    solutions = _trajectory_solutions(dem, transform, None, 25, 1000, 200, 525, 1000, 0, payload)

    assert len(solutions) == 1
    assert solutions[0]["kind"] == "high"
    assert solutions[0]["elevation_deg"] == pytest.approx(76.69, abs=0.01)


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
    assert result["trajectory"][-1]["z"] == pytest.approx(result["impact_height_error_m"])
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
