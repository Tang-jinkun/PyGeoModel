import numpy
import pytest

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
