from pathlib import Path

import numpy
import pytest
import rasterio
from rasterio.coords import BoundingBox
from rasterio.transform import from_origin

from app.schemas.radar import CoverageRequest
from app.scene3d.radar_volume import (
    _bounded_grid_shape,
    _extract_surface,
    _terrain_contact_segments,
    _unknown_boundary_segments,
    build_radar_visibility_volume,
)
from app.services.coverage_model import PreparedCoverageDem


def test_default_grid_shape_follows_payload_preview_resolution() -> None:
    payload = CoverageRequest.model_validate(
        {
            "dem_id": "dem_grid_shape",
            "radar": {"lon": 79.0, "lat": 31.5, "height_m": 0},
            "coverage": {"max_range_m": 1_000},
            "advanced": {"voxel_grid_size": 48, "voxel_vertical_levels": 8},
        }
    )

    assert _bounded_grid_shape(None, payload) == (64, 64, 32)
    assert _bounded_grid_shape((7, 8, 9), payload) == (7, 8, 9)
    assert _bounded_grid_shape((300, 300, 200), payload) == (256, 256, 128)


def test_terrain_contacts_are_triangle_height_field_intersections() -> None:
    vertices = numpy.asarray(
        [
            [0.0, 0.0, -1.0],
            [1.0, 0.0, 1.0],
            [1.0, 1.0, 1.0],
            [0.0, 1.0, -1.0],
        ]
    )
    faces = numpy.asarray([[0, 1, 2], [0, 2, 3]])
    terrain = numpy.zeros((2, 2), dtype=numpy.float64)
    segments = _terrain_contact_segments(
        vertices,
        faces,
        terrain,
        numpy.zeros_like(terrain),
        numpy.ones_like(terrain, dtype=bool),
        origin=(0.0, 0.0),
        pitch=(1.0, 1.0, 2.0),
    )

    assert segments.shape == (2, 2, 3)
    assert numpy.allclose(segments[:, :, 0], 0.5)
    assert numpy.allclose(segments[:, :, 2], 0.0)
    assert numpy.all(numpy.linalg.norm(segments[:, 1] - segments[:, 0], axis=1) > 0)
    canonical = numpy.sort(numpy.round(segments, 12), axis=1)
    assert len(numpy.unique(canonical.reshape(len(canonical), -1), axis=0)) == 2


def test_unknown_boundaries_use_sampled_terrain_height() -> None:
    payload = CoverageRequest.model_validate(
        {
            "dem_id": "dem_unknown_height",
            "radar": {"lon": 79.0, "lat": 31.5, "height_m": 0},
            "coverage": {"max_range_m": 10_000},
        }
    )
    terrain = numpy.asarray([[10.0, 20.0], [30.0, 40.0]])
    valid = numpy.asarray([[True, True], [True, False]])

    segments = _unknown_boundary_segments(
        valid,
        terrain,
        numpy.full_like(terrain, 500.0),
        1_000.0,
        origin=(0.0, 0.0),
        pitch=(1.0, 1.0),
        radar_xy=(0.0, 0.0),
        effective_range_m=10_000.0,
        payload=payload,
    )

    assert len(segments) > 0
    assert set(segments[:, :, 2].ravel()).issubset({10.0, 20.0, 30.0})


@pytest.mark.parametrize("occupied", [False, True])
def test_empty_or_degenerate_occupancy_raises_clear_error(occupied: bool) -> None:
    occupancy = numpy.full((3, 3, 3), occupied, dtype=bool)

    with pytest.raises(ValueError, match="occupancy.*surface"):
        _extract_surface(
            occupancy,
            spacing=(1.0, 1.0, 1.0),
            origin=(0.0, 0.0, 0.0),
        )


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
    unknown_distance = numpy.hypot(
        volume.unknown_segments[:, :, 0] - prepared.radar_x,
        volume.unknown_segments[:, :, 1] - prepared.radar_y,
    )
    assert numpy.all(unknown_distance <= payload.coverage.max_range_m)


def test_unknown_boundaries_behind_sector_are_not_exported(tmp_path: Path) -> None:
    dem_path = tmp_path / "sector-dem.tif"
    min_height_path = tmp_path / "sector-minimum-visible-height.tif"
    nodata = -9999.0
    shape = (25, 25)
    transform = from_origin(-1_250, 1_250, 100, 100)
    dem = numpy.full(shape, 100, dtype=numpy.float32)
    min_visible_height = numpy.zeros(shape, dtype=numpy.float32)
    dem[:7, :7] = nodata
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
            "coverage": {
                "max_range_m": 1_000,
                "scan_mode": "sector",
                "azimuth_deg": 90,
                "beam_width_deg": 60,
            },
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

    assert volume.unknown_segments.shape == (0, 2, 3)


def test_los_threshold_surface_is_not_reported_as_terrain_contact(
    tmp_path: Path,
) -> None:
    dem_path = tmp_path / "flat-dem.tif"
    min_height_path = tmp_path / "positive-minimum-visible-height.tif"
    shape = (25, 25)
    transform = from_origin(-1_250, 1_250, 100, 100)
    dem = numpy.full(shape, 100, dtype=numpy.float32)
    min_visible_height = numpy.full(shape, 30, dtype=numpy.float32)

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
            nodata=-9999,
        ) as dataset:
            dataset.write(data, 1)

    payload = CoverageRequest.model_validate(
        {
            "dem_id": "dem_threshold_only",
            "radar": {"lon": 79.0, "lat": 31.5, "height_m": 0},
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
        dem_coverage_ratio=1,
        analysis_domain=numpy.ones(shape, dtype=bool),
    )

    volume = build_radar_visibility_volume(
        prepared,
        payload,
        min_height_path,
        grid_shape=(40, 40, 24),
    )

    assert volume.vertices.shape[0] > 0
    assert volume.terrain_segments.shape == (0, 2, 3)
