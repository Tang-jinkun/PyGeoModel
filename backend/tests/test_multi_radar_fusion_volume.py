from pathlib import Path

import numpy
from rasterio.transform import from_origin

from app.scene3d.exporter import read_glb_document
from app.services.multi_radar_fusion_volume import (
    FusionHeightCounts,
    accumulate_fusion_height_counts,
    write_cooperative_intersection_glb,
    write_multi_radar_fusion_glb,
)


def test_fusion_height_counts_preserve_overlap_per_height() -> None:
    counts = accumulate_fusion_height_counts([
        numpy.array([[[True, False]], [[False, True]]]),
        numpy.array([[[True, True]], [[False, True]]]),
    ])

    assert counts.tolist() == [[[2, 1]], [[0, 2]]]


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


def test_cooperative_intersection_glb_contains_only_common_detection_mesh(tmp_path: Path) -> None:
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
    path = tmp_path / "cooperative_intersection.glb"

    metadata = write_cooperative_intersection_glb(path, task_id="multi_task_test", counts=counts)

    document = read_glb_document(path.read_bytes())
    names = {node.get("name") for node in document["nodes"]}
    material = document["materials"][0]["pbrMetallicRoughness"]["baseColorFactor"]
    assert metadata is not None
    assert metadata["kind"] == "cooperative_intersection"
    assert "cooperative_intersection/common_detection" in names
    assert not {name for name in names if name and ("union" in name or "triple" in name)}
    assert material[0] > 0.95
    assert material[1] > 0.6
    assert material[3] > 0.8


def test_cooperative_intersection_glb_returns_none_without_common_detection(tmp_path: Path) -> None:
    counts = FusionHeightCounts(
        target_epsg=32644,
        transform=from_origin(400_000, 3_500_000, 100, 100),
        heights_m=numpy.array([0, 200], dtype=numpy.float32),
        coverage_count=numpy.ones((2, 2, 2), dtype=numpy.uint16),
        terrain_m=numpy.zeros((2, 2), dtype=numpy.float32),
    )

    metadata = write_cooperative_intersection_glb(
        tmp_path / "cooperative_intersection.glb", task_id="multi_task_test", counts=counts
    )

    assert metadata is None
