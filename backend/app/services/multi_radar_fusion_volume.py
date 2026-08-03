from dataclasses import dataclass, replace
from pathlib import Path
from typing import Sequence

import numpy
from rasterio.fill import fillnodata
import trimesh
from skimage import measure

from app.scene3d.exporter import MaterialSpec, SceneNode, export_glb
from app.scene3d.frame import SceneFrame
from app.scene3d.radar_volume import build_height_field_envelope_mesh
from app.services.coverage_model import (
    LOWEST_PLAUSIBLE_TERRAIN_ELEVATION_M,
    PROJECTED_DEM_NODATA,
)


UNION_MATERIAL = MaterialSpec("fusion_union_jade", (31, 138, 112, 72), shading="unlit", emissive_rgb=(18, 82, 66))
OVERLAP_MATERIAL = MaterialSpec("fusion_overlap_amber", (244, 176, 68, 184), shading="unlit", emissive_rgb=(160, 104, 24))
TRIPLE_MATERIAL = MaterialSpec("fusion_triple_amber", (255, 220, 148, 230), shading="unlit", emissive_rgb=(198, 144, 62))
COOPERATIVE_INTERSECTION_MATERIAL = MaterialSpec(
    "cooperative_common_detection_gold",
    (255, 190, 54, 96),
    shading="unlit",
    emissive_rgb=(255, 150, 30),
)


@dataclass(frozen=True)
class FusionHeightCounts:
    target_epsg: int
    transform: object
    heights_m: numpy.ndarray
    coverage_count: numpy.ndarray
    terrain_m: numpy.ndarray

    def __post_init__(self) -> None:
        if self.coverage_count.ndim != 3:
            raise ValueError("Fusion coverage count must have height, row, and column dimensions.")
        if self.coverage_count.shape[0] != len(self.heights_m):
            raise ValueError("Fusion height count does not match coverage-count bands.")
        if self.coverage_count.shape[1:] != self.terrain_m.shape:
            raise ValueError("Fusion terrain shape does not match coverage-count grid.")


@dataclass(frozen=True)
class FusionHeightEnvelope:
    target_epsg: int
    transform: object
    lower_m: numpy.ndarray
    upper_m: numpy.ndarray
    valid: numpy.ndarray

    def __post_init__(self) -> None:
        lower = numpy.asarray(self.lower_m)
        upper = numpy.asarray(self.upper_m)
        valid = numpy.asarray(self.valid, dtype=bool)
        if lower.ndim != 2 or upper.shape != lower.shape or valid.shape != lower.shape:
            raise ValueError("Fusion height envelopes require matching two-dimensional grids.")
        if not numpy.isfinite(lower[valid]).all() or not numpy.isfinite(upper[valid]).all():
            raise ValueError("Fusion height envelopes require finite valid bounds.")
        if (lower[valid] > upper[valid]).any():
            raise ValueError("Fusion height envelopes cannot have inverted valid bounds.")


def intersect_fusion_envelopes(
    envelopes: Sequence[FusionHeightEnvelope],
) -> FusionHeightEnvelope | None:
    if not envelopes:
        raise ValueError("Fusion envelope intersection requires at least one envelope.")
    reference = envelopes[0]
    for envelope in envelopes[1:]:
        if envelope.target_epsg != reference.target_epsg:
            raise ValueError("Fusion height envelopes must share one target CRS.")
        if envelope.lower_m.shape != reference.lower_m.shape:
            raise ValueError("Fusion height envelopes must share one grid shape.")
        if tuple(envelope.transform) != tuple(reference.transform):
            raise ValueError("Fusion height envelopes must share one grid transform.")

    valid = numpy.logical_and.reduce([numpy.asarray(envelope.valid, dtype=bool) for envelope in envelopes])
    lower = numpy.max(
        numpy.stack([numpy.where(envelope.valid, envelope.lower_m, -numpy.inf) for envelope in envelopes]),
        axis=0,
    )
    upper = numpy.min(
        numpy.stack([numpy.where(envelope.valid, envelope.upper_m, numpy.inf) for envelope in envelopes]),
        axis=0,
    )
    valid &= numpy.isfinite(lower) & numpy.isfinite(upper) & (lower <= upper)
    if not valid.any():
        return None
    return FusionHeightEnvelope(
        target_epsg=reference.target_epsg,
        transform=reference.transform,
        lower_m=numpy.where(valid, lower, 0.0),
        upper_m=numpy.where(valid, upper, 0.0),
        valid=valid,
    )


def accumulate_fusion_height_counts(masks) -> numpy.ndarray:
    items = [numpy.asarray(item, dtype=bool) for item in masks]
    if not items:
        raise ValueError("Fusion aggregation requires at least one station mask.")
    shape = items[0].shape
    counts = numpy.zeros(shape, dtype=numpy.uint16)
    for item in items:
        if item.shape != shape:
            raise ValueError("Fusion station masks must share one height grid.")
        counts += item.astype(numpy.uint16)
    return counts


def write_multi_radar_fusion_glb(path: Path, *, task_id: str, counts: FusionHeightCounts) -> dict:
    counts = replace(counts, terrain_m=_fill_invalid_terrain(counts.terrain_m))
    nodes: list[SceneNode] = []
    frame = _fusion_frame(counts)
    for threshold, name, material in (
        (1, "union", UNION_MATERIAL),
        (2, "overlap", OVERLAP_MATERIAL),
        (3, "triple_overlap", TRIPLE_MATERIAL),
    ):
        mesh = _coverage_mesh(counts, threshold, frame)
        if mesh is not None:
            nodes.append(SceneNode(
                name=f"multi_radar_fusion/{name}",
                mesh=mesh,
                material=material,
                extras={"kind": f"fusion_{name}", "minimum_coverage_count": threshold},
            ))
    if not nodes:
        raise ValueError("Fusion GLB requires at least one covered cell.")
    root = SceneNode(name="multi_radar_fusion", extras={"kind": "multi_radar_fusion"}, children=nodes)
    metadata = frame.metadata(f"{task_id}--fusion", "radar")
    metadata.update({
        "kind": "multi_radar_fusion",
        "fusion_height_count": int(len(counts.heights_m)),
        "fusion_heights_m": [float(height) for height in counts.heights_m],
        "coverage_thresholds": [1, 2, 3],
    })
    export_glb(path, [root], scene_metadata=metadata, include_normals=False)
    return metadata


def write_cooperative_intersection_glb(
    path: Path,
    *,
    task_id: str,
    envelope: FusionHeightEnvelope,
    station_count: int = 2,
) -> dict | None:
    if station_count < 2:
        raise ValueError("Cooperative intersection requires at least two stations.")
    if not envelope.valid.any():
        return None
    frame = _envelope_frame(envelope)
    mesh = _envelope_mesh(envelope, frame)
    root = SceneNode(
        name="cooperative_intersection",
        extras={"kind": "cooperative_intersection"},
        children=[
            SceneNode(
                name="cooperative_intersection/common_detection",
                mesh=mesh,
                material=COOPERATIVE_INTERSECTION_MATERIAL,
                extras={
                    "kind": "common_detection",
                    "minimum_coverage_count": station_count,
                },
            )
        ],
    )
    metadata = frame.metadata(f"{task_id}--intersection", "radar")
    metadata.update({
        "kind": "cooperative_intersection",
        "intersection_method": "shared_analytic_envelopes",
        "intersection_grid_shape": [int(value) for value in envelope.lower_m.shape],
        "intersection_valid_cell_count": int(numpy.count_nonzero(envelope.valid)),
        "intersection_station_count": station_count,
        "intersection_altitude_range_m": [
            float(envelope.lower_m[envelope.valid].min()),
            float(envelope.upper_m[envelope.valid].max()),
        ],
    })
    export_glb(path, [root], scene_metadata=metadata, include_normals=False)
    return metadata


def _fill_invalid_terrain(terrain_m: numpy.ndarray) -> numpy.ndarray:
    masked = numpy.ma.asarray(terrain_m, dtype=numpy.float32)
    terrain = numpy.asarray(masked.data, dtype=numpy.float32)
    invalid = (
        numpy.ma.getmaskarray(masked)
        | ~numpy.isfinite(terrain)
        | (terrain == numpy.float32(PROJECTED_DEM_NODATA))
        | (terrain < numpy.float32(LOWEST_PLAUSIBLE_TERRAIN_ELEVATION_M))
    )
    valid = ~invalid
    if not valid.any():
        raise ValueError("Fusion GLB requires at least one valid terrain elevation.")
    if valid.all():
        return terrain
    filled = fillnodata(
        numpy.where(valid, terrain, 0.0),
        mask=valid.astype(numpy.uint8),
        max_search_distance=float(max(terrain.shape) * 2),
    )
    if (
        not numpy.isfinite(filled).all()
        or (filled == numpy.float32(PROJECTED_DEM_NODATA)).any()
    ):
        raise ValueError("Fusion GLB terrain elevations could not be completed.")
    return numpy.asarray(filled, dtype=numpy.float32)


def _coverage_mesh(counts: FusionHeightCounts, threshold: int, frame: SceneFrame) -> trimesh.Trimesh | None:
    occupied = counts.coverage_count >= threshold
    if not occupied.any():
        return None
    padded = numpy.pad(occupied.astype(numpy.float32), 1)
    vertices, faces, _normals, _values = measure.marching_cubes(padded, level=0.5)
    vertices -= 1
    height_index = vertices[:, 0]
    row_index = vertices[:, 1]
    column_index = vertices[:, 2]
    row_sample = numpy.clip(numpy.rint(row_index).astype(int), 0, counts.terrain_m.shape[0] - 1)
    column_sample = numpy.clip(numpy.rint(column_index).astype(int), 0, counts.terrain_m.shape[1] - 1)
    terrain = counts.terrain_m[row_sample, column_sample]
    height = numpy.interp(height_index, numpy.arange(len(counts.heights_m)), counts.heights_m)
    x = counts.transform.c + (column_index + 0.5) * counts.transform.a
    y = counts.transform.f + (row_index + 0.5) * counts.transform.e
    projected = numpy.column_stack([x, y, terrain + height])
    local_vertices = numpy.asarray([frame.to_gltf(tuple(point)) for point in projected], dtype=numpy.float64)
    return trimesh.Trimesh(vertices=local_vertices, faces=faces, process=False)


def _envelope_mesh(envelope: FusionHeightEnvelope, frame: SceneFrame) -> trimesh.Trimesh:
    height, width = envelope.lower_m.shape
    x = envelope.transform.c + (numpy.arange(width, dtype=numpy.float64) + 0.5) * envelope.transform.a
    y = envelope.transform.f + (numpy.arange(height, dtype=numpy.float64) + 0.5) * envelope.transform.e
    x_grid, y_grid = numpy.meshgrid(x, y)
    vertices, faces = build_height_field_envelope_mesh(
        x_grid,
        y_grid,
        envelope.lower_m,
        envelope.upper_m,
        envelope.valid,
    )
    local_vertices = numpy.asarray(
        [frame.to_gltf(tuple(point)) for point in vertices],
        dtype=numpy.float64,
    )
    return trimesh.Trimesh(vertices=local_vertices, faces=faces, process=False)


def _fusion_frame(counts: FusionHeightCounts) -> SceneFrame:
    height, width = counts.terrain_m.shape
    points = []
    for row in (0, height - 1):
        for column in (0, width - 1):
            points.append((
                counts.transform.c + (column + 0.5) * counts.transform.a,
                counts.transform.f + (row + 0.5) * counts.transform.e,
                float(counts.terrain_m[row, column]),
            ))
            points.append((
                points[-1][0], points[-1][1],
                float(counts.terrain_m[row, column] + counts.heights_m[-1]),
            ))
    return SceneFrame.from_projected_points(counts.target_epsg, points, axes="z_up")


def _envelope_frame(envelope: FusionHeightEnvelope) -> SceneFrame:
    rows, columns = numpy.where(envelope.valid)
    if not len(rows):
        raise ValueError("Fusion envelope requires at least one valid cell.")
    x_coordinates = envelope.transform.c + (
        numpy.arange(envelope.lower_m.shape[1], dtype=numpy.float64) + 0.5
    ) * envelope.transform.a
    y_coordinates = envelope.transform.f + (
        numpy.arange(envelope.lower_m.shape[0], dtype=numpy.float64) + 0.5
    ) * envelope.transform.e
    x_min = float(x_coordinates[columns].min())
    x_max = float(x_coordinates[columns].max())
    y_min = float(y_coordinates[rows].min())
    y_max = float(y_coordinates[rows].max())
    valid_lower = envelope.lower_m[envelope.valid]
    valid_upper = envelope.upper_m[envelope.valid]
    lower = float(valid_lower.min())
    upper = float(valid_upper.max())
    points = [
        (x_min, y_min, lower),
        (x_min, y_min, upper),
        (x_min, y_max, lower),
        (x_min, y_max, upper),
        (x_max, y_min, lower),
        (x_max, y_min, upper),
        (x_max, y_max, lower),
        (x_max, y_max, upper),
    ]
    return SceneFrame.from_projected_points(envelope.target_epsg, points, axes="z_up")
