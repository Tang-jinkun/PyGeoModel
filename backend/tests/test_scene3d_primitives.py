import numpy
import pytest

import app.scene3d.primitives as primitives
from app.scene3d.primitives import annular_prism_mesh, ribbon_mesh, tube_mesh


def test_tube_and_ribbon_are_finite_bounded_meshes() -> None:
    points = numpy.asarray(
        [[0, 100, 0], [500, 120, -200], [1000, 160, -100]],
        dtype=float,
    )
    tube = tube_mesh(points, radius_m=12, sections=8)
    ribbon = ribbon_mesh(points, width_m=400)

    assert len(tube.vertices) > 0 and len(tube.faces) > 0
    assert len(ribbon.vertices) == 6 and len(ribbon.faces) == 4
    assert numpy.isfinite(tube.vertices).all()
    assert numpy.isfinite(ribbon.vertices).all()


def test_annular_prism_preserves_inner_gap_and_height() -> None:
    mesh = annular_prism_mesh(
        center=numpy.asarray([0, 0, 0], dtype=float),
        inner_radius_m=100,
        outer_radius_m=500,
        bottom_y=50,
        top_y=850,
        sections=24,
    )

    radii = numpy.hypot(mesh.vertices[:, 0], mesh.vertices[:, 2])
    assert radii.min() == pytest.approx(100)
    assert radii.max() == pytest.approx(500)
    assert mesh.bounds[:, 1].tolist() == pytest.approx([50, 850])


def test_primitives_reject_invalid_geometry() -> None:
    with pytest.raises(ValueError, match="at least two"):
        tube_mesh(numpy.asarray([[0, 0, 0]], dtype=float), radius_m=1)
    with pytest.raises(ValueError, match="outer radius"):
        annular_prism_mesh(numpy.zeros(3), 20, 10, 0, 100)


def test_dashed_vertical_leader_merges_four_dashes_from_seven_intervals() -> None:
    mesh = primitives.dashed_vertical_leader_mesh(
        bottom_y=40,
        top_y=110,
        radius_m=3,
    )

    assert len(numpy.unique(numpy.round(mesh.vertices[:, 1], decimals=9))) == 8
    assert mesh.bounds[:, 1] == pytest.approx([40, 110])
    assert numpy.hypot(mesh.vertices[:, 0], mesh.vertices[:, 2]).max() == pytest.approx(
        3
    )


def test_annular_prism_boundary_has_rings_and_four_vertical_strokes() -> None:
    mesh = primitives.annular_prism_boundary_mesh(
        center=numpy.zeros(3),
        inner_radius_m=0,
        outer_radius_m=500,
        bottom_y=50,
        top_y=850,
        stroke_radius_m=4,
        sections=24,
    )

    assert len(mesh.vertices) == 456
    assert mesh.bounds[:, 1] == pytest.approx([46, 854])
    assert numpy.hypot(mesh.vertices[:, 0], mesh.vertices[:, 2]).max() == pytest.approx(
        504
    )
