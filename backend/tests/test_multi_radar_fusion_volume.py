from pathlib import Path

import numpy
import pytest
from rasterio.transform import from_origin
import trimesh

from app.scene3d.exporter import read_glb_document
from app.services.coverage_model import PROJECTED_DEM_NODATA
from app.services.multi_radar_fusion_volume import (
    FusionHeightEnvelope,
    FusionHeightCounts,
    accumulate_fusion_height_counts,
    intersect_fusion_envelopes,
    write_cooperative_intersection_glb,
    write_multi_radar_fusion_glb,
)


def _glb_vertices(path: Path) -> numpy.ndarray:
    scene = trimesh.load(path, force="scene")
    return numpy.vstack([geometry.vertices for geometry in scene.geometry.values()])


def test_fusion_height_counts_preserve_overlap_per_height() -> None:
    counts = accumulate_fusion_height_counts([
        numpy.array([[[True, False]], [[False, True]]]),
        numpy.array([[[True, True]], [[False, True]]]),
    ])

    assert counts.tolist() == [[[2, 1]], [[0, 2]]]


def test_intersect_fusion_envelopes_keeps_only_common_vertical_interval() -> None:
    transform = from_origin(400_000, 3_500_000, 100, 100)
    first = FusionHeightEnvelope(
        target_epsg=32644,
        transform=transform,
        lower_m=numpy.array([[100, 200], [300, 400]], dtype=numpy.float32),
        upper_m=numpy.array([[900, 800], [700, 600]], dtype=numpy.float32),
        valid=numpy.ones((2, 2), dtype=bool),
    )
    second = FusionHeightEnvelope(
        target_epsg=32644,
        transform=transform,
        lower_m=numpy.array([[500, 100], [800, 450]], dtype=numpy.float32),
        upper_m=numpy.array([[1_000, 500], [900, 550]], dtype=numpy.float32),
        valid=numpy.ones((2, 2), dtype=bool),
    )

    result = intersect_fusion_envelopes([first, second])

    assert result is not None
    numpy.testing.assert_array_equal(result.lower_m, [[500, 200], [0, 450]])
    numpy.testing.assert_array_equal(result.upper_m, [[900, 500], [0, 550]])
    numpy.testing.assert_array_equal(result.valid, [[True, True], [False, True]])


def test_intersect_fusion_envelopes_returns_none_when_vertical_ranges_do_not_overlap() -> None:
    transform = from_origin(400_000, 3_500_000, 100, 100)
    envelopes = [
        FusionHeightEnvelope(
            target_epsg=32644,
            transform=transform,
            lower_m=numpy.zeros((1, 1), dtype=numpy.float32),
            upper_m=numpy.full((1, 1), 100, dtype=numpy.float32),
            valid=numpy.ones((1, 1), dtype=bool),
        ),
        FusionHeightEnvelope(
            target_epsg=32644,
            transform=transform,
            lower_m=numpy.full((1, 1), 200, dtype=numpy.float32),
            upper_m=numpy.full((1, 1), 300, dtype=numpy.float32),
            valid=numpy.ones((1, 1), dtype=bool),
        ),
    ]

    assert intersect_fusion_envelopes(envelopes) is None


def test_fusion_glb_contains_union_and_overlap_meshes(tmp_path: Path) -> None:
    counts = FusionHeightCounts(
        target_epsg=32644,
        transform=from_origin(400_000, 3_500_000, 100, 100),
        heights_m=numpy.array([0, 200, 500], dtype=numpy.float32),
        coverage_count=numpy.array([
            [[1, 1, 0], [1, 2, 0], [0, 0, 0]],
            [[1, 2, 0], [1, 2, 0], [0, 0, 0]],
            [[0, 2, 0], [0, 3, 0], [0, 0, 0]],
        ], dtype=numpy.uint16),
        terrain_m=numpy.zeros((3, 3), dtype=numpy.float32),
    )
    path = tmp_path / "fusion_scene.glb"

    metadata = write_multi_radar_fusion_glb(path, task_id="multi_task_test", counts=counts)

    document = read_glb_document(path.read_bytes())
    names = {node.get("name") for node in document["nodes"]}
    assert path.stat().st_size > 0
    assert {"multi_radar_fusion/union", "multi_radar_fusion/overlap"} <= names
    assert metadata["fusion_height_count"] == 3


def test_fusion_glb_fills_non_finite_terrain_samples(tmp_path: Path) -> None:
    counts = FusionHeightCounts(
        target_epsg=32644,
        transform=from_origin(400_000, 3_500_000, 100, 100),
        heights_m=numpy.array([0, 200, 500], dtype=numpy.float32),
        coverage_count=numpy.ones((3, 3, 3), dtype=numpy.uint16),
        terrain_m=numpy.array([
            [1200, 1200, 1200],
            [1200, numpy.nan, 1200],
            [1200, 1200, 1200],
        ], dtype=numpy.float32),
    )

    metadata = write_multi_radar_fusion_glb(
        tmp_path / "fusion_scene.glb", task_id="multi_task_nan_terrain", counts=counts
    )

    assert metadata["kind"] == "multi_radar_fusion"


def test_fusion_glb_fills_projected_dem_nodata_sentinel(tmp_path: Path) -> None:
    counts = FusionHeightCounts(
        target_epsg=32644,
        transform=from_origin(400_000, 3_500_000, 100, 100),
        heights_m=numpy.array([0, 200, 500], dtype=numpy.float32),
        coverage_count=numpy.ones((3, 3, 3), dtype=numpy.uint16),
        terrain_m=numpy.array([
            [PROJECTED_DEM_NODATA, 1200, 1200],
            [1200, 1200, 1200],
            [1200, 1200, 1200],
        ], dtype=numpy.float32),
    )
    path = tmp_path / "fusion_scene.glb"

    metadata = write_multi_radar_fusion_glb(
        path, task_id="multi_task_nodata_terrain", counts=counts
    )

    assert metadata["origin"]["altitude_amsl_m"] == 1200
    assert numpy.abs(_glb_vertices(path)).max() < 10_000


def test_fusion_glb_fills_interpolated_nodata_artifacts(tmp_path: Path) -> None:
    counts = FusionHeightCounts(
        target_epsg=32644,
        transform=from_origin(400_000, 3_500_000, 100, 100),
        heights_m=numpy.array([0, 200, 500], dtype=numpy.float32),
        coverage_count=numpy.ones((3, 3, 3), dtype=numpy.uint16),
        terrain_m=numpy.array([
            [-2.2394891524064644e38, 1200, 1200],
            [1200, 1200, 1200],
            [1200, 1200, 1200],
        ], dtype=numpy.float32),
    )
    path = tmp_path / "fusion_scene.glb"

    write_multi_radar_fusion_glb(
        path, task_id="multi_task_interpolated_nodata", counts=counts
    )

    assert numpy.abs(_glb_vertices(path)).max() < 10_000


def test_fusion_glb_fills_implausibly_low_terrain(tmp_path: Path) -> None:
    counts = FusionHeightCounts(
        target_epsg=32644,
        transform=from_origin(400_000, 3_500_000, 100, 100),
        heights_m=numpy.array([0, 200, 500], dtype=numpy.float32),
        coverage_count=numpy.ones((3, 3, 3), dtype=numpy.uint16),
        terrain_m=numpy.array([
            [-100_000, 1200, 1200],
            [1200, 1200, 1200],
            [1200, 1200, 1200],
        ], dtype=numpy.float32),
    )
    path = tmp_path / "fusion_scene.glb"

    write_multi_radar_fusion_glb(
        path, task_id="multi_task_low_terrain", counts=counts
    )

    assert numpy.abs(_glb_vertices(path)).max() < 10_000


def test_cooperative_intersection_glb_contains_only_common_detection_mesh(tmp_path: Path) -> None:
    envelope = FusionHeightEnvelope(
        target_epsg=32644,
        transform=from_origin(400_000, 3_500_000, 100, 100),
        lower_m=numpy.zeros((3, 3), dtype=numpy.float32),
        upper_m=numpy.full((3, 3), 500, dtype=numpy.float32),
        valid=numpy.array([
            [True, True, False],
            [True, True, False],
            [False, False, False],
        ]),
    )
    path = tmp_path / "cooperative_intersection.glb"

    metadata = write_cooperative_intersection_glb(path, task_id="multi_task_test", envelope=envelope)

    document = read_glb_document(path.read_bytes())
    names = {node.get("name") for node in document["nodes"]}
    material = document["materials"][0]["pbrMetallicRoughness"]["baseColorFactor"]
    assert metadata is not None
    assert metadata["kind"] == "cooperative_intersection"
    assert "cooperative_intersection/common_detection" in names
    assert not {name for name in names if name and ("union" in name or "triple" in name)}
    assert material[0] > 0.95
    assert material[1] > 0.6
    assert 0.3 < material[3] < 0.5
    assert numpy.ptp(_glb_vertices(path)[:, 2]) > 400


def test_cooperative_intersection_glb_rejects_empty_envelope(tmp_path: Path) -> None:
    envelope = FusionHeightEnvelope(
        target_epsg=32644,
        transform=from_origin(400_000, 3_500_000, 100, 100),
        lower_m=numpy.zeros((2, 2), dtype=numpy.float32),
        upper_m=numpy.zeros((2, 2), dtype=numpy.float32),
        valid=numpy.zeros((2, 2), dtype=bool),
    )
    path = tmp_path / "cooperative_intersection.glb"

    assert write_cooperative_intersection_glb(path, task_id="multi_task_empty", envelope=envelope) is None


def test_fusion_glb_rejects_terrain_without_valid_samples(tmp_path: Path) -> None:
    counts = FusionHeightCounts(
        target_epsg=32644,
        transform=from_origin(400_000, 3_500_000, 100, 100),
        heights_m=numpy.array([0, 200], dtype=numpy.float32),
        coverage_count=numpy.ones((2, 2, 2), dtype=numpy.uint16),
        terrain_m=numpy.full((2, 2), PROJECTED_DEM_NODATA, dtype=numpy.float32),
    )

    with pytest.raises(ValueError, match="valid terrain elevation"):
        write_multi_radar_fusion_glb(
            tmp_path / "fusion_scene.glb", task_id="multi_task_invalid_terrain", counts=counts
        )
