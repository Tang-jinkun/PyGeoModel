from dataclasses import dataclass
import json
from pathlib import Path
import struct

import numpy
import trimesh


JSON_CHUNK = 0x4E4F534A


@dataclass(frozen=True)
class MaterialSpec:
    name: str
    rgba: tuple[int, int, int, int]


def export_glb(
    path: Path,
    meshes: dict[str, tuple[trimesh.Trimesh, MaterialSpec]],
    *,
    scene_metadata: dict,
    node_metadata: dict[str, dict],
) -> None:
    if not meshes:
        raise ValueError("GLB scene requires at least one mesh")
    scene = trimesh.Scene()
    for name, (mesh, material) in meshes.items():
        if (
            mesh.is_empty
            or not numpy.isfinite(mesh.vertices).all()
            or len(mesh.faces) == 0
        ):
            raise ValueError(f"Invalid scene mesh: {name}")
        alpha_mode = "BLEND" if material.rgba[3] < 255 else "OPAQUE"
        mesh.visual = trimesh.visual.TextureVisuals(
            material=trimesh.visual.material.PBRMaterial(
                name=material.name,
                baseColorFactor=numpy.asarray(material.rgba, dtype=numpy.uint8),
                metallicFactor=0.0,
                roughnessFactor=0.85,
                alphaMode=alpha_mode,
                doubleSided=True,
            )
        )
        scene.add_geometry(mesh, node_name=name, geom_name=name)
    payload = trimesh.exchange.gltf.export_glb(scene, include_normals=True)
    payload = inject_glb_extras(payload, scene_metadata, node_metadata)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    loaded = trimesh.load(path, force="scene")
    if set(meshes) - set(loaded.graph.nodes_geometry):
        raise ValueError("Exported GLB lost semantic scene nodes")


def read_glb_document(payload: bytes) -> dict:
    _version, chunks = _parse_glb(payload)
    for chunk_type, chunk in chunks:
        if chunk_type == JSON_CHUNK:
            return json.loads(chunk.decode("utf-8").rstrip(" \t\r\n\x00"))
    raise ValueError("GLB does not contain a JSON chunk")


def inject_glb_extras(
    payload: bytes,
    scene_metadata: dict,
    node_metadata: dict[str, dict],
) -> bytes:
    version, chunks = _parse_glb(payload)
    if version != 2:
        raise ValueError("Only GLB version 2 is supported")
    json_index = next(
        (index for index, (kind, _chunk) in enumerate(chunks) if kind == JSON_CHUNK),
        None,
    )
    if json_index is None:
        raise ValueError("GLB does not contain a JSON chunk")
    document = json.loads(
        chunks[json_index][1].decode("utf-8").rstrip(" \t\r\n\x00")
    )
    document.setdefault("asset", {}).setdefault("extras", {})[
        "scene3d"
    ] = scene_metadata
    nodes_by_name = {
        node.get("name"): node
        for node in document.get("nodes", [])
        if node.get("name")
    }
    missing = set(node_metadata) - set(nodes_by_name)
    if missing:
        raise ValueError(f"GLB metadata references missing nodes: {sorted(missing)}")
    for name, extras in node_metadata.items():
        nodes_by_name[name]["extras"] = extras
    encoded = json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    encoded += b" " * ((-len(encoded)) % 4)
    chunks[json_index] = (JSON_CHUNK, encoded)
    return _build_glb(chunks)


def _parse_glb(payload: bytes) -> tuple[int, list[tuple[int, bytes]]]:
    if len(payload) < 12:
        raise ValueError("GLB header is truncated")
    magic, version, total_length = struct.unpack_from("<4sII", payload, 0)
    if magic != b"glTF" or total_length != len(payload):
        raise ValueError("Invalid GLB header")
    chunks: list[tuple[int, bytes]] = []
    offset = 12
    while offset < len(payload):
        if offset + 8 > len(payload):
            raise ValueError("GLB chunk header is truncated")
        length, chunk_type = struct.unpack_from("<II", payload, offset)
        start = offset + 8
        end = start + length
        if end > len(payload):
            raise ValueError("GLB chunk is truncated")
        chunks.append((chunk_type, payload[start:end]))
        offset = end
    if offset != len(payload):
        raise ValueError("GLB chunk lengths do not match file length")
    return version, chunks


def _build_glb(chunks: list[tuple[int, bytes]]) -> bytes:
    body = b"".join(
        struct.pack("<II", len(chunk), chunk_type) + chunk
        for chunk_type, chunk in chunks
    )
    return struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body
