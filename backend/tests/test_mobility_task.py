import numpy
from rasterio.transform import from_origin

from app.schemas.mobility import MobilityAccessibilityRequest
from app.workers.mobility_task import _compute_mobility


class Prepared:
    target_epsg = 32644
    start_x = 5.0
    start_y = 95.0
    end_x = 95.0
    end_y = 95.0
    bounds = type("Bounds", (), {"left": 0, "bottom": 0, "right": 100, "top": 100})()
    resolution_m = (10, 10)


def test_flat_dem_prefers_wheeled_vehicle() -> None:
    dem = numpy.zeros((10, 10), dtype=numpy.float32)
    transform = from_origin(0, 100, 10, 10)
    payload = MobilityAccessibilityRequest(
        dem_id="dem_a",
        start={"lon": 79.8, "lat": 31.48},
        end={"lon": 79.81, "lat": 31.48},
        vehicles={
            "wheeled": {"base_speed_kph": 60, "max_slope_deg": 18, "offroad_speed_multiplier": 1.0},
            "tracked": {"base_speed_kph": 30, "max_slope_deg": 30, "offroad_speed_multiplier": 1.0},
        },
    )

    result = _compute_mobility(dem, transform, None, Prepared(), payload)

    assert result["metrics"].winner == "wheeled"
    assert result["metrics"].wheeled.reachable is True
    assert result["metrics"].tracked.reachable is True
    assert result["metrics"].wheeled.travel_time_seconds < result["metrics"].tracked.travel_time_seconds


def test_steep_dem_blocks_wheeled_but_allows_tracked() -> None:
    dem = numpy.zeros((10, 10), dtype=numpy.float32)
    dem[:, :] = numpy.arange(10, dtype=numpy.float32) * 3
    transform = from_origin(0, 100, 10, 10)
    payload = MobilityAccessibilityRequest(
        dem_id="dem_a",
        start={"lon": 79.8, "lat": 31.48},
        end={"lon": 79.81, "lat": 31.48},
        vehicles={
            "wheeled": {"base_speed_kph": 60, "max_slope_deg": 10, "offroad_speed_multiplier": 1.0},
            "tracked": {"base_speed_kph": 30, "max_slope_deg": 30, "offroad_speed_multiplier": 1.0},
        },
    )

    result = _compute_mobility(dem, transform, None, Prepared(), payload)

    assert result["metrics"].winner == "tracked"
    assert result["metrics"].wheeled.reachable is False
    assert result["metrics"].tracked.reachable is True
