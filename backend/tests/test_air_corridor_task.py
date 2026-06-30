import numpy
from rasterio.transform import from_origin

from app.schemas.air_corridor import AirCorridorPlanningRequest
from app.workers.air_corridor_task import _compute_air_corridor


class Prepared:
    target_epsg = 32644
    start_x = 5.0
    start_y = 95.0
    end_x = 95.0
    end_y = 95.0
    threat_xy = {"sam_1": (45.0, 95.0)}
    bounds = type("Bounds", (), {"left": 0, "bottom": 0, "right": 100, "top": 100})()
    resolution_m = (10, 10)


def test_air_corridor_flat_dem_finds_route_without_threat() -> None:
    dem = numpy.zeros((10, 10), dtype=numpy.float32)
    transform = from_origin(0, 100, 10, 10)
    payload = AirCorridorPlanningRequest(
        dem_id="dem_a",
        start={"lon": 79.8, "lat": 31.48, "altitude_m": 300},
        end={"lon": 79.81, "lat": 31.48, "altitude_m": 300},
        altitude_layers_m=[300],
        threats=[],
    )
    prepared = Prepared()
    prepared.threat_xy = {}

    result = _compute_air_corridor(dem, transform, None, prepared, payload)

    assert result["metrics"].route_found is True
    assert result["metrics"].risk_score == 0
    assert result["metrics"].corridor_length_m > 0


def test_air_corridor_uses_higher_layer_to_reduce_threat_risk() -> None:
    dem = numpy.zeros((10, 10), dtype=numpy.float32)
    transform = from_origin(0, 100, 10, 10)
    payload = AirCorridorPlanningRequest(
        dem_id="dem_a",
        start={"lon": 79.8, "lat": 31.48, "altitude_m": 300},
        end={"lon": 79.81, "lat": 31.48, "altitude_m": 300},
        altitude_layers_m=[300, 1200],
        threats=[
            {
                "id": "sam_1",
                "lon": 79.805,
                "lat": 31.48,
                "max_range_m": 60,
                "min_altitude_m": 0,
                "max_altitude_m": 900,
                "threat_level": 10,
            }
        ],
        planning={"allow_altitude_change": True, "threat_weight": 20, "altitude_change_weight": 0.01},
    )

    result = _compute_air_corridor(dem, transform, None, Prepared(), payload)

    assert result["metrics"].route_found is True
    assert result["metrics"].altitude_change_count > 0
    assert result["metrics"].max_altitude_m == 1200
