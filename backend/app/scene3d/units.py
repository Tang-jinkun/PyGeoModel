from dataclasses import astuple, dataclass, field
import re
import unicodedata

import numpy
import trimesh

from .exporter import MaterialSpec, SceneNode
from .frame import SceneFrame
from .primitives import annular_prism_mesh
from .tactical_glyphs import (
    crossed_air_defense_symbol_nodes,
    crossed_label_nodes,
    crossed_unknown_symbol_nodes,
    sanitize_short_label,
)


SUPPORTED_UNIT_TYPES = frozenset({"unknown", "air_defense"})
SUPPORTED_STATUSES = frozenset({"unknown", "active"})

BODY_MATERIAL = MaterialSpec("unit_body", (112, 119, 124, 255))
BODY_DARK_MATERIAL = MaterialSpec("unit_body_dark", (70, 76, 82, 255))
WARNING_ZONE_MATERIAL = MaterialSpec(
    "unit_warning_zone",
    (240, 142, 32, 64),
    shading="unlit",
    emissive_rgb=(120, 71, 16),
)
KILL_ZONE_MATERIAL = MaterialSpec(
    "unit_kill_zone",
    (218, 48, 55, 72),
    shading="unlit",
    emissive_rgb=(109, 24, 28),
)


@dataclass(frozen=True)
class InfluenceZoneSpec:
    inner_radius_m: float
    outer_radius_m: float
    min_altitude_amsl_m: float
    max_altitude_amsl_m: float


@dataclass(frozen=True)
class UnitSpec:
    unit_id: str
    position: tuple[float, float]
    altitude_amsl_m: float
    display_scale_m: float
    unit_type: str | None = None
    heading_deg: float | None = None
    status: str | None = None
    short_label: str | None = None
    warning_zone: InfluenceZoneSpec | None = None
    kill_zone: InfluenceZoneSpec | None = None
    source: dict = field(default_factory=dict)


@dataclass(frozen=True)
class UnitDisplayOptions:
    model: bool = True
    symbol: bool = True
    label: bool = True
    warning_zone: bool = True
    kill_zone: bool = True


@dataclass(frozen=True)
class UnitDimensions:
    length: float
    width: float
    chassis_height: float
    equipment_top: float


@dataclass(frozen=True)
class UnitDisplayProfile:
    actual_dimensions_m: UnitDimensions
    display_dimensions_m: UnitDimensions
    exaggeration: float
    symbol_scale_m: float


def derive_air_defense_display_profile(
    scene_extent_m: float,
) -> UnitDisplayProfile:
    exaggeration = min(15.0, max(10.0, scene_extent_m / 6000.0))
    actual = UnitDimensions(12.0, 3.2, 2.8, 7.5)
    displayed = UnitDimensions(
        *(value * exaggeration for value in astuple(actual))
    )
    symbol_scale = min(400.0, max(260.0, displayed.length * 2.2))
    return UnitDisplayProfile(actual, displayed, exaggeration, symbol_scale)


@dataclass(frozen=True)
class UnitOmission:
    unit_id: str
    reason: str


def build_unit_nodes(
    specs: list[UnitSpec],
    frame: SceneFrame,
    options: UnitDisplayOptions = UnitDisplayOptions(),
) -> tuple[list[SceneNode], list[UnitOmission]]:
    normalized_ids = _preflight_unit_ids(specs)
    if not options.model and not options.symbol:
        raise ValueError("Unit display requires a model or symbol")

    nodes: list[SceneNode] = []
    omissions: list[UnitOmission] = []
    for index, (spec, normalized_id) in enumerate(zip(specs, normalized_ids)):
        try:
            node = _build_unit_node(spec, normalized_id, index, frame, options)
            _validate_unit_geometry(node)
        except Exception as error:
            omissions.append(UnitOmission(str(spec.unit_id), str(error)))
        else:
            nodes.append(node)
    return nodes, omissions


def _preflight_unit_ids(specs: list[UnitSpec]) -> list[str]:
    normalized_ids: list[str] = []
    seen: set[str] = set()
    for spec in specs:
        normalized = _normalize_unit_id(spec.unit_id)
        if not normalized:
            raise ValueError("Unit ID is empty after normalization")
        if normalized in seen:
            raise ValueError(f"Duplicate normalized unit ID: {normalized}")
        seen.add(normalized)
        normalized_ids.append(normalized)
    return normalized_ids


def _normalize_unit_id(unit_id: str) -> str:
    if not isinstance(unit_id, str):
        raise ValueError("Unit ID must be a string")
    value = unicodedata.normalize("NFKC", unit_id).strip().casefold()
    value = re.sub(r"[^a-z0-9_-]+", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("_")


def _build_unit_node(
    spec: UnitSpec,
    normalized_id: str,
    index: int,
    frame: SceneFrame,
    options: UnitDisplayOptions,
) -> SceneNode:
    position = numpy.asarray(spec.position, dtype=numpy.float64)
    if position.shape != (2,) or not numpy.isfinite(position).all():
        raise ValueError("position must contain two finite coordinates")
    altitude = _finite_number(spec.altitude_amsl_m, "altitude_amsl_m")
    scale = _finite_number(spec.display_scale_m, "display_scale_m")
    if scale <= 0:
        raise ValueError("display_scale_m must be positive and finite")

    unit_type = "unknown" if spec.unit_type is None else spec.unit_type
    if unit_type not in SUPPORTED_UNIT_TYPES:
        raise ValueError(f"unit_type is unsupported: {unit_type}")
    status = "unknown" if spec.status is None else spec.status
    if status not in SUPPORTED_STATUSES:
        raise ValueError(f"status is unsupported: {status}")
    heading = (
        0.0
        if spec.heading_deg is None
        else _finite_number(spec.heading_deg, "heading_deg") % 360
    )
    if not isinstance(spec.source, dict):
        raise ValueError("source must be a dictionary")

    _validate_zone(spec.warning_zone, "warning_zone")
    _validate_zone(spec.kill_zone, "kill_zone")

    translation = frame.to_gltf(
        (float(position[0]), float(position[1]), altitude)
    )
    transform = trimesh.transformations.rotation_matrix(
        -numpy.deg2rad(heading),
        [0, 1, 0],
    )
    transform[:3, 3] = translation

    identity = {
        "unit_id": spec.unit_id,
        "unit_type": unit_type,
        "status": status,
        "display_scale_m": scale,
    }
    children: list[SceneNode] = []
    if options.model:
        model = (
            _air_defense_model(scale)
            if unit_type == "air_defense"
            else _unknown_model(scale)
        )
        children.append(
            _prepare_component(model, normalized_id, "model", identity)
        )
    if options.symbol:
        symbol = (
            crossed_air_defense_symbol_nodes(scale)
            if unit_type == "air_defense"
            else crossed_unknown_symbol_nodes(scale)
        )
        symbol.transform = trimesh.transformations.translation_matrix(
            [0, scale * 1.34, 0]
        )
        children.append(
            _prepare_component(symbol, normalized_id, "symbol_cross", identity)
        )
    if options.label:
        label = crossed_label_nodes(
            sanitize_short_label(spec.short_label, spec.unit_id, index),
            scale,
        )
        label.transform = trimesh.transformations.translation_matrix(
            [0, scale * 0.88, 0]
        )
        children.append(
            _prepare_component(label, normalized_id, "label_cross", identity)
        )
    if options.warning_zone and spec.warning_zone is not None:
        children.append(
            _zone_component(
                spec.warning_zone,
                altitude,
                normalized_id,
                "warning_zone",
                WARNING_ZONE_MATERIAL,
                identity,
            )
        )
    if options.kill_zone and spec.kill_zone is not None:
        children.append(
            _zone_component(
                spec.kill_zone,
                altitude,
                normalized_id,
                "kill_zone",
                KILL_ZONE_MATERIAL,
                identity,
            )
        )

    return SceneNode(
        name=f"unit_{normalized_id}",
        transform=transform,
        extras={
            "kind": "unit",
            **identity,
            "heading_deg": heading,
            "source": dict(spec.source),
        },
        children=children,
    )


def _finite_number(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not numpy.isscalar(value):
        raise ValueError(f"{field_name} must be finite")
    result = float(value)
    if not numpy.isfinite(result):
        raise ValueError(f"{field_name} must be finite")
    return result


def _validate_zone(zone: InfluenceZoneSpec | None, field_name: str) -> None:
    if zone is None:
        return
    if not isinstance(zone, InfluenceZoneSpec):
        raise ValueError(f"{field_name} must be an InfluenceZoneSpec")
    inner = _finite_number(zone.inner_radius_m, field_name)
    outer = _finite_number(zone.outer_radius_m, field_name)
    bottom = _finite_number(zone.min_altitude_amsl_m, field_name)
    top = _finite_number(zone.max_altitude_amsl_m, field_name)
    if inner < 0 or outer <= inner:
        raise ValueError(f"{field_name} outer radius must exceed inner radius")
    if top <= bottom:
        raise ValueError(f"{field_name} maximum altitude must exceed minimum altitude")


def _prepare_component(
    node: SceneNode,
    normalized_id: str,
    role: str,
    identity: dict,
) -> SceneNode:
    root_name = f"unit_{normalized_id}/{role}"
    _rename_tree(node, root_name)
    node.extras = {"kind": "unit_component", **identity, "role": role}
    return node


def _rename_tree(node: SceneNode, name: str) -> None:
    node.name = name
    for child in node.children:
        _rename_tree(child, f"{name}/{child.name}")


def _zone_component(
    zone: InfluenceZoneSpec,
    ground_altitude_m: float,
    normalized_id: str,
    role: str,
    material: MaterialSpec,
    identity: dict,
) -> SceneNode:
    mesh = annular_prism_mesh(
        center=numpy.zeros(3),
        inner_radius_m=zone.inner_radius_m,
        outer_radius_m=zone.outer_radius_m,
        bottom_y=zone.min_altitude_amsl_m - ground_altitude_m,
        top_y=zone.max_altitude_amsl_m - ground_altitude_m,
    )
    return SceneNode(
        name=f"unit_{normalized_id}/{role}",
        mesh=mesh,
        material=material,
        extras={"kind": "unit_component", **identity, "role": role},
    )


def _unknown_model(scale_m: float) -> SceneNode:
    return SceneNode(
        name="model",
        children=[
            SceneNode(
                name="body",
                mesh=_box_mesh(
                    [scale_m * 0.56, scale_m * 0.3, scale_m * 0.42],
                    [0, scale_m * 0.15, 0],
                ),
                material=BODY_MATERIAL,
            ),
            SceneNode(
                name="marker",
                mesh=_box_mesh(
                    [scale_m * 0.22, scale_m * 0.18, scale_m * 0.22],
                    [0, scale_m * 0.39, 0],
                ),
                material=BODY_DARK_MATERIAL,
            ),
        ],
    )


def _air_defense_model(scale_m: float) -> SceneNode:
    mast = trimesh.creation.cylinder(
        radius=scale_m * 0.035,
        height=scale_m * 0.32,
        sections=8,
    )
    mast.apply_transform(
        trimesh.transformations.rotation_matrix(-numpy.pi / 2, [1, 0, 0])
    )
    mast.apply_translation([0, scale_m * 0.43, 0])
    launcher = _box_mesh(
        [scale_m * 0.48, scale_m * 0.14, scale_m * 0.18],
        [0, scale_m * 0.31, -scale_m * 0.04],
    )
    launcher.apply_transform(
        trimesh.transformations.rotation_matrix(-numpy.pi / 12, [1, 0, 0])
    )
    return SceneNode(
        name="model",
        children=[
            SceneNode(
                name="chassis",
                mesh=_box_mesh(
                    [scale_m * 0.76, scale_m * 0.18, scale_m * 0.46],
                    [0, scale_m * 0.09, 0],
                ),
                material=BODY_MATERIAL,
            ),
            SceneNode(
                name="launcher",
                mesh=launcher,
                material=BODY_DARK_MATERIAL,
            ),
            SceneNode(name="radar_mast", mesh=mast, material=BODY_DARK_MATERIAL),
            SceneNode(
                name="radar_panel",
                mesh=_box_mesh(
                    [scale_m * 0.3, scale_m * 0.19, scale_m * 0.045],
                    [0, scale_m * 0.62, 0],
                ),
                material=BODY_MATERIAL,
            ),
        ],
    )


def _box_mesh(extents: list[float], center: list[float]) -> trimesh.Trimesh:
    mesh = trimesh.creation.box(extents=extents)
    mesh.apply_translation(center)
    return mesh


def _validate_unit_geometry(root: SceneNode) -> None:
    def validate(node: SceneNode) -> None:
        transform = numpy.asarray(node.transform)
        if transform.shape != (4, 4) or not numpy.isfinite(transform).all():
            raise ValueError(f"geometry has an invalid transform: {node.name}")
        if node.mesh is not None and (
            node.mesh.is_empty
            or len(node.mesh.faces) == 0
            or not numpy.isfinite(node.mesh.vertices).all()
        ):
            raise ValueError(f"geometry is invalid: {node.name}")
        if node.mesh is None and not node.children:
            raise ValueError(f"geometry group is empty: {node.name}")
        for child in node.children:
            validate(child)

    validate(root)
