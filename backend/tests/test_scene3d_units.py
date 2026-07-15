from collections.abc import Iterator
from dataclasses import replace
from math import pi
from pathlib import Path

import numpy
import pytest
import trimesh

from app.scene3d.exporter import SceneNode, export_glb, read_glb_document
from app.scene3d.frame import SceneFrame
from app.scene3d.tactical_glyphs import (
    ALLOWED_LABEL_CHARACTERS,
    GLYPH_MAP,
    crossed_air_defense_symbol_nodes,
    crossed_label_nodes,
    sanitize_short_label,
)
from app.scene3d.units import (
    InfluenceZoneSpec,
    UnitDisplayOptions,
    UnitOmission,
    UnitSpec,
    build_unit_nodes,
    derive_air_defense_display_profile,
)


def frame() -> SceneFrame:
    return SceneFrame(
        target_epsg=32648,
        origin_x=500_000,
        origin_y=3_500_000,
        origin_altitude_m=5_000,
        origin_longitude=105,
        origin_latitude=31.6,
    )


def unit(**changes: object) -> UnitSpec:
    values = {
        "unit_id": "ad-05",
        "unit_type": "air_defense",
        "position": (500_000, 3_500_000),
        "altitude_amsl_m": 5_900,
        "heading_deg": 45,
        "status": "active",
        "short_label": "AD-05",
        "display_scale_m": 800,
        "warning_zone": InfluenceZoneSpec(0, 7_750, 0, 6_600),
        "kill_zone": InfluenceZoneSpec(0, 4_500, 0, 6_600),
        "source": {"threat_level": "high", "max_range_m": 8_000},
    }
    values.update(changes)
    return UnitSpec(**values)


def walk_nodes(node: SceneNode) -> Iterator[SceneNode]:
    yield node
    for child in node.children:
        yield from walk_nodes(child)


def transformed_vertices(
    node: SceneNode,
    parent_transform: numpy.ndarray | None = None,
) -> Iterator[numpy.ndarray]:
    transform = (
        node.transform
        if parent_transform is None
        else parent_transform @ node.transform
    )
    if node.mesh is not None:
        yield trimesh.transform_points(node.mesh.vertices, transform)
    for child in node.children:
        yield from transformed_vertices(child, transform)


def bounds(node: SceneNode) -> numpy.ndarray:
    vertices = list(transformed_vertices(node))
    assert vertices
    combined = numpy.vstack(vertices)
    return numpy.asarray([combined.min(axis=0), combined.max(axis=0)])


def material_names(node: SceneNode) -> set[str]:
    return {
        item.material.name
        for item in walk_nodes(node)
        if item.material is not None
    }


def child_by_role(root: SceneNode, role: str) -> SceneNode:
    return next(child for child in root.children if child.extras["role"] == role)


def test_display_profile_uses_scene_extent_clamp() -> None:
    assert derive_air_defense_display_profile(60_000).exaggeration == 10
    assert derive_air_defense_display_profile(72_000).exaggeration == 12
    assert derive_air_defense_display_profile(120_000).exaggeration == 15
    assert derive_air_defense_display_profile(
        72_000
    ).display_dimensions_m.length == 144
    assert derive_air_defense_display_profile(72_000).symbol_scale_m == pytest.approx(
        316.8
    )


def test_air_defense_unit_binds_all_components_to_one_root() -> None:
    nodes, omissions = build_unit_nodes([unit()], frame())

    assert omissions == []
    root = nodes[0]
    assert root.name == "unit_ad-05"
    assert root.extras["display_scale_m"] == 800
    assert root.extras["source"] == {
        "threat_level": "high",
        "max_range_m": 8_000,
    }
    assert {child.extras["role"] for child in root.children} == {
        "model",
        "symbol_cross",
        "label_cross",
        "warning_zone",
        "kill_zone",
    }
    for child in root.children:
        assert child.extras.items() >= {
            "kind": "unit_component",
            "unit_id": "ad-05",
            "unit_type": "air_defense",
            "status": "active",
            "display_scale_m": 800,
        }.items()


def test_unit_ids_cannot_collide_with_hierarchy_component_names(
    tmp_path: Path,
) -> None:
    nodes, omissions = build_unit_nodes(
        [
            unit(unit_id="a", warning_zone=None, kill_zone=None),
            unit(
                unit_id="a_model",
                position=(501_000, 3_500_000),
                warning_zone=None,
                kill_zone=None,
            ),
        ],
        frame(),
    )

    assert omissions == []
    assert [node.name for node in nodes] == ["unit_a", "unit_a_model"]
    assert {child.name for child in nodes[0].children} == {
        "unit_a/model",
        "unit_a/symbol_cross",
        "unit_a/label_cross",
    }
    for root in nodes:
        for parent in walk_nodes(root):
            for child in parent.children:
                suffix = child.name.removeprefix(f"{parent.name}/")
                assert suffix != child.name
                assert "/" not in suffix

    path = tmp_path / "collision-proof-units.glb"
    export_glb(path, nodes, scene_metadata={"schema_version": 1})
    document = read_glb_document(path.read_bytes())
    names = [node["name"] for node in document["nodes"]]
    assert len(names) == len(set(names))


def test_missing_type_status_and_heading_use_explicit_defaults() -> None:
    nodes, omissions = build_unit_nodes(
        [
            unit(
                unit_id="unknown-1",
                unit_type=None,
                status=None,
                heading_deg=None,
                warning_zone=None,
                kill_zone=None,
            )
        ],
        frame(),
    )

    assert omissions == []
    root = nodes[0]
    assert root.extras.items() >= {
        "unit_type": "unknown",
        "status": "unknown",
        "heading_deg": 0,
    }.items()
    assert root.transform[:3, :3] == pytest.approx(numpy.eye(3))
    assert root.transform[:3, 3] == pytest.approx([0, 900, 0])


def test_heading_is_normalized_and_applied_clockwise_on_parent() -> None:
    nodes, omissions = build_unit_nodes([unit(heading_deg=405)], frame())

    assert omissions == []
    root = nodes[0]
    expected = trimesh.transformations.rotation_matrix(-pi / 4, [0, 1, 0])
    expected[:3, 3] = [0, 900, 0]
    assert root.extras["heading_deg"] == 45
    assert root.transform == pytest.approx(expected)
    assert all(numpy.allclose(child.transform[:3, 3], [0, 0, 0]) is False
               for child in root.children
               if child.extras["role"] in {"symbol_cross", "label_cross"})


@pytest.mark.parametrize("display_scale_m", [0, -1, numpy.nan, numpy.inf])
def test_invalid_display_scale_is_one_complete_omission(
    display_scale_m: float,
) -> None:
    nodes, omissions = build_unit_nodes(
        [unit(display_scale_m=display_scale_m)],
        frame(),
    )

    assert nodes == []
    assert len(omissions) == 1
    assert omissions[0].unit_id == "ad-05"
    assert "display_scale_m" in omissions[0].reason


def test_identity_bounds_exclude_model_defined_influence_zones() -> None:
    scale = 800
    nodes, omissions = build_unit_nodes([unit(display_scale_m=scale)], frame())

    assert omissions == []
    root = nodes[0]
    identity_vertices = [
        vertices
        for role in ("model", "symbol_cross", "label_cross")
        for vertices in transformed_vertices(child_by_role(root, role))
    ]
    identity = numpy.vstack(identity_vertices)
    identity_size = identity.max(axis=0) - identity.min(axis=0)
    assert identity_size[0] <= 1.25 * scale
    assert identity_size[2] <= 1.25 * scale
    assert identity_size[1] <= 2.0 * scale

    warning = bounds(child_by_role(root, "warning_zone"))
    warning_vertices = numpy.vstack(
        list(transformed_vertices(child_by_role(root, "warning_zone")))
    )
    warning_radii = numpy.hypot(warning_vertices[:, 0], warning_vertices[:, 2])
    assert warning_radii.min() == pytest.approx(0)
    assert warning_radii.max() == pytest.approx(7_750)
    assert warning[:, 1] == pytest.approx([-5_900, 700])

    kill_vertices = numpy.vstack(
        list(transformed_vertices(child_by_role(root, "kill_zone")))
    )
    kill_radii = numpy.hypot(kill_vertices[:, 0], kill_vertices[:, 2])
    assert kill_radii.min() == pytest.approx(0)
    assert kill_radii.max() == pytest.approx(4_500)
    assert bounds(child_by_role(root, "kill_zone"))[:, 1] == pytest.approx(
        [-5_900, 700]
    )


def test_crossed_air_defense_symbol_has_perpendicular_planes() -> None:
    symbol = crossed_air_defense_symbol_nodes(800)

    assert len(symbol.children) == 2
    normals = [
        child.transform[:3, :3] @ numpy.asarray([0, 0, 1], dtype=float)
        for child in symbol.children
    ]
    assert abs(float(numpy.dot(normals[0], normals[1]))) < 1e-12
    assert all(node.material is None or node.material.double_sided
               for node in walk_nodes(symbol))


def test_glyph_map_is_complete_fixed_five_by_seven_masks() -> None:
    assert set(GLYPH_MAP) == set(ALLOWED_LABEL_CHARACTERS)
    assert all(len(mask) == 7 for mask in GLYPH_MAP.values())
    assert all(len(row) == 5 for mask in GLYPH_MAP.values() for row in mask)
    assert all(set(row) <= {"0", "1"} for mask in GLYPH_MAP.values() for row in mask)


@pytest.mark.parametrize("character", sorted(ALLOWED_LABEL_CHARACTERS))
def test_every_allowed_label_character_produces_finite_geometry(
    character: str,
) -> None:
    label = crossed_label_nodes(character, 800)
    meshes = [node.mesh for node in walk_nodes(label) if node.mesh is not None]

    assert meshes
    assert all(len(mesh.faces) > 0 for mesh in meshes)
    assert all(numpy.isfinite(mesh.vertices).all() for mesh in meshes)


def test_crossed_label_accepts_eight_allowed_characters() -> None:
    label = crossed_label_nodes("ABCD-123", 800)
    meshes = [node.mesh for node in walk_nodes(label) if node.mesh is not None]

    assert meshes
    assert all(numpy.isfinite(mesh.vertices).all() for mesh in meshes)


def test_crossed_label_rejects_nine_allowed_characters() -> None:
    with pytest.raises(ValueError, match="1 through 8"):
        crossed_label_nodes("ABCDE-123", 800)


def test_crossed_label_rejects_unsupported_characters() -> None:
    with pytest.raises(ValueError, match="allowed uppercase characters"):
        crossed_label_nodes("AD.05", 800)


@pytest.mark.parametrize(
    ("value", "unit_id", "index", "expected"),
    [
        (" ad-05! ", "ignored", 0, "AD-05"),
        ("ABCDEFGHI", "unit-02", 1, "UNIT-02"),
        (None, "unit identifier too long", 0, "U01"),
        ("!!!", "***", 11, "U12"),
    ],
)
def test_short_label_sanitization_and_fallback_are_stable(
    value: str | None,
    unit_id: str,
    index: int,
    expected: str,
) -> None:
    assert sanitize_short_label(value, unit_id, index) == expected
    assert sanitize_short_label(value, unit_id, index) == expected


@pytest.mark.parametrize(
    ("field", "role"),
    [
        ("model", "model"),
        ("symbol", "symbol_cross"),
        ("label", "label_cross"),
        ("warning_zone", "warning_zone"),
        ("kill_zone", "kill_zone"),
    ],
)
def test_display_options_remove_role_and_its_unused_materials(
    field: str,
    role: str,
) -> None:
    full_nodes, _ = build_unit_nodes([unit()], frame())
    full_root = full_nodes[0]
    removed_materials = material_names(child_by_role(full_root, role))
    options = replace(UnitDisplayOptions(), **{field: False})

    nodes, omissions = build_unit_nodes([unit()], frame(), options)

    assert omissions == []
    root = nodes[0]
    assert role not in {child.extras["role"] for child in root.children}
    assert material_names(root).isdisjoint(removed_materials)


def test_display_options_require_model_or_symbol_identity() -> None:
    with pytest.raises(ValueError, match="model or symbol"):
        build_unit_nodes(
            [unit()],
            frame(),
            UnitDisplayOptions(model=False, symbol=False),
        )


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"position": (numpy.nan, 3_500_000)}, "position"),
        ({"altitude_amsl_m": numpy.inf}, "altitude_amsl_m"),
        ({"heading_deg": numpy.nan}, "heading_deg"),
        ({"unit_type": "frigate"}, "unit_type"),
        ({"unit_type": ""}, "unit_type"),
        ({"status": "invented"}, "status"),
        ({"status": ""}, "status"),
        ({"warning_zone": {}}, "warning_zone"),
        (
            {"warning_zone": InfluenceZoneSpec(100, 50, 0, 1_000)},
            "warning_zone",
        ),
        (
            {"kill_zone": InfluenceZoneSpec(0, 50, 1_000, 1_000)},
            "kill_zone",
        ),
        (
            {"kill_zone": InfluenceZoneSpec(0, numpy.inf, 0, 1_000)},
            "kill_zone",
        ),
    ],
)
def test_invalid_unit_data_returns_one_omission_and_no_partial_root(
    changes: dict[str, object],
    reason: str,
) -> None:
    nodes, omissions = build_unit_nodes([unit(**changes)], frame())

    assert nodes == []
    assert len(omissions) == 1
    assert omissions[0].unit_id == "ad-05"
    assert reason in omissions[0].reason


def test_geometry_failure_returns_one_omission_and_no_partial_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_geometry(_scale_m: float) -> SceneNode:
        raise RuntimeError("glyph geometry failed")

    monkeypatch.setattr(
        "app.scene3d.units.crossed_air_defense_symbol_nodes",
        fail_geometry,
    )

    nodes, omissions = build_unit_nodes([unit()], frame())

    assert nodes == []
    assert omissions == [UnitOmission("ad-05", "glyph geometry failed")]


class TrackingFrame:
    def __init__(self) -> None:
        self.calls = 0

    def to_gltf(self, _point: tuple[float, float, float]) -> numpy.ndarray:
        self.calls += 1
        return numpy.zeros(3)


@pytest.mark.parametrize(
    "specs",
    [
        [unit(unit_id="   ")],
        [unit(unit_id="AD 05"), unit(unit_id="ad_05")],
    ],
)
def test_invalid_scene_identity_raises_during_preflight(
    specs: list[UnitSpec],
) -> None:
    tracking_frame = TrackingFrame()

    with pytest.raises(ValueError, match="[Uu]nit ID|normalized unit ID"):
        build_unit_nodes(specs, tracking_frame)

    assert tracking_frame.calls == 0
