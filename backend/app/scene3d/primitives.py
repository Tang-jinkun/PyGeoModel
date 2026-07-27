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


def continuous_tube_mesh(
    points: Iterable[Iterable[float]],
    radius_m: float,
    sections: int = 8,
) -> trimesh.Trimesh:
    values = _points(points, 2)
    if radius_m <= 0 or sections < 3:
        raise ValueError("Tube radius must be positive and sections at least three")
    keep = numpy.concatenate(
        ([True], numpy.linalg.norm(numpy.diff(values, axis=0), axis=1) > 1e-9)
    )
    values = values[keep]
    if len(values) < 2:
        raise ValueError("Tube path requires at least two distinct points")

    tangents = numpy.empty_like(values)
    tangents[0] = values[1] - values[0]
    tangents[-1] = values[-1] - values[-2]
    if len(values) > 2:
        tangents[1:-1] = values[2:] - values[:-2]
    tangent_lengths = numpy.linalg.norm(tangents, axis=1)
    for index in numpy.flatnonzero(tangent_lengths <= 1e-9):
        tangents[index] = values[index + 1] - values[index]
    tangents /= numpy.linalg.norm(tangents, axis=1)[:, numpy.newaxis]

    # Parallel transport keeps adjacent cross sections aligned at shared joints.
    normals = numpy.empty_like(values)
    binormals = numpy.empty_like(values)
    axes = numpy.eye(3)
    for index, tangent in enumerate(tangents):
        if index == 0:
            axis = axes[numpy.argmin(numpy.abs(axes @ tangent))]
            normal = numpy.cross(tangent, axis)
        else:
            normal = normals[index - 1] - tangent * numpy.dot(
                normals[index - 1], tangent
            )
            if numpy.linalg.norm(normal) <= 1e-9:
                axis = axes[numpy.argmin(numpy.abs(axes @ tangent))]
                normal = numpy.cross(tangent, axis)
        normals[index] = normal / numpy.linalg.norm(normal)
        binormals[index] = numpy.cross(tangent, normals[index])

    angles = numpy.linspace(0, 2 * numpy.pi, sections, endpoint=False)
    rings = numpy.asarray(
        [
            point
            + radius_m
            * (
                numpy.cos(angle) * normal
                + numpy.sin(angle) * binormal
            )
            for point, normal, binormal in zip(values, normals, binormals)
            for angle in angles
        ]
    )
    vertices = numpy.vstack([rings, values[0], values[-1]])
    start_center = len(rings)
    end_center = start_center + 1
    faces: list[list[int]] = []
    for point_index in range(len(values) - 1):
        current = point_index * sections
        following = current + sections
        for section_index in range(sections):
            next_section = (section_index + 1) % sections
            faces.extend(
                [
                    [
                        current + section_index,
                        following + section_index,
                        current + next_section,
                    ],
                    [
                        current + next_section,
                        following + section_index,
                        following + next_section,
                    ],
                ]
            )
    last_ring = (len(values) - 1) * sections
    for section_index in range(sections):
        next_section = (section_index + 1) % sections
        faces.append([start_center, next_section, section_index])
        faces.append(
            [end_center, last_ring + section_index, last_ring + next_section]
        )
    return trimesh.Trimesh(
        vertices=vertices,
        faces=numpy.asarray(faces, dtype=numpy.int64),
        process=False,
    )


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


def dashed_vertical_leader_mesh(
    *,
    bottom_y: float,
    top_y: float,
    radius_m: float,
    sections: int = 8,
) -> trimesh.Trimesh:
    values = numpy.asarray([bottom_y, top_y, radius_m], dtype=numpy.float64)
    if not numpy.isfinite(values).all() or top_y <= bottom_y:
        raise ValueError("Dashed leader requires finite positive height")
    if radius_m <= 0 or sections < 6:
        raise ValueError("Dashed leader requires positive radius and at least six sections")

    interval_height = (top_y - bottom_y) / 7
    dashes = [
        _vertical_cylinder_mesh(
            bottom_y + interval * interval_height,
            bottom_y + (interval + 1) * interval_height,
            radius_m,
            sections,
        )
        for interval in (0, 2, 4, 6)
    ]
    return trimesh.util.concatenate(dashes)


def annular_prism_boundary_mesh(
    *,
    center: numpy.ndarray,
    inner_radius_m: float,
    outer_radius_m: float,
    bottom_y: float,
    top_y: float,
    stroke_radius_m: float,
    sections: int = 32,
) -> trimesh.Trimesh:
    center = numpy.asarray(center, dtype=numpy.float64)
    scalars = numpy.asarray(
        [inner_radius_m, outer_radius_m, bottom_y, top_y, stroke_radius_m],
        dtype=numpy.float64,
    )
    if (
        center.shape != (3,)
        or not numpy.isfinite(center).all()
        or not numpy.isfinite(scalars).all()
    ):
        raise ValueError("Annular prism boundary requires finite coordinates")
    if inner_radius_m < 0 or outer_radius_m <= inner_radius_m:
        raise ValueError("Annular prism boundary outer radius must exceed inner radius")
    if top_y <= bottom_y or stroke_radius_m <= 0 or sections < 8:
        raise ValueError("Annular prism boundary requires positive dimensions")

    rings = [
        _ring_mesh(center, outer_radius_m, y, stroke_radius_m, sections)
        for y in (bottom_y, top_y)
    ]
    if inner_radius_m > 0:
        rings.extend(
            _ring_mesh(center, inner_radius_m, y, stroke_radius_m, sections)
            for y in (bottom_y, top_y)
        )
    strokes = [
        _vertical_cylinder_mesh(
            bottom_y,
            top_y,
            stroke_radius_m,
            8,
            x=center[0] + outer_radius_m * numpy.cos(angle),
            z=center[2] + outer_radius_m * numpy.sin(angle),
        )
        for angle in numpy.linspace(0, 2 * numpy.pi, 4, endpoint=False)
    ]
    return trimesh.util.concatenate([*rings, *strokes])


def _ring_mesh(
    center: numpy.ndarray,
    radius_m: float,
    y: float,
    stroke_radius_m: float,
    sections: int,
    tube_sections: int = 8,
) -> trimesh.Trimesh:
    around = numpy.linspace(0, 2 * numpy.pi, sections, endpoint=False)
    cross = numpy.linspace(0, 2 * numpy.pi, tube_sections, endpoint=False)
    theta, phi = numpy.meshgrid(around, cross, indexing="ij")
    radial = radius_m + stroke_radius_m * numpy.cos(phi)
    vertices = numpy.column_stack(
        (
            center[0] + radial.ravel() * numpy.cos(theta).ravel(),
            y + stroke_radius_m * numpy.sin(phi).ravel(),
            center[2] + radial.ravel() * numpy.sin(theta).ravel(),
        )
    )
    faces = []
    for around_index in range(sections):
        next_around = (around_index + 1) % sections
        for cross_index in range(tube_sections):
            next_cross = (cross_index + 1) % tube_sections
            current = around_index * tube_sections + cross_index
            faces.extend(
                [
                    [current, next_around * tube_sections + cross_index, around_index * tube_sections + next_cross],
                    [
                        around_index * tube_sections + next_cross,
                        next_around * tube_sections + cross_index,
                        next_around * tube_sections + next_cross,
                    ],
                ]
            )
    return trimesh.Trimesh(
        vertices=vertices,
        faces=numpy.asarray(faces),
        process=False,
    )


def _vertical_cylinder_mesh(
    bottom_y: float,
    top_y: float,
    radius_m: float,
    sections: int,
    *,
    x: float = 0.0,
    z: float = 0.0,
) -> trimesh.Trimesh:
    mesh = trimesh.creation.cylinder(
        radius=radius_m,
        height=top_y - bottom_y,
        sections=sections,
    )
    mesh.apply_transform(
        trimesh.transformations.rotation_matrix(-numpy.pi / 2, [1, 0, 0])
    )
    mesh.apply_translation([x, (bottom_y + top_y) / 2, z])
    return mesh
