import json
import struct
from pathlib import Path

import numpy
import pytest
import trimesh

from app.scene3d import exporter
from app.scene3d.exporter import MaterialSpec, SceneNode, export_glb
from app.scene3d.primitives import marker_mesh


def glb_json(path: Path) -> dict:
    payload = path.read_bytes()
    assert payload[:4] == b"glTF"
    chunk_length, chunk_type = struct.unpack_from("<II", payload, 12)
    assert chunk_type == 0x4E4F534A
    return json.loads(payload[20 : 20 + chunk_length].decode("utf-8"))


def test_export_glb_keeps_node_names_materials_and_extras(tmp_path: Path) -> None:
    path = tmp_path / "scene.glb"
    export_glb(
        path,
        {
            "start": (
                marker_mesh(numpy.asarray([0, 10, 0]), 4),
                MaterialSpec("terminal", (230, 235, 240, 255)),
            )
        },
        scene_metadata={"schema_version": 1, "model_id": "air_corridor"},
        node_metadata={"start": {"kind": "terminal", "role": "start"}},
    )

    document = glb_json(path)
    assert document["asset"]["extras"]["scene3d"]["model_id"] == "air_corridor"
    node = next(item for item in document["nodes"] if item.get("name") == "start")
    assert node["extras"] == {"kind": "terminal", "role": "start"}
    loaded = trimesh.load(path, force="scene")
    assert "start" in loaded.graph.nodes_geometry


def test_export_glb_keeps_hierarchy_and_unlit_material(tmp_path: Path) -> None:
    path = tmp_path / "scene.glb"
    root = SceneNode(
        name="unit_ad_01",
        extras={"kind": "unit", "unit_id": "ad-01"},
        children=[
            SceneNode(
                name="unit_ad_01_symbol",
                mesh=marker_mesh(numpy.zeros(3), 4),
                material=MaterialSpec(
                    "symbol",
                    (220, 48, 64, 255),
                    shading="unlit",
                    emissive_rgb=(110, 24, 32),
                ),
                extras={"kind": "unit_component", "role": "symbol_cross"},
            )
        ],
    )

    export_glb(path, [root], scene_metadata={"schema_version": 1})

    document = glb_json(path)
    by_name = {node.get("name"): node for node in document["nodes"]}
    child_index = document["nodes"].index(by_name["unit_ad_01_symbol"])
    assert child_index in by_name["unit_ad_01"]["children"]
    assert by_name["unit_ad_01"]["extras"]["unit_id"] == "ad-01"
    assert document["extensionsUsed"] == ["KHR_materials_unlit"]
    assert "KHR_materials_unlit" not in document.get("extensionsRequired", [])
    material = next(item for item in document["materials"] if item["name"] == "symbol")
    assert material["extensions"]["KHR_materials_unlit"] == {}
    assert material["emissiveFactor"] == pytest.approx([110 / 255, 24 / 255, 32 / 255])


@pytest.mark.parametrize(
    ("nodes", "message"),
    [
        (
            [
                SceneNode(
                    name="unlit",
                    mesh=marker_mesh(numpy.zeros(3), 4),
                    material=MaterialSpec("unlit", (1, 2, 3, 255), shading="unlit"),
                )
            ],
            "Unlit material requires emissive_rgb: unlit",
        ),
        (
            [SceneNode(name="mesh", mesh=marker_mesh(numpy.zeros(3), 4))],
            "Scene mesh requires a material: mesh",
        ),
        ([SceneNode(name="group")], "Scene group requires children: group"),
        (
            [
                SceneNode(
                    name="same",
                    mesh=marker_mesh(numpy.zeros(3), 4),
                    material=MaterialSpec("first", (1, 2, 3, 255)),
                ),
                SceneNode(
                    name="same",
                    mesh=marker_mesh(numpy.zeros(3), 4),
                    material=MaterialSpec("second", (1, 2, 3, 255)),
                ),
            ],
            "Duplicate scene node name: same",
        ),
        (
            [
                SceneNode(
                    name="transform",
                    mesh=marker_mesh(numpy.zeros(3), 4),
                    material=MaterialSpec("material", (1, 2, 3, 255)),
                    transform=numpy.full((4, 4), numpy.nan),
                )
            ],
            "Invalid scene transform: transform",
        ),
    ],
)
def test_export_glb_rejects_invalid_scene_nodes(
    tmp_path: Path,
    nodes: list[SceneNode],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        export_glb(tmp_path / "scene.glb", nodes, scene_metadata={})


@pytest.mark.parametrize(
    ("node", "message"),
    [
        (SceneNode(name=""), "Scene node requires a non-empty name"),
        (
            SceneNode(
                name="material_only",
                material=MaterialSpec("material", (1, 2, 3, 255)),
            ),
            "Scene material requires a mesh: material_only",
        ),
        (
            SceneNode(
                name="empty",
                mesh=trimesh.Trimesh(),
                material=MaterialSpec("material", (1, 2, 3, 255)),
            ),
            "Invalid scene mesh: empty",
        ),
        (
            SceneNode(
                name="shape",
                mesh=marker_mesh(numpy.zeros(3), 4),
                material=MaterialSpec("material", (1, 2, 3, 255)),
                transform=numpy.eye(3),
            ),
            "Invalid scene transform: shape",
        ),
    ],
)
def test_export_glb_rejects_invalid_node_contracts(
    tmp_path: Path,
    node: SceneNode,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        export_glb(tmp_path / "scene.glb", [node], scene_metadata={})


@pytest.mark.parametrize(
    "material",
    [
        MaterialSpec("rgba_min", (0, 0, 0, 0)),
        MaterialSpec(
            "unlit_min",
            (0, 0, 0, 0),
            shading="unlit",
            emissive_rgb=(0, 0, 0),
        ),
        MaterialSpec(
            "unlit_max",
            (255, 255, 255, 255),
            shading="unlit",
            emissive_rgb=(255, 255, 255),
        ),
    ],
)
def test_export_glb_accepts_material_color_channel_boundaries(
    tmp_path: Path,
    material: MaterialSpec,
) -> None:
    export_glb(
        tmp_path / f"{material.name}.glb",
        [
            SceneNode(
                name="mesh",
                mesh=marker_mesh(numpy.zeros(3), 4),
                material=material,
            )
        ],
        scene_metadata={},
    )


@pytest.mark.parametrize(
    ("material", "message"),
    [
        (MaterialSpec("rgba", (-1, 0, 0, 255)), "Invalid rgba channel: rgba"),
        (MaterialSpec("rgba", (0, 256, 0, 255)), "Invalid rgba channel: rgba"),
        (MaterialSpec("rgba", (0, 0.5, 0, 255)), "Invalid rgba channel: rgba"),
        (
            MaterialSpec(
                "emissive",
                (0, 0, 0, 255),
                shading="unlit",
                emissive_rgb=(-1, 0, 0),
            ),
            "Invalid emissive_rgb channel: emissive",
        ),
        (
            MaterialSpec(
                "emissive",
                (0, 0, 0, 255),
                shading="unlit",
                emissive_rgb=(0, 256, 0),
            ),
            "Invalid emissive_rgb channel: emissive",
        ),
        (
            MaterialSpec(
                "emissive",
                (0, 0, 0, 255),
                shading="unlit",
                emissive_rgb=(0, 0.5, 0),
            ),
            "Invalid emissive_rgb channel: emissive",
        ),
    ],
)
def test_export_glb_rejects_invalid_material_color_channels(
    tmp_path: Path,
    material: MaterialSpec,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        export_glb(
            tmp_path / "scene.glb",
            [
                SceneNode(
                    name="mesh",
                    mesh=marker_mesh(numpy.zeros(3), 4),
                    material=material,
                )
            ],
            scene_metadata={},
        )


def test_export_glb_propagates_final_glb_reload_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_to_reload(*args: object, **kwargs: object) -> trimesh.Scene:
        raise ValueError("malformed finalized GLB")

    monkeypatch.setattr(trimesh, "load", fail_to_reload)

    with pytest.raises(ValueError, match="malformed finalized GLB"):
        export_glb(
            tmp_path / "scene.glb",
            [
                SceneNode(
                    name="mesh",
                    mesh=marker_mesh(numpy.zeros(3), 4),
                    material=MaterialSpec("material", (1, 2, 3, 255)),
                )
            ],
            scene_metadata={},
        )


def test_export_glb_rejects_missing_reloaded_mesh_node(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trimesh, "load", lambda *args, **kwargs: trimesh.Scene())

    with pytest.raises(
        ValueError,
        match=r"Exported GLB lost semantic scene nodes: \['mesh'\]",
    ):
        export_glb(
            tmp_path / "scene.glb",
            [
                SceneNode(
                    name="mesh",
                    mesh=marker_mesh(numpy.zeros(3), 4),
                    material=MaterialSpec("material", (1, 2, 3, 255)),
                )
            ],
            scene_metadata={},
        )


def test_export_glb_rejects_missing_serialized_hierarchy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_export_glb = trimesh.exchange.gltf.export_glb

    def export_without_children(*args: object, **kwargs: object) -> bytes:
        payload = original_export_glb(*args, **kwargs)
        version, chunks = exporter._parse_glb(payload)
        document = exporter.read_glb_document(payload)
        next(node for node in document["nodes"] if node["name"] == "root").pop(
            "children"
        )
        json_index = next(
            index for index, (kind, _chunk) in enumerate(chunks) if kind == exporter.JSON_CHUNK
        )
        encoded = json.dumps(document, separators=(",", ":")).encode("utf-8")
        chunks[json_index] = (exporter.JSON_CHUNK, encoded + b" " * ((-len(encoded)) % 4))
        assert version == 2
        return exporter._build_glb(chunks)

    monkeypatch.setattr(trimesh.exchange.gltf, "export_glb", export_without_children)
    nodes = [
        SceneNode(
            name="root",
            children=[
                SceneNode(
                    name="child",
                    mesh=marker_mesh(numpy.zeros(3), 4),
                    material=MaterialSpec("material", (1, 2, 3, 255)),
                )
            ],
        )
    ]

    with pytest.raises(ValueError, match="Exported GLB lost scene hierarchy: root -> child"):
        export_glb(tmp_path / "scene.glb", nodes, scene_metadata={})
