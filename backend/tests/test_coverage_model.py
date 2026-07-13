from pathlib import Path

import numpy
import pytest
import rasterio
from rasterio.transform import from_origin

from app.core.errors import AppError
from app.schemas.radar import CoverageRequest
from app.services.coverage_domain import build_coverage_domain
from app.services.coverage_model import (
    _coverage_ratio_for_domain,
    bounded_canvas,
    default_simplify_tolerance,
    prepare_coverage_dem,
    project_lonlat_to_crs,
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


def test_bounded_canvas_scales_resolution_to_fit_cell_budget() -> None:
    width, height, x_resolution, y_resolution = bounded_canvas(
        (0, 0, 200_000, 200_000),
        10,
        10,
        max_cells=10_000,
    )

    assert width * height <= 10_000
    assert width * x_resolution >= 200_000
    assert height * y_resolution >= 200_000
    assert x_resolution / 10 == pytest.approx(y_resolution / 10)


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


def test_build_coverage_domain_clips_off_ray_nodata_gap() -> None:
    valid = numpy.ones((200, 200), dtype=bool)
    valid[14, 101] = False

    domain = build_coverage_domain(
        valid,
        from_origin(-1000, 1000, 10, 10),
        radar_x=0,
        radar_y=0,
        max_range_m=950,
        azimuth_step_deg=2,
    )

    assert not domain.analysis_mask[14, 101]
    assert not domain.analysis_mask[5, 101]
    assert domain.analysis_mask[14, 106]


def test_build_coverage_domain_rasterizes_profile_in_row_chunks(monkeypatch) -> None:
    valid = numpy.ones((1025, 4), dtype=bool)
    transform = from_origin(-20, 5125, 10, 10)
    original_meshgrid = numpy.meshgrid
    row_chunk_sizes: list[int] = []

    def bounded_meshgrid(rows, cols, *args, **kwargs):
        row_chunk_sizes.append(len(rows))
        assert len(rows) <= 256
        return original_meshgrid(rows, cols, *args, **kwargs)

    monkeypatch.setattr(numpy, "meshgrid", bounded_meshgrid)

    domain = build_coverage_domain(
        valid,
        transform,
        radar_x=5,
        radar_y=5,
        max_range_m=100,
        azimuth_step_deg=2,
    )

    assert domain.analysis_mask.shape == valid.shape
    assert len(row_chunk_sizes) > 1


def test_coverage_ratio_counts_requested_pixels_in_row_chunks(monkeypatch) -> None:
    domain = numpy.ones((1025, 4), dtype=bool)
    transform = from_origin(-20, 5125, 10, 10)
    original_meshgrid = numpy.meshgrid
    row_chunk_sizes: list[int] = []

    def bounded_meshgrid(rows, cols, *args, **kwargs):
        row_chunk_sizes.append(len(rows))
        assert len(rows) <= 256
        return original_meshgrid(rows, cols, *args, **kwargs)

    monkeypatch.setattr(numpy, "meshgrid", bounded_meshgrid)

    ratio = _coverage_ratio_for_domain(
        domain,
        transform,
        radar_x=5,
        radar_y=5,
        payload=make_request(lon=105.0, lat=35.0, max_range_m=100),
        effective_range_m=100,
    )

    assert ratio == pytest.approx(1)
    assert len(row_chunk_sizes) > 1


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
    assert prepared.resolution_adjusted is False

    with rasterio.open(destination) as dataset:
        assert dataset.crs.to_epsg() == 32648
        assert dataset.width < 100
        assert dataset.height < 100


def test_prepare_coverage_dem_reports_adjusted_resolution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "source.tif"
    destination = tmp_path / "projected.tif"
    write_test_dem(source)
    monkeypatch.setattr("app.services.coverage_model.MAX_COVERAGE_CELLS", 100)

    prepared = prepare_coverage_dem(
        source,
        destination,
        make_request(lon=105.0, lat=35.0, max_range_m=2000),
    )

    assert prepared.resolution_adjusted is True
    with rasterio.open(destination) as dataset:
        assert dataset.width * dataset.height <= 100


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


def test_validate_coverage_extent_uses_radar_equation_effective_range(tmp_path: Path) -> None:
    source = tmp_path / "source.tif"
    write_test_dem(source)
    request = make_request(lon=105.0, lat=35.0, max_range_m=50_000)
    request.reserved_radar_params.frequency_hz = 1_000_000_000
    request.reserved_radar_params.transmit_power_w = 1
    request.reserved_radar_params.antenna_gain_db = 0
    request.reserved_radar_params.receiver_sensitivity_dbm = -140
    request.reserved_radar_params.target_rcs_m2 = 1
    request.reserved_radar_params.system_loss_db = 0

    ratio = validate_coverage_extent(source, request)

    assert ratio == pytest.approx(1)


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


def test_prepare_coverage_dem_marks_nan_without_nodata_as_invalid(tmp_path: Path) -> None:
    source = tmp_path / "source.tif"
    destination = tmp_path / "projected.tif"
    write_test_dem(source, nan_cell=(50, 53), nodata=None)

    prepared = prepare_coverage_dem(
        source,
        destination,
        make_request(lon=105.0, lat=35.0),
    )

    nan_lon = 104.95 + (53.5 * 0.001)
    nan_lat = 35.05 - (50.5 * 0.001)
    nan_x, nan_y = project_lonlat_to_crs(nan_lon, nan_lat, f"EPSG:{prepared.target_epsg}")
    with rasterio.open(destination) as dataset:
        nan_row, nan_col = dataset.index(nan_x, nan_y)

    assert prepared.analysis_domain is not None
    assert not prepared.analysis_domain[nan_row, nan_col]


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


def write_test_dem(
    path: Path,
    *,
    nodata_center: bool = False,
    elevation: float | None = None,
    nan_cell: tuple[int, int] | None = None,
    nodata: float | None = -9999,
) -> None:
    data = (
        numpy.full((100, 100), elevation, dtype=numpy.float32)
        if elevation is not None
        else numpy.arange(10_000, dtype=numpy.float32).reshape((100, 100))
    )
    if nodata_center:
        data[50, 50] = -9999
    if nan_cell is not None:
        data[nan_cell] = numpy.nan
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
        nodata=nodata,
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
