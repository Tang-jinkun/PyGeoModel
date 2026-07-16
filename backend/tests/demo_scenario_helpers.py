from pathlib import Path

import numpy
import rasterio
from rasterio.transform import from_origin


def write_dem(path: Path, size: int = 80) -> None:
    rows, cols = numpy.indices((size, size))
    data = (rows * 40 + numpy.abs(cols - size // 2) * 15).astype("float32")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=size,
        height=size,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(79.0, 32.0, 0.005, 0.005),
    ) as dataset:
        dataset.write(data, 1)
