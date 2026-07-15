from math import atan, degrees, hypot, sqrt
from pathlib import Path
import warnings

import numpy
import pytest
import rasterio
from rasterio.transform import from_origin

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
