import io
import math
from functools import lru_cache
from pathlib import Path

import numpy
from PIL import Image
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject, transform_bounds

from app.core.errors import AppError
from app.services.dem_store import find_dem_cog_file

TILE_SIZE = 256
MAX_TILE_ZOOM = 16


def render_dem_tile(dem_id: str, z: int, x: int, y: int) -> bytes:
    data = read_dem_tile_data(dem_id, z, x, y)
    if data is None:
        return transparent_png()
    return encode_dem_png(data, dem_color_range(find_dem_cog_file(dem_id)))


def render_terrain_tile(dem_id: str, z: int, x: int, y: int) -> bytes:
    data = read_dem_tile_data(dem_id, z, x, y)
    if data is None:
        return terrarium_png(numpy.zeros((TILE_SIZE, TILE_SIZE), dtype="float32"))
    return terrarium_png(numpy.ma.filled(data.astype("float32"), 0))


def read_dem_tile_data(dem_id: str, z: int, x: int, y: int) -> numpy.ma.MaskedArray | None:
    if z < 0 or z > MAX_TILE_ZOOM:
        raise AppError("INVALID_TILE_ZOOM", f"DEM tile zoom must be between 0 and {MAX_TILE_ZOOM}.", status_code=400)
    max_index = 2**z
    if x < 0 or y < 0 or x >= max_index or y >= max_index:
        raise AppError("INVALID_TILE_COORDINATE", "DEM tile coordinate is outside the zoom range.", status_code=400)

    import rasterio

    dem_path = find_dem_cog_file(dem_id)
    with rasterio.open(dem_path) as dataset:
        tile_bounds = tile_bounds_web_mercator(z, x, y)
        source_bounds = transform_bounds("EPSG:3857", dataset.crs, *tile_bounds, densify_pts=21)
        dem_bounds = dataset.bounds
        if not bounds_intersect(source_bounds, (dem_bounds.left, dem_bounds.bottom, dem_bounds.right, dem_bounds.top)):
            return None

        destination = numpy.full((TILE_SIZE, TILE_SIZE), numpy.nan, dtype="float32")
        reproject(
            source=rasterio.band(dataset, 1),
            destination=destination,
            src_transform=dataset.transform,
            src_crs=dataset.crs,
            src_nodata=dataset.nodata,
            dst_transform=from_bounds(*tile_bounds, TILE_SIZE, TILE_SIZE),
            dst_crs="EPSG:3857",
            dst_nodata=numpy.nan,
            resampling=Resampling.bilinear,
        )

    data = numpy.ma.masked_invalid(destination)
    return None if data.count() == 0 else data


def tile_bounds_web_mercator(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    origin_shift = 20037508.342789244
    tile_span = 2 * origin_shift / (2**z)
    west = -origin_shift + x * tile_span
    east = west + tile_span
    north = origin_shift - y * tile_span
    south = north - tile_span
    return west, south, east, north


def tile_bounds_lonlat(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    n = 2.0**z
    west = x / n * 360.0 - 180.0
    east = (x + 1) / n * 360.0 - 180.0
    north = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    south = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return west, south, east, north


def bounds_intersect(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


@lru_cache(maxsize=64)
def dem_color_range(dem_path: Path) -> tuple[float, float]:
    import rasterio

    with rasterio.open(dem_path) as dataset:
        stats = dataset.statistics(1, approx=True, clear_cache=False)
        vmin = float(stats.min)
        vmax = float(stats.max)
        if math.isfinite(vmin) and math.isfinite(vmax) and vmax > vmin:
            return vmin, vmax

        data = dataset.read(1, masked=True, out_shape=(1, 512, 512), resampling=Resampling.bilinear)
        values = numpy.ma.filled(data.astype("float32"), numpy.nan)
        finite = numpy.isfinite(values)
        if not finite.any():
            return 0, 1
        valid_values = values[finite]
        vmin = float(numpy.nanpercentile(valid_values, 2))
        vmax = float(numpy.nanpercentile(valid_values, 98))
        if math.isfinite(vmin) and math.isfinite(vmax) and vmax > vmin:
            return vmin, vmax
        return float(numpy.nanmin(valid_values)), float(numpy.nanmax(valid_values))


def encode_dem_png(data: numpy.ma.MaskedArray, color_range: tuple[float, float] | None = None) -> bytes:
    values = numpy.ma.filled(data.astype("float32"), numpy.nan)
    finite = numpy.isfinite(values)
    if not finite.any():
        return transparent_png()

    if color_range:
        vmin, vmax = color_range
    else:
        valid_values = values[finite]
        vmin = float(numpy.nanpercentile(valid_values, 2))
        vmax = float(numpy.nanpercentile(valid_values, 98))
    if not math.isfinite(vmin) or not math.isfinite(vmax) or vmax <= vmin:
        valid_values = values[finite]
        vmin = float(numpy.nanmin(valid_values))
        vmax = float(numpy.nanmax(valid_values))
    if vmax <= vmin:
        normalized = numpy.zeros_like(values, dtype="float32")
    else:
        normalized = numpy.clip((values - vmin) / (vmax - vmin), 0, 1)
    normalized = numpy.where(finite, normalized, 0)

    rgba = numpy.zeros((TILE_SIZE, TILE_SIZE, 4), dtype=numpy.uint8)
    rgba[..., 0] = numpy.where(normalized < 0.5, 46 + normalized * 2 * 110, 156 + (normalized - 0.5) * 2 * 88).astype(numpy.uint8)
    rgba[..., 1] = numpy.where(normalized < 0.5, 125 + normalized * 2 * 78, 203 - (normalized - 0.5) * 2 * 79).astype(numpy.uint8)
    rgba[..., 2] = numpy.where(normalized < 0.5, 50 + normalized * 2 * 57, 107 - (normalized - 0.5) * 2 * 65).astype(numpy.uint8)
    rgba[..., 3] = numpy.where(finite, 185, 0).astype(numpy.uint8)
    return png_bytes(rgba)


def terrarium_png(data: numpy.ndarray) -> bytes:
    encoded = numpy.clip(data + 32768.0, 0, 65535.99609375)
    red = numpy.floor(encoded / 256.0)
    green = numpy.floor(encoded - red * 256.0)
    blue = numpy.floor((encoded - red * 256.0 - green) * 256.0)
    rgba = numpy.zeros((TILE_SIZE, TILE_SIZE, 4), dtype=numpy.uint8)
    rgba[..., 0] = red.astype(numpy.uint8)
    rgba[..., 1] = green.astype(numpy.uint8)
    rgba[..., 2] = blue.astype(numpy.uint8)
    rgba[..., 3] = 255
    return png_bytes(rgba)


@lru_cache(maxsize=1)
def transparent_png() -> bytes:
    return png_bytes(numpy.zeros((TILE_SIZE, TILE_SIZE, 4), dtype=numpy.uint8))


def png_bytes(rgba: numpy.ndarray) -> bytes:
    output = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(output, format="PNG", optimize=True)
    return output.getvalue()
