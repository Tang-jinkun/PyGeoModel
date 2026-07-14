import json
import struct
from pathlib import Path

import numpy
import trimesh

from app.scene3d.exporter import MaterialSpec, export_glb
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
