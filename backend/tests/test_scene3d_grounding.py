from math import atan, degrees, hypot, sqrt
from pathlib import Path
import warnings

import numpy
import pytest
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform as transform_points

from app.scene3d.grounding import sample_terrain_anchor


DEM_TRANSFORM = from_origin(499_800, 3_500_200, 10, 10)
DEM_SHAPE = (40, 40)
TARGET_POSITION = (500_000, 3_500_000)


def plane_dem(
    center_elevation_m: float,
    x_slope: float = 0,
    y_slope: float = 0,
) -> numpy.ndarray:
    rows, columns = numpy.indices(DEM_SHAPE, dtype=numpy.float64)
    x = DEM_TRANSFORM.c + (columns + 0.5) * DEM_TRANSFORM.a
    y = DEM_TRANSFORM.f + (rows + 0.5) * DEM_TRANSFORM.e
    return (
        center_elevation_m
        + x_slope * (x - TARGET_POSITION[0])
        + y_slope * (y - TARGET_POSITION[1])
    )


def write_dem(
    path: Path,
    elevation: numpy.ndarray,
    nodata: float | None = None,
) -> Path:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=elevation.shape[1],
        height=elevation.shape[0],
        count=1,
        dtype="float64",
        crs="EPSG:32644",
        transform=DEM_TRANSFORM,
        nodata=nodata,
    ) as dataset:
        dataset.write(elevation, 1)
    return path


def write_geographic_plane_dem(
    path: Path,
    center_elevation_m: float,
    x_slope: float,
    y_slope: float,
) -> Path:
    longitude, latitude = transform_points(
        "EPSG:32644",
        "EPSG:4326",
        [TARGET_POSITION[0]],
        [TARGET_POSITION[1]],
    )
    shape = (160, 160)
    pixel_size_deg = 0.00002
    geo_transform = from_origin(
        longitude[0] - shape[1] * pixel_size_deg / 2,
        latitude[0] + shape[0] * pixel_size_deg / 2,
        pixel_size_deg,
        pixel_size_deg,
    )
    rows, columns = numpy.indices(shape, dtype=numpy.float64)
    source_x = geo_transform.c + (columns + 0.5) * geo_transform.a
    source_y = geo_transform.f + (rows + 0.5) * geo_transform.e
    target_x, target_y = transform_points(
        "EPSG:4326",
        "EPSG:32644",
        source_x.ravel().tolist(),
        source_y.ravel().tolist(),
    )
    target_x_array = numpy.asarray(target_x).reshape(shape)
    target_y_array = numpy.asarray(target_y).reshape(shape)
    elevation = (
        center_elevation_m
        + x_slope * (target_x_array - TARGET_POSITION[0])
        + y_slope * (target_y_array - TARGET_POSITION[1])
    )

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=shape[1],
        height=shape[0],
        count=1,
        dtype="float64",
        crs="EPSG:4326",
        transform=geo_transform,
    ) as dataset:
        dataset.write(elevation, 1)
    return path


def test_sample_terrain_anchor_fits_flat_original_dem(tmp_path: Path) -> None:
    path = write_dem(tmp_path / "flat.tif", plane_dem(1_250))

    anchor = sample_terrain_anchor(
        path,
        32644,
        TARGET_POSITION,
        25,
        144,
        38.4,
    )

    assert anchor.ground_elevation_amsl_m == pytest.approx(1_250, abs=0.01)
    assert anchor.normal_enu == pytest.approx((0, 0, 1), abs=1e-12)
    assert anchor.slope_deg == pytest.approx(0, abs=0.1)
    assert anchor.fit_rmse_m <= 0.01
    assert anchor.max_residual_m <= 0.01


def test_sample_terrain_anchor_fits_sloped_original_dem(tmp_path: Path) -> None:
    x_slope = 0.1
    y_slope = -0.05
    path = write_dem(
        tmp_path / "sloped.tif",
        plane_dem(1_000, x_slope=x_slope, y_slope=y_slope),
    )

    anchor = sample_terrain_anchor(
        path,
        32644,
        TARGET_POSITION,
        25,
        144,
        38.4,
    )

    normal = numpy.asarray((-x_slope, -y_slope, 1), dtype=numpy.float64)
    normal /= numpy.linalg.norm(normal)
    expected_slope = degrees(atan(hypot(x_slope, y_slope)))
    assert anchor.ground_elevation_amsl_m == pytest.approx(1_000, abs=0.01)
    assert anchor.normal_enu == pytest.approx(normal, abs=1e-10)
    assert anchor.slope_deg == pytest.approx(expected_slope, abs=0.1)
    assert anchor.fit_rmse_m <= 0.01
    assert anchor.max_residual_m <= 0.01


def test_sample_terrain_anchor_transforms_target_coordinates_to_source_crs(
    tmp_path: Path,
) -> None:
    x_slope = 0.04
    y_slope = -0.025
    path = write_geographic_plane_dem(
        tmp_path / "geographic-plane.tif",
        center_elevation_m=875,
        x_slope=x_slope,
        y_slope=y_slope,
    )

    anchor = sample_terrain_anchor(
        path,
        32644,
        TARGET_POSITION,
        25,
        144,
        38.4,
    )

    normal = numpy.asarray((-x_slope, -y_slope, 1), dtype=numpy.float64)
    normal /= numpy.linalg.norm(normal)
    expected_slope = degrees(atan(hypot(x_slope, y_slope)))
    assert anchor.ground_elevation_amsl_m == pytest.approx(875, abs=0.01)
    assert anchor.normal_enu == pytest.approx(normal, abs=1e-5)
    assert anchor.slope_deg == pytest.approx(expected_slope, abs=0.01)
    assert anchor.fit_rmse_m <= 0.01
    assert anchor.max_residual_m <= 0.01


def test_sample_terrain_anchor_rejects_nodata_in_any_sample(
    tmp_path: Path,
) -> None:
    elevation = plane_dem(900)
    elevation[19, 19] = -9_999
    path = write_dem(tmp_path / "nodata.tif", elevation, nodata=-9_999)

    with pytest.raises(ValueError, match="terrain sample"):
        sample_terrain_anchor(
            path,
            32644,
            TARGET_POSITION,
            25,
            144,
            38.4,
        )


def test_sample_terrain_anchor_avoids_deprecated_masked_raster_reads(
    tmp_path: Path,
) -> None:
    path = write_dem(tmp_path / "flat.tif", plane_dem(1_250))

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        anchor = sample_terrain_anchor(
            path,
            32644,
            TARGET_POSITION,
            25,
            144,
            38.4,
        )

    assert anchor.ground_elevation_amsl_m == pytest.approx(1_250, abs=0.01)


def test_sample_terrain_anchor_reports_rough_plane_residuals(
    tmp_path: Path,
) -> None:
    elevation = plane_dem(100)
    elevation[19:21, 19:21] = 109
    path = write_dem(tmp_path / "rough.tif", elevation)

    anchor = sample_terrain_anchor(
        path,
        32644,
        TARGET_POSITION,
        0,
        144,
        38.4,
    )

    assert anchor.ground_elevation_amsl_m == pytest.approx(101, abs=0.01)
    assert anchor.fit_rmse_m == pytest.approx(sqrt(8), abs=0.01)
    assert anchor.max_residual_m == pytest.approx(8, abs=0.01)
