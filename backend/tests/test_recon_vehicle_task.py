from pathlib import Path

import numpy
import rasterio
from rasterio.transform import from_origin

from app.workers.recon_vehicle_task import _read_viewshed_mask


def test_read_viewshed_mask_aligns_cropped_raster_to_dem_grid(tmp_path: Path) -> None:
    path = tmp_path / "viewshed.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=2,
        height=2,
        count=1,
        dtype="uint8",
        crs="EPSG:32644",
        transform=from_origin(1, 3, 1, 1),
        nodata=0,
    ) as dataset:
        dataset.write(numpy.array([[1, 0], [0, 1]], dtype="uint8"), 1)

    mask = _read_viewshed_mask(
        path,
        out_shape=(4, 4),
        dst_transform=from_origin(0, 4, 1, 1),
    )

    assert mask.shape == (4, 4)
    assert mask[1, 1]
    assert mask[2, 2]
    assert mask.sum() == 2
