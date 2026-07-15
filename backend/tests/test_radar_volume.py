from pathlib import Path

import numpy
import rasterio
from rasterio.coords import BoundingBox
from rasterio.transform import from_origin

from app.schemas.radar import CoverageRequest
from app.scene3d.radar_volume import build_radar_visibility_volume
from app.services.coverage_model import PreparedCoverageDem


def test_visibility_volume_carves_terrain_and_unknown_space(tmp_path: Path) -> None:
    dem_path = tmp_path / "projected-dem.tif"
    min_height_path = tmp_path / "minimum-visible-height.tif"
    nodata = -9999.0
    shape = (25, 25)
    transform = from_origin(-1_250, 1_250, 100, 100)

    dem = numpy.full(shape, 100, dtype=numpy.float32)
    dem[4:21, 15:17] = 450
    dem[:7, :7] = nodata

    min_visible_height = numpy.zeros(shape, dtype=numpy.float32)
    lee_columns = numpy.arange(shape[1], dtype=numpy.float32)
    min_visible_height[:, 17:] = 100 + (lee_columns[17:] - 16) * 45
    min_visible_height[:7, :7] = nodata

    for path, data in ((dem_path, dem), (min_height_path, min_visible_height)):
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=shape[1],
            height=shape[0],
            count=1,
            dtype=data.dtype,
            crs="EPSG:32644",
            transform=transform,
            nodata=nodata,
        ) as dataset:
            dataset.write(data, 1)

    payload = CoverageRequest.model_validate(
        {
            "dem_id": "dem_radar_volume",
            "radar": {"lon": 79.0, "lat": 31.5, "height_m": 50},
            "coverage": {"max_range_m": 1_000, "scan_mode": "omni"},
        }
    )
    prepared = PreparedCoverageDem(
        source_dem=dem_path,
        projected_dem=dem_path,
        target_epsg=32644,
        radar_x=0,
        radar_y=0,
        projected_bounds=BoundingBox(-1_250, -1_250, 1_250, 1_250),
        resolution_m=(100, 100),
        dem_coverage_ratio=0.9,
        analysis_domain=dem != nodata,
    )

    volume = build_radar_visibility_volume(
        prepared,
        payload,
        min_height_path,
        grid_shape=(40, 40, 24),
    )

    x = numpy.linspace(-1_000, 1_000, 40)
    y = numpy.linspace(-1_000, 1_000, 40)
    z = numpy.linspace(0, 1_000, 24)
    xx, yy, zz = numpy.meshgrid(x, y, z, indexing="xy")
    uncarved_hemisphere_count = numpy.count_nonzero(xx * xx + yy * yy + zz * zz <= 1_000**2)

    assert volume.grid_shape == (40, 40, 24)
    assert volume.vertices.shape[1] == 3
    assert volume.faces.shape[1] == 3
    assert len(volume.vertices) > 0
    assert len(volume.faces) > 0
    assert 0 < volume.occupied_voxel_count < uncarved_hemisphere_count
    assert volume.terrain_segments.shape[0] > 0
    assert volume.terrain_segments.shape[1:] == (2, 3)
    assert volume.unknown_segments.shape[0] > 0
    assert volume.unknown_segments.shape[1:] == (2, 3)
