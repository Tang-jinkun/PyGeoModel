from pathlib import Path

import numpy
import pytest
import rasterio
from rasterio.transform import from_origin

from app.core.errors import AppError
from app.schemas.radar import CoverageRequest
from app.services.coverage_domain import build_coverage_domain
from app.services.coverage_model import (
    default_simplify_tolerance,
    prepare_coverage_dem,
    validate_coverage_extent,
    vectorize_visible_viewshed,
)
from app.services.geometry import make_range_geometry
from app.services.projection import utm_epsg_from_lonlat


def test_utm_epsg_from_lonlat_northern_and_southern() -> None:
    assert utm_epsg_from_lonlat(105.0, 35.0) == 32648
    assert utm_epsg_from_lonlat(105.0, -12.0) == 32748


def test_sector_geometry_uses_north_clockwise_azimuth() -> None:
    geom = make_range_geometry(0, 0, 1000, "sector", 0, 60)
    minx, miny, maxx, maxy = geom.bounds

    assert maxy == pytest.approx(1000, abs=1)
    assert miny == pytest.approx(0, abs=1)
    assert minx < 0
    assert maxx > 0


def test_default_simplify_tolerance_uses_resolution_when_missing() -> None:
    assert default_simplify_tolerance((30, 25), None) == 30
    assert default_simplify_tolerance((30, 25), 5) == 5


def test_build_coverage_domain_stops_at_first_nodata_gap() -> None:
    valid = numpy.ones((10, 10), dtype=bool)
    valid[2, 5] = False

    domain = build_coverage_domain(
        valid,
        from_origin(-50, 50, 10, 10),
        radar_x=5,
        radar_y=5,
        max_range_m=100,
        azimuth_step_deg=2,
    )

    assert domain.radius_m[0] < 30
    assert not domain.analysis_mask[0, 5]


def test_build_coverage_domain_preserves_other_azimuths() -> None:
    valid = numpy.ones((10, 10), dtype=bool)
    valid[2, 5] = False

    domain = build_coverage_domain(
        valid,
        from_origin(-50, 50, 10, 10),
        radar_x=5,
        radar_y=5,
        max_range_m=100,
        azimuth_step_deg=2,
    )

    assert domain.radius_m[45] >= 40


def test_advanced_height_layers_are_sorted_deduplicated_and_limited() -> None:
    request = make_request(lon=105.0, lat=35.0)
    request.advanced.height_layers_m = [500, 0, 100, 100, 250]
    normalized = CoverageRequest.model_validate(request.model_dump())

    assert normalized.advanced.height_layers_m == [0, 100, 250, 500]


def test_advanced_height_layers_rejects_too_many_values() -> None:
    payload = make_request(lon=105.0, lat=35.0).model_dump()
    payload["advanced"]["height_layers_m"] = list(range(21))

    with pytest.raises(ValueError):
        CoverageRequest.model_validate(payload)


def test_prepare_coverage_dem_reprojects_crop(tmp_path: Path) -> None:
    source = tmp_path / "source.tif"
    destination = tmp_path / "projected.tif"
    write_test_dem(source)

    prepared = prepare_coverage_dem(source, destination, make_request(lon=105.0, lat=35.0, max_range_m=2000))

    assert destination.exists()
    assert prepared.target_epsg == 32648
    assert prepared.radar_x > 0
    assert prepared.radar_y > 0
    assert prepared.resolution_m[0] > 0

    with rasterio.open(destination) as dataset:
        assert dataset.crs.to_epsg() == 32648
        assert dataset.width < 100
        assert dataset.height < 100


def test_prepare_coverage_dem_rejects_outside_radar(tmp_path: Path) -> None:
    source = tmp_path / "source.tif"
    write_test_dem(source)

    with pytest.raises(AppError) as exc_info:
        prepare_coverage_dem(source, tmp_path / "projected.tif", make_request(lon=110.0, lat=35.0))

    assert exc_info.value.code == "RADAR_OUTSIDE_DEM"


def test_validate_coverage_extent_rejects_mostly_outside_range(tmp_path: Path) -> None:
    source = tmp_path / "source.tif"
    write_test_dem(source)

    with pytest.raises(AppError) as exc_info:
        validate_coverage_extent(source, make_request(lon=105.0, lat=35.0, max_range_m=50_000))

    assert exc_info.value.code == "RANGE_OUTSIDE_DEM"


def test_prepare_coverage_dem_reports_dem_coverage_ratio(tmp_path: Path) -> None:
    source = tmp_path / "source.tif"
    destination = tmp_path / "projected.tif"
    write_test_dem(source)

    prepared = prepare_coverage_dem(source, destination, make_request(lon=105.0, lat=35.0, max_range_m=2000))

    assert 0 < prepared.dem_coverage_ratio <= 1


def test_prepare_coverage_dem_uses_full_requested_canvas(tmp_path: Path) -> None:
    source = tmp_path / "source.tif"
    destination = tmp_path / "projected.tif"
    write_test_dem(source)

    prepared = prepare_coverage_dem(
        source,
        destination,
        make_request(lon=105.0, lat=35.0, max_range_m=6000),
    )

    assert prepared.projected_bounds.left <= prepared.radar_x - 5900
    assert prepared.projected_bounds.right >= prepared.radar_x + 5900
    with rasterio.open(destination) as dataset:
        assert prepared.analysis_domain is not None
        assert prepared.analysis_domain.shape == (dataset.height, dataset.width)


def test_prepare_coverage_dem_rejects_radar_on_nodata(tmp_path: Path) -> None:
    source = tmp_path / "source.tif"
    write_test_dem(source, nodata_center=True)

    with pytest.raises(AppError) as exc_info:
        prepare_coverage_dem(
            source,
            tmp_path / "projected.tif",
            make_request(lon=105.0, lat=35.0),
        )

    assert exc_info.value.code == "RADAR_ON_DEM_NODATA"


def test_prepare_coverage_dem_keeps_negative_elevations_valid(tmp_path: Path) -> None:
    source = tmp_path / "source.tif"
    write_test_dem(source, elevation=-25)

    prepared = prepare_coverage_dem(
        source,
        tmp_path / "projected.tif",
        make_request(lon=105.0, lat=35.0),
    )

    assert prepared.analysis_domain is not None
    assert prepared.analysis_domain.any()


def test_vectorize_visible_viewshed(tmp_path: Path) -> None:
    viewshed = tmp_path / "viewshed.tif"
    transform = from_origin(0, 40, 10, 10)
    data = numpy.array(
        [
            [0, 255, 255, 0],
            [0, 255, 255, 0],
            [0, 0, 0, 0],
            [0, 0, 0, 0],
        ],
        dtype=numpy.uint8,
    )
    with rasterio.open(
        viewshed,
        "w",
        driver="GTiff",
        width=4,
        height=4,
        count=1,
        dtype=data.dtype,
        crs="EPSG:32648",
        transform=transform,
    ) as dataset:
        dataset.write(data, 1)

    geom = vectorize_visible_viewshed(viewshed)

    assert geom.area == pytest.approx(400)
    assert geom.bounds == pytest.approx((10, 20, 30, 40))


def write_test_dem(path: Path, *, nodata_center: bool = False, elevation: float | None = None) -> None:
    data = (
        numpy.full((100, 100), elevation, dtype=numpy.float32)
        if elevation is not None
        else numpy.arange(10_000, dtype=numpy.float32).reshape((100, 100))
    )
    if nodata_center:
        data[50, 50] = -9999
    transform = from_origin(104.95, 35.05, 0.001, 0.001)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=100,
        height=100,
        count=1,
        dtype=data.dtype,
        crs="EPSG:4326",
        transform=transform,
        nodata=-9999,
    ) as dataset:
        dataset.write(data, 1)


def make_request(lon: float, lat: float, max_range_m: float = 1000) -> CoverageRequest:
    return CoverageRequest.model_validate(
        {
            "dem_id": "dem_test",
            "radar": {"lon": lon, "lat": lat, "height_m": 10},
            "target": {"height_m": 0},
            "coverage": {
                "max_range_m": max_range_m,
                "scan_mode": "omni",
                "azimuth_deg": 0,
                "beam_width_deg": 360,
            },
            "advanced": {
                "use_curvature": True,
                "curvature_coeff": 0.75,
                "output_simplify_tolerance_m": None,
            },
        }
    )
