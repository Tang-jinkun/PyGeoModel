import numpy
import trimesh

from .exporter import MaterialSpec, SceneNode


ALLOWED_LABEL_CHARACTERS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
)

GLYPH_MAP: dict[str, tuple[str, ...]] = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00010", "00010", "00010", "10010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    "_": ("00000", "00000", "00000", "00000", "00000", "00000", "11111"),
}

assert set(GLYPH_MAP) == set(ALLOWED_LABEL_CHARACTERS)


SYMBOL_BACKPLATE_MATERIAL = MaterialSpec(
    "tactical_symbol_backplate",
    (236, 238, 232, 255),
    shading="unlit",
    emissive_rgb=(118, 119, 116),
)
THREAT_SYMBOL_MATERIAL = MaterialSpec(
    "tactical_symbol_threat",
    (218, 48, 55, 255),
    shading="unlit",
    emissive_rgb=(109, 24, 28),
)
UNKNOWN_SYMBOL_MATERIAL = MaterialSpec(
    "tactical_symbol_unknown",
    (62, 68, 74, 255),
    shading="unlit",
    emissive_rgb=(31, 34, 37),
)
LABEL_OUTLINE_MATERIAL = MaterialSpec(
    "tactical_label_outline",
    (24, 28, 32, 255),
    shading="unlit",
    emissive_rgb=(12, 14, 16),
)
LABEL_FOREGROUND_MATERIAL = MaterialSpec(
    "tactical_label_foreground",
    (245, 247, 242, 255),
    shading="unlit",
    emissive_rgb=(123, 124, 121),
)


def sanitize_short_label(value: str | None, unit_id: str, index: int) -> str:
    for candidate in (value, unit_id):
        filtered = "".join(
            character
            for character in (candidate or "").upper()
            if character in ALLOWED_LABEL_CHARACTERS
        )
        if 1 <= len(filtered) <= 8:
            return filtered
    return f"U{index + 1:02d}"


def crossed_label_nodes(label: str, scale_m: float) -> SceneNode:
    _validate_scale(scale_m)
    if not label or any(
        character not in ALLOWED_LABEL_CHARACTERS for character in label
    ):
        raise ValueError("Label requires allowed uppercase characters")

    return SceneNode(
        name="label_cross",
        children=[
            _label_face(label, scale_m, "face_0", 0.0),
            _label_face(label, scale_m, "face_90", numpy.pi / 2),
        ],
    )


def crossed_air_defense_symbol_nodes(scale_m: float) -> SceneNode:
    _validate_scale(scale_m)
    return SceneNode(
        name="symbol_cross",
        children=[
            _symbol_face(scale_m, "face_0", 0.0, threat=True),
            _symbol_face(scale_m, "face_90", numpy.pi / 2, threat=True),
        ],
    )


def crossed_unknown_symbol_nodes(scale_m: float) -> SceneNode:
    _validate_scale(scale_m)
    return SceneNode(
        name="symbol_cross",
        children=[
            _symbol_face(scale_m, "face_0", 0.0, threat=False),
            _symbol_face(scale_m, "face_90", numpy.pi / 2, threat=False),
        ],
    )


def _validate_scale(scale_m: float) -> None:
    if (
        isinstance(scale_m, bool)
        or not numpy.isscalar(scale_m)
        or not numpy.isfinite(scale_m)
        or scale_m <= 0
    ):
        raise ValueError("Glyph scale_m must be positive and finite")


def _label_face(
    label: str,
    scale_m: float,
    name: str,
    angle: float,
) -> SceneNode:
    transform = trimesh.transformations.rotation_matrix(angle, [0, 1, 0])
    return SceneNode(
        name=name,
        transform=transform,
        children=[
            SceneNode(
                name="outline",
                mesh=_label_mesh(label, scale_m, cell_ratio=0.019, depth_ratio=0.018),
                material=LABEL_OUTLINE_MATERIAL,
            ),
            SceneNode(
                name="foreground",
                mesh=_label_mesh(
                    label,
                    scale_m,
                    cell_ratio=0.015,
                    depth_ratio=0.012,
                    front_offset_ratio=0.016,
                ),
                material=LABEL_FOREGROUND_MATERIAL,
            ),
        ],
    )


def _label_mesh(
    label: str,
    scale_m: float,
    *,
    cell_ratio: float,
    depth_ratio: float,
    front_offset_ratio: float = 0.0,
) -> trimesh.Trimesh:
    pitch = scale_m * 0.02
    character_pitch = pitch * 6
    total_width = pitch * (5 * len(label) + max(0, len(label) - 1))
    total_height = pitch * 7
    cells: list[trimesh.Trimesh] = []
    for character_index, character in enumerate(label):
        for row, mask_row in enumerate(GLYPH_MAP[character]):
            for column, occupied in enumerate(mask_row):
                if occupied == "0":
                    continue
                x = (
                    character_index * character_pitch
                    + (column + 0.5) * pitch
                    - total_width / 2
                )
                y = total_height / 2 - (row + 0.5) * pitch
                cell = trimesh.creation.box(
                    extents=[
                        scale_m * cell_ratio,
                        scale_m * cell_ratio,
                        scale_m * depth_ratio,
                    ]
                )
                cell.apply_translation([x, y, scale_m * front_offset_ratio])
                cells.append(cell)
    if not cells:
        raise ValueError("Label produced no geometry")
    return trimesh.util.concatenate(cells)


def _symbol_face(
    scale_m: float,
    name: str,
    angle: float,
    *,
    threat: bool,
) -> SceneNode:
    transform = trimesh.transformations.rotation_matrix(angle, [0, 1, 0])
    accent_material = THREAT_SYMBOL_MATERIAL if threat else UNKNOWN_SYMBOL_MATERIAL
    accent_name = "threat_border_glyph" if threat else "unknown_border_glyph"
    return SceneNode(
        name=name,
        transform=transform,
        children=[
            SceneNode(
                name="backplate",
                mesh=trimesh.creation.box(
                    extents=[scale_m * 0.9, scale_m * 0.52, scale_m * 0.025]
                ),
                material=SYMBOL_BACKPLATE_MATERIAL,
            ),
            SceneNode(
                name=accent_name,
                mesh=_symbol_accent_mesh(scale_m, threat=threat),
                material=accent_material,
            ),
        ],
    )


def _symbol_accent_mesh(scale_m: float, *, threat: bool) -> trimesh.Trimesh:
    width = scale_m * 0.9
    height = scale_m * 0.52
    stroke = scale_m * 0.035
    depth = scale_m * 0.018
    z = scale_m * 0.022
    pieces = [
        _box([width, stroke, depth], [0, height / 2 - stroke / 2, z]),
        _box([width, stroke, depth], [0, -height / 2 + stroke / 2, z]),
        _box([stroke, height, depth], [-width / 2 + stroke / 2, 0, z]),
        _box([stroke, height, depth], [width / 2 - stroke / 2, 0, z]),
    ]
    if threat:
        pieces.extend(
            [
                _box([stroke, height * 0.55, depth], [0, -height * 0.03, z]),
                _box([width * 0.46, stroke, depth], [0, -height * 0.03, z]),
                _rotated_box(
                    [width * 0.28, stroke, depth],
                    [-width * 0.11, height * 0.12, z],
                    numpy.pi / 4,
                ),
                _rotated_box(
                    [width * 0.28, stroke, depth],
                    [width * 0.11, height * 0.12, z],
                    -numpy.pi / 4,
                ),
            ]
        )
    else:
        pieces.extend(
            [
                _rotated_box([width * 0.42, stroke, depth], [0, 0, z], numpy.pi / 4),
                _rotated_box([width * 0.42, stroke, depth], [0, 0, z], -numpy.pi / 4),
            ]
        )
    return trimesh.util.concatenate(pieces)


def _box(extents: list[float], center: list[float]) -> trimesh.Trimesh:
    mesh = trimesh.creation.box(extents=extents)
    mesh.apply_translation(center)
    return mesh


def _rotated_box(
    extents: list[float],
    center: list[float],
    angle: float,
) -> trimesh.Trimesh:
    mesh = trimesh.creation.box(extents=extents)
    mesh.apply_transform(trimesh.transformations.rotation_matrix(angle, [0, 0, 1]))
    mesh.apply_translation(center)
    return mesh
