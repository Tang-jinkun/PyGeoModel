from dataclasses import astuple, dataclass, field
import re
import unicodedata

import numpy
import trimesh

from .exporter import MaterialSpec, SceneNode
from .frame import SceneFrame
from .grounding import TerrainAnchor
from .primitives import (
    annular_prism_boundary_mesh,
    annular_prism_mesh,
    dashed_vertical_leader_mesh,
)
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
GROUND_ANCHOR_MATERIAL = MaterialSpec(
    "unit_ground_anchor",
    (174, 181, 180, 255),
    shading="unlit",
    emissive_rgb=(87, 91, 90),
)
LEADER_MATERIAL = MaterialSpec(
    "unit_leader",
    (174, 181, 180, 255),
    shading="unlit",
    emissive_rgb=(87, 91, 90),
)
WARNING_ZONE_MATERIAL = MaterialSpec(
    "unit_warning_zone",
    (240, 142, 32, 20),
    shading="unlit",
    emissive_rgb=(120, 71, 16),
)
KILL_ZONE_MATERIAL = MaterialSpec(
    "unit_kill_zone",
    (218, 48, 55, 31),
    shading="unlit",
    emissive_rgb=(109, 24, 28),
)
WARNING_ZONE_BOUNDARY_MATERIAL = MaterialSpec(
    "unit_warning_zone_boundary",
    (240, 142, 32, 192),
    shading="unlit",
    emissive_rgb=(120, 71, 16),
)
KILL_ZONE_BOUNDARY_MATERIAL = MaterialSpec(
    "unit_kill_zone_boundary",
    (218, 48, 55, 192),
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
    terrain_anchor: TerrainAnchor | None = None
    display_profile: "UnitDisplayProfile | None" = None


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

    if (spec.terrain_anchor is None) != (spec.display_profile is None):
        raise ValueError("terrain_anchor and display_profile must be supplied together")
    if spec.terrain_anchor is not None and spec.display_profile is not None:
        return _build_grounded_unit_node(
            spec,
            normalized_id,
            index,
            frame,
            options,
            unit_type,
            status,
            heading,
        )

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


def _build_grounded_unit_node(
    spec: UnitSpec,
    normalized_id: str,
    index: int,
    frame: SceneFrame,
    options: UnitDisplayOptions,
    unit_type: str,
    status: str,
    heading: float,
) -> SceneNode:
    assert spec.terrain_anchor is not None
    assert spec.display_profile is not None
    anchor = spec.terrain_anchor
    profile = spec.display_profile
    ground_elevation = _finite_number(
        anchor.ground_elevation_amsl_m, "terrain_anchor.ground_elevation_amsl_m"
    )
    normal_enu = numpy.asarray(anchor.normal_enu, dtype=numpy.float64)
    if normal_enu.shape != (3,) or not numpy.isfinite(normal_enu).all():
        raise ValueError("terrain_anchor.normal_enu must contain three finite values")
    normal_length = float(numpy.linalg.norm(normal_enu))
    if normal_length == 0 or normal_enu[2] <= 0:
        raise ValueError("terrain_anchor.normal_enu must point upward")
    normal_enu /= normal_length
    normal_gltf = numpy.asarray(
        [normal_enu[0], normal_enu[2], -normal_enu[1]], dtype=numpy.float64
    )
    slope_transform = trimesh.geometry.align_vectors(
        [0.0, 1.0, 0.0], normal_gltf
    )
    heading_transform = trimesh.transformations.rotation_matrix(
        -numpy.deg2rad(heading), [0, 1, 0]
    )
    model_transform = slope_transform @ heading_transform
    clearance_m = 0.75
    translation = frame.to_gltf(
        (float(spec.position[0]), float(spec.position[1]), ground_elevation + clearance_m)
    )
    root_transform = trimesh.transformations.translation_matrix(translation)
    identity = {
        "unit_id": spec.unit_id,
        "unit_type": unit_type,
        "status": status,
        "display_scale_m": _finite_number(spec.display_scale_m, "display_scale_m"),
    }
    actual = _validated_dimensions(
        profile.actual_dimensions_m, "display_profile.actual_dimensions_m"
    )
    displayed = _validated_dimensions(
        profile.display_dimensions_m, "display_profile.display_dimensions_m"
    )
    exaggeration = _finite_number(
        profile.exaggeration, "display_profile.exaggeration"
    )
    symbol_scale = _finite_number(profile.symbol_scale_m, "symbol_scale_m")
    if exaggeration <= 0 or symbol_scale <= 0:
        raise ValueError("display_profile values must be positive and finite")
    vehicle_top_y = displayed.equipment_top * normal_gltf[1]
    symbol_gap_y = min(140.0, max(90.0, symbol_scale * 0.35))
    symbol_lower_y = vehicle_top_y + symbol_gap_y
    symbol_center_y = symbol_lower_y + symbol_scale * 0.26
    label_center_y = symbol_lower_y + symbol_scale * 0.65
    children: list[SceneNode] = [
        _prepare_component(
            SceneNode(
                name="ground_anchor",
                mesh=annular_prism_mesh(
                    center=numpy.zeros(3),
                    inner_radius_m=displayed.length * 0.16625,
                    outer_radius_m=displayed.length * 0.175,
                    bottom_y=-0.125,
                    top_y=0.125,
                ),
                material=GROUND_ANCHOR_MATERIAL,
                transform=slope_transform,
            ),
            normalized_id,
            "ground_anchor",
            identity,
        )
    ]
    if options.model:
        model = (
            _grounded_air_defense_model(displayed)
            if unit_type == "air_defense"
            else _unknown_model(spec.display_scale_m)
        )
        model.transform = model_transform
        children.append(_prepare_component(model, normalized_id, "model", identity))

    leader = SceneNode(
        name="leader",
        mesh=dashed_vertical_leader_mesh(
            bottom_y=vehicle_top_y,
            top_y=symbol_lower_y,
            radius_m=min(4.0, max(2.0, symbol_scale * 0.008)),
        ),
        material=LEADER_MATERIAL,
    )
    children.append(_prepare_component(leader, normalized_id, "leader", identity))
    if options.symbol:
        symbol = (
            crossed_air_defense_symbol_nodes(symbol_scale)
            if unit_type == "air_defense"
            else crossed_unknown_symbol_nodes(symbol_scale)
        )
        symbol.transform = trimesh.transformations.translation_matrix(
            [0, symbol_center_y, 0]
        )
        children.append(
            _prepare_component(symbol, normalized_id, "symbol_cross", identity)
        )
    if options.label:
        label = crossed_label_nodes(
            sanitize_short_label(spec.short_label, spec.unit_id, index), symbol_scale
        )
        label.transform = trimesh.transformations.translation_matrix(
            [0, label_center_y, 0]
        )
        children.append(_prepare_component(label, normalized_id, "label_cross", identity))
    if options.warning_zone and spec.warning_zone is not None:
        children.append(
            _zone_component(
                spec.warning_zone,
                ground_elevation + clearance_m,
                normalized_id,
                "warning_zone",
                WARNING_ZONE_MATERIAL,
                identity,
                display_ground_altitude_m=ground_elevation,
                include_boundary=True,
            )
        )
    if options.kill_zone and spec.kill_zone is not None:
        children.append(
            _zone_component(
                spec.kill_zone,
                ground_elevation + clearance_m,
                normalized_id,
                "kill_zone",
                KILL_ZONE_MATERIAL,
                identity,
                display_ground_altitude_m=ground_elevation,
                include_boundary=True,
            )
        )

    return SceneNode(
        name=f"unit_{normalized_id}",
        transform=root_transform,
        extras={
            "kind": "unit",
            **identity,
            "heading_deg": heading,
            "source": dict(spec.source),
            "actual_dimensions_m": _dimensions_metadata(actual),
            "display_dimensions_m": _dimensions_metadata(displayed),
            "display_exaggeration": exaggeration,
            "ground_elevation_amsl_m": ground_elevation,
            "terrain_normal": normal_enu.tolist(),
            "terrain_slope_deg": _finite_number(
                anchor.slope_deg, "terrain_anchor.slope_deg"
            ),
            "terrain_fit_rmse_m": _finite_number(
                anchor.fit_rmse_m, "terrain_anchor.fit_rmse_m"
            ),
            "terrain_max_residual_m": _finite_number(
                anchor.max_residual_m, "terrain_anchor.max_residual_m"
            ),
            "ground_clearance_m": clearance_m,
            "symbol_scale_m": symbol_scale,
        },
        children=children,
    )


def _vertical_cylinder_mesh(
    bottom_y: float,
    top_y: float,
    radius_m: float,
) -> trimesh.Trimesh:
    mesh = trimesh.creation.cylinder(
        radius=radius_m,
        height=top_y - bottom_y,
        sections=8,
    )
    mesh.apply_transform(
        trimesh.transformations.rotation_matrix(-numpy.pi / 2, [1, 0, 0])
    )
    mesh.apply_translation([0, (bottom_y + top_y) / 2, 0])
    return mesh


def _validated_dimensions(value: UnitDimensions, field_name: str) -> UnitDimensions:
    if not isinstance(value, UnitDimensions):
        raise ValueError(f"{field_name} must be a UnitDimensions")
    dimensions = UnitDimensions(
        *(_finite_number(component, field_name) for component in astuple(value))
    )
    if any(component <= 0 for component in astuple(dimensions)):
        raise ValueError(f"{field_name} must contain positive finite values")
    return dimensions


def _dimensions_metadata(dimensions: UnitDimensions) -> dict[str, float]:
    return {
        "length": dimensions.length,
        "width": dimensions.width,
        "chassis_height": dimensions.chassis_height,
        "equipment_top": dimensions.equipment_top,
    }


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
    _apply_component_extras(node, role, identity)
    return node


def _rename_tree(node: SceneNode, name: str) -> None:
    node.name = name
    for child in node.children:
        _rename_tree(child, f"{name}/{child.name}")


def _apply_component_extras(node: SceneNode, role: str, identity: dict) -> None:
    node.extras = {
        "kind": "unit_component",
        **node.extras,
        **identity,
        "role": role,
    }
    for child in node.children:
        _apply_component_extras(child, role, identity)


def _zone_component(
    zone: InfluenceZoneSpec,
    root_altitude_m: float,
    normalized_id: str,
    role: str,
    material: MaterialSpec,
    identity: dict,
    *,
    display_ground_altitude_m: float | None = None,
    include_boundary: bool = False,
) -> SceneNode:
    display_bottom = zone.min_altitude_amsl_m
    if display_ground_altitude_m is not None:
        display_bottom = max(display_bottom, display_ground_altitude_m)
    display_top = zone.max_altitude_amsl_m
    if display_top <= display_bottom:
        raise ValueError(f"{role} display maximum altitude must exceed display minimum altitude")
    fill = SceneNode(
        name="fill",
        mesh=annular_prism_mesh(
            center=numpy.zeros(3),
            inner_radius_m=zone.inner_radius_m,
            outer_radius_m=zone.outer_radius_m,
            bottom_y=display_bottom - root_altitude_m,
            top_y=display_top - root_altitude_m,
        ),
        material=material,
    )
    if not include_boundary:
        return _prepare_component(fill, normalized_id, role, identity)

    boundary_material = (
        WARNING_ZONE_BOUNDARY_MATERIAL
        if role == "warning_zone"
        else KILL_ZONE_BOUNDARY_MATERIAL
    )
    boundary = SceneNode(
        name="boundary",
        mesh=annular_prism_boundary_mesh(
            center=numpy.zeros(3),
            inner_radius_m=zone.inner_radius_m,
            outer_radius_m=zone.outer_radius_m,
            bottom_y=display_bottom - root_altitude_m,
            top_y=display_top - root_altitude_m,
            stroke_radius_m=min(8.0, max(2.0, zone.outer_radius_m * 0.001)),
        ),
        material=boundary_material,
    )
    component = _prepare_component(
        SceneNode(name=role, children=[fill, boundary]),
        normalized_id,
        role,
        identity,
    )
    component.extras.update(
        {
            "requested_min_altitude_amsl_m": zone.min_altitude_amsl_m,
            "requested_max_altitude_amsl_m": zone.max_altitude_amsl_m,
            "display_min_altitude_amsl_m": display_bottom,
            "display_max_altitude_amsl_m": display_top,
        }
    )
    return component


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


def _grounded_air_defense_model(dimensions: UnitDimensions) -> SceneNode:
    length = dimensions.length
    width = dimensions.width
    chassis_height = dimensions.chassis_height
    track_height = chassis_height * 0.38
    track_width = width * 0.24
    chassis_body_height = chassis_height - track_height
    chassis_center_y = track_height + chassis_body_height / 2
    cabin_height = chassis_height * 0.42
    launcher_height = chassis_height * 0.18
    mast_bottom_y = chassis_height + launcher_height
    panel_height = chassis_height * 0.2
    panel_center_y = dimensions.equipment_top - panel_height / 2

    return SceneNode(
        name="model",
        children=[
            SceneNode(
                name="chassis",
                mesh=_box_mesh(
                    [length * 0.84, chassis_body_height, width * 0.68],
                    [0, chassis_center_y, 0],
                ),
                material=BODY_MATERIAL,
            ),
            SceneNode(
                name="left_track",
                mesh=_box_mesh(
                    [length, track_height, track_width],
                    [0, track_height / 2, width / 2 - track_width / 2],
                ),
                material=BODY_DARK_MATERIAL,
            ),
            SceneNode(
                name="right_track",
                mesh=_box_mesh(
                    [length, track_height, track_width],
                    [0, track_height / 2, -width / 2 + track_width / 2],
                ),
                material=BODY_DARK_MATERIAL,
            ),
            SceneNode(
                name="cabin",
                mesh=_box_mesh(
                    [length * 0.24, cabin_height, width * 0.48],
                    [-length * 0.18, chassis_height + cabin_height / 2, 0],
                ),
                material=BODY_MATERIAL,
            ),
            SceneNode(
                name="launcher",
                mesh=_box_mesh(
                    [length * 0.48, launcher_height, width * 0.44],
                    [length * 0.16, chassis_height + launcher_height / 2, 0],
                ),
                material=BODY_DARK_MATERIAL,
            ),
            SceneNode(
                name="radar_mast",
                mesh=_vertical_cylinder_mesh(
                    mast_bottom_y,
                    panel_center_y,
                    max(0.5, width * 0.04),
                ),
                material=BODY_DARK_MATERIAL,
            ),
            SceneNode(
                name="radar_panel",
                mesh=_box_mesh(
                    [length * 0.3, panel_height, width * 0.12],
                    [length * 0.16, panel_center_y, 0],
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
