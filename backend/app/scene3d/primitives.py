from collections.abc import Iterable

import numpy
import trimesh


def _points(values: Iterable[Iterable[float]], minimum: int) -> numpy.ndarray:
    points = numpy.asarray(list(values), dtype=numpy.float64)
    if points.ndim != 2 or points.shape[1] != 3 or len(points) < minimum:
        label = "two" if minimum == 2 else str(minimum)
        raise ValueError(f"Geometry requires at least {label} points")
    if not numpy.isfinite(points).all():
        raise ValueError("Geometry contains non-finite coordinates")
    return points


def marker_mesh(point: numpy.ndarray, radius_m: float) -> trimesh.Trimesh:
    point = numpy.asarray(point, dtype=numpy.float64)
    if point.shape != (3,) or not numpy.isfinite(point).all():
        raise ValueError("Marker requires one finite point")
    if radius_m <= 0:
        raise ValueError("Marker radius must be positive")
    mesh = trimesh.creation.icosphere(subdivisions=1, radius=radius_m)
    mesh.apply_translation(point)
    return mesh


def tube_mesh(
    points: Iterable[Iterable[float]],
    radius_m: float,
    sections: int = 8,
) -> trimesh.Trimesh:
    values = _points(points, 2)
    if radius_m <= 0 or sections < 6:
        raise ValueError("Tube radius must be positive and sections at least six")
    pieces = [marker_mesh(point, radius_m) for point in values]
    for left, right in zip(values, values[1:]):
        vector = right - left
        length = float(numpy.linalg.norm(vector))
        if length == 0:
            continue
        cylinder = trimesh.creation.cylinder(
            radius=radius_m,
            height=length,
            sections=sections,
        )
        transform = trimesh.geometry.align_vectors([0, 0, 1], vector / length)
        transform[:3, 3] = (left + right) / 2
        cylinder.apply_transform(transform)
        pieces.append(cylinder)
    return trimesh.util.concatenate(pieces)


def ribbon_mesh(
    points: Iterable[Iterable[float]],
    width_m: float,
) -> trimesh.Trimesh:
    values = _points(points, 2)
    if width_m <= 0:
        raise ValueError("Ribbon width must be positive")
    offsets = []
    previous = numpy.asarray([0.0, 0.0, 1.0])
    for index in range(len(values)):
        before = values[max(0, index - 1)]
        after = values[min(len(values) - 1, index + 1)]
        tangent = after - before
        horizontal = numpy.asarray([tangent[0], 0.0, tangent[2]])
        norm = float(numpy.linalg.norm(horizontal))
        if norm > 0:
            previous = numpy.asarray([-horizontal[2], 0.0, horizontal[0]]) / norm
        offsets.append(previous * width_m / 2)
    vertices = numpy.asarray(
        [
            value + side * offset
            for value, offset in zip(values, offsets)
            for side in (-1, 1)
        ]
    )
    faces = []
    for index in range(len(values) - 1):
        left = index * 2
        faces.extend(
            [
                [left, left + 2, left + 1],
                [left + 1, left + 2, left + 3],
            ]
        )
    return trimesh.Trimesh(
        vertices=vertices,
        faces=numpy.asarray(faces),
        process=False,
    )


def annular_prism_mesh(
    center: numpy.ndarray,
    inner_radius_m: float,
    outer_radius_m: float,
    bottom_y: float,
    top_y: float,
    sections: int = 32,
) -> trimesh.Trimesh:
    center = numpy.asarray(center, dtype=numpy.float64)
    scalars = numpy.asarray(
        [inner_radius_m, outer_radius_m, bottom_y, top_y],
        dtype=numpy.float64,
    )
    if (
        center.shape != (3,)
        or not numpy.isfinite(center).all()
        or not numpy.isfinite(scalars).all()
    ):
        raise ValueError("Annular prism requires finite coordinates")
    if inner_radius_m < 0 or outer_radius_m <= inner_radius_m:
        raise ValueError("Annular prism outer radius must exceed inner radius")
    if top_y <= bottom_y or sections < 8:
        raise ValueError(
            "Annular prism requires positive height and at least eight sections"
        )
    if inner_radius_m == 0:
        mesh = trimesh.creation.cylinder(
            radius=outer_radius_m,
            height=top_y - bottom_y,
            sections=sections,
        )
        mesh.apply_transform(
            trimesh.transformations.rotation_matrix(-numpy.pi / 2, [1, 0, 0])
        )
        mesh.apply_translation(
            [center[0], (bottom_y + top_y) / 2, center[2]]
        )
        return mesh

    angles = numpy.linspace(0, 2 * numpy.pi, sections, endpoint=False)
    outer_x = center[0] + numpy.cos(angles) * outer_radius_m
    outer_z = center[2] + numpy.sin(angles) * outer_radius_m
    inner_x = center[0] + numpy.cos(angles) * inner_radius_m
    inner_z = center[2] + numpy.sin(angles) * inner_radius_m
    rings = [
        numpy.column_stack(
            [outer_x, numpy.full(sections, bottom_y), outer_z]
        ),
        numpy.column_stack([outer_x, numpy.full(sections, top_y), outer_z]),
        numpy.column_stack(
            [inner_x, numpy.full(sections, bottom_y), inner_z]
        ),
        numpy.column_stack([inner_x, numpy.full(sections, top_y), inner_z]),
    ]
    vertices = numpy.vstack(rings)
    faces = []
    for index in range(sections):
        nxt = (index + 1) % sections
        outer_bottom, outer_next = index, nxt
        outer_top, outer_top_next = sections + index, sections + nxt
        inner_bottom, inner_next = 2 * sections + index, 2 * sections + nxt
        inner_top, inner_top_next = 3 * sections + index, 3 * sections + nxt
        faces.extend(
            [
                [outer_bottom, outer_next, outer_top],
                [outer_next, outer_top_next, outer_top],
                [inner_bottom, inner_top, inner_next],
                [inner_next, inner_top, inner_top_next],
                [outer_top, outer_top_next, inner_top],
                [outer_top_next, inner_top_next, inner_top],
                [outer_bottom, inner_bottom, outer_next],
                [outer_next, inner_bottom, inner_next],
            ]
        )
    return trimesh.Trimesh(
        vertices=vertices,
        faces=numpy.asarray(faces),
        process=False,
    )
