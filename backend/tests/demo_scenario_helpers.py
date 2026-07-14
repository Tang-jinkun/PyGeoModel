from pathlib import Path

import numpy
import rasterio
from rasterio.transform import from_origin


def write_dem(path: Path) -> None:
    rows, cols = numpy.indices((80, 80))
    data = (rows * 40 + numpy.abs(cols - 40) * 15).astype("float32")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=80,
        height=80,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(79.0, 32.0, 0.005, 0.005),
    ) as dataset:
        dataset.write(data, 1)
