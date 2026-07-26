from pathlib import Path

import numpy
import rasterio
from rasterio.transform import from_origin

from app.schemas.radar import MultiRadarRequest
from app.services.multi_radar_dem import prepare_shared_multi_radar_dem


def test_shared_dem_projects_all_stations_to_one_grid(tmp_path: Path) -> None:
    source = tmp_path / "source.tif"
    with rasterio.open(
        source,
        "w",
        driver="GTiff",
        width=10,
        height=10,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(78.95, 31.55, 0.01, 0.01),
    ) as dataset:
        dataset.write(numpy.ones((1, 10, 10), dtype=numpy.float32))
    payload = MultiRadarRequest.model_validate(
        {
            "dem_id": "dem_a",
            "radars": [
                {"radar_id": "north", "radar": {"lon": 79.0, "lat": 31.5, "height_m": 20}, "coverage": {"max_range_m": 500}},
                {"radar_id": "south", "radar": {"lon": 79.01, "lat": 31.5, "height_m": 20}, "coverage": {"max_range_m": 500}},
            ],
        }
    )

    shared = prepare_shared_multi_radar_dem(source, tmp_path / "shared.tif", payload)

    assert shared.projected_dem.exists()
    assert set(shared.station_points) == {"north", "south"}
    assert shared.analysis_domain.any()
