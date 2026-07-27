from dataclasses import dataclass, field
import json
from pathlib import Path
import struct
from typing import Literal

import numpy
import trimesh


JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942
MAX_GLB_BYTES = 50_000_000


@dataclass(frozen=True)
class MaterialSpec:
    name: str
    rgba: tuple[int, int, int, int]
    shading: Literal["pbr", "unlit"] = "pbr"
    emissive_rgb: tuple[int, int, int] | None = None
    double_sided: bool = True


@dataclass
class SceneNode:
    name: str
    mesh: trimesh.Trimesh | None = None
    material: MaterialSpec | None = None
    transform: numpy.ndarray = field(default_factory=lambda: numpy.eye(4))
    extras: dict = field(default_factory=dict)
    children: list["SceneNode"] = field(default_factory=list)


@dataclass(frozen=True)
class AnimationTrack:
    node_name: str
    path: Literal["rotation", "scale"]
    times: numpy.ndarray
    values: numpy.ndarray
    interpolation: Literal["LINEAR", "STEP"] = "LINEAR"


@dataclass(frozen=True)
class AnimationSpec:
    name: str
    tracks: list[AnimationTrack]


def export_glb(
    path: Path,
    meshes: dict[str, tuple[trimesh.Trimesh, MaterialSpec]] | list[SceneNode],
    *,
    scene_metadata: dict,
    node_metadata: dict[str, dict] | None = None,
    animations: list[AnimationSpec] | None = None,
    include_normals: bool = True,
) -> None:
    nodes = _normalize_scene_nodes(meshes, node_metadata)
    materials = _validate_scene_nodes(nodes)

    scene = trimesh.Scene()
    _add_scene_nodes(scene, nodes, parent=None)
    payload = trimesh.exchange.gltf.export_glb(
        scene,
        include_normals=include_normals,
    )
    payload = inject_glb_extras(
        payload,
        scene_metadata,
        _node_metadata(nodes),
        materials,
    )
    if animations:
        payload = inject_glb_animations(payload, animations)
    _ensure_glb_size_within_limit(payload)
    _validate_serialized_scene(payload, nodes)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    loaded = trimesh.load(path, force="scene")
    missing_mesh_nodes = _mesh_node_names(nodes) - set(loaded.graph.nodes_geometry)
    if missing_mesh_nodes:
        raise ValueError(
            f"Exported GLB lost semantic scene nodes: {sorted(missing_mesh_nodes)}"
        )


def _ensure_glb_size_within_limit(payload: bytes) -> None:
    size = len(payload)
    if size > MAX_GLB_BYTES:
        raise ValueError(
            f"GLB payload exceeds {MAX_GLB_BYTES}-byte hard limit: {size} bytes"
        )


def _normalize_scene_nodes(
    meshes: dict[str, tuple[trimesh.Trimesh, MaterialSpec]] | list[SceneNode],
    node_metadata: dict[str, dict] | None,
) -> list[SceneNode]:
    if isinstance(meshes, dict):
        metadata = node_metadata or {}
        return [
            SceneNode(
                name=name,
                mesh=mesh,
                material=material,
                extras=metadata.get(name, {}),
            )
            for name, (mesh, material) in meshes.items()
        ]
    if node_metadata is not None:
        raise ValueError("Hierarchical scene export does not accept node_metadata")
    return meshes


def _validate_scene_nodes(nodes: list[SceneNode]) -> dict[str, MaterialSpec]:
    if not nodes:
        raise ValueError("GLB scene requires at least one node")

    names: set[str] = set()
    materials: dict[str, MaterialSpec] = {}

    def validate(node: SceneNode) -> None:
        if not isinstance(node.name, str) or not node.name:
            raise ValueError("Scene node requires a non-empty name")
        if node.name in names:
            raise ValueError(f"Duplicate scene node name: {node.name}")
        names.add(node.name)

        transform = numpy.asarray(node.transform)
        if transform.shape != (4, 4) or not numpy.isfinite(transform).all():
            raise ValueError(f"Invalid scene transform: {node.name}")

        if node.mesh is None:
            if node.material is not None:
                raise ValueError(f"Scene material requires a mesh: {node.name}")
            if not node.children:
                raise ValueError(f"Scene group requires children: {node.name}")
        else:
            if node.material is None:
                raise ValueError(f"Scene mesh requires a material: {node.name}")
            if (
                node.mesh.is_empty
                or not numpy.isfinite(node.mesh.vertices).all()
                or len(node.mesh.faces) == 0
            ):
                raise ValueError(f"Invalid scene mesh: {node.name}")
            _validate_material(node.material)
            existing = materials.setdefault(node.material.name, node.material)
            if existing != node.material:
                raise ValueError(
                    f"Conflicting scene material specification: {node.material.name}"
                )

        for child in node.children:
            validate(child)

    for node in nodes:
        validate(node)
    return materials


def _validate_material(material: MaterialSpec) -> None:
    if material.shading not in {"pbr", "unlit"}:
        raise ValueError(f"Invalid material shading: {material.name}")
    _validate_color_channels(material.rgba, 4, "rgba", material.name)
    if material.emissive_rgb is not None:
        _validate_color_channels(
            material.emissive_rgb,
            3,
            "emissive_rgb",
            material.name,
        )
    if material.shading == "unlit" and material.emissive_rgb is None:
        raise ValueError(f"Unlit material requires emissive_rgb: {material.name}")


def _validate_color_channels(
    channels: tuple[int, ...],
    expected_count: int,
    label: str,
    material_name: str,
) -> None:
    if len(channels) != expected_count or any(
        isinstance(channel, bool)
        or not isinstance(channel, (int, numpy.integer))
        or not 0 <= channel <= 255
        for channel in channels
    ):
        raise ValueError(f"Invalid {label} channel: {material_name}")


def _add_scene_nodes(
    scene: trimesh.Scene,
    nodes: list[SceneNode],
    parent: str | None,
) -> None:
    for node in nodes:
        if node.mesh is None:
            scene.graph.update(
                frame_to=node.name,
                frame_from=parent,
                matrix=node.transform,
                metadata=node.extras,
            )
        else:
            node.mesh.visual = trimesh.visual.TextureVisuals(
                material=_pbr_material(node.material)
            )
            scene.add_geometry(
                node.mesh,
                node_name=node.name,
                geom_name=node.name,
                parent_node_name=parent,
                transform=node.transform,
                metadata=node.extras,
            )
        _add_scene_nodes(scene, node.children, parent=node.name)


def _pbr_material(material: MaterialSpec | None) -> trimesh.visual.material.PBRMaterial:
    assert material is not None
    alpha_mode = "BLEND" if material.rgba[3] < 255 else "OPAQUE"
    return trimesh.visual.material.PBRMaterial(
        name=material.name,
        baseColorFactor=numpy.asarray(material.rgba, dtype=numpy.uint8),
        metallicFactor=0.0,
        roughnessFactor=0.85,
        alphaMode=alpha_mode,
        doubleSided=material.double_sided,
    )


def _node_metadata(nodes: list[SceneNode]) -> dict[str, dict]:
    metadata: dict[str, dict] = {}

    def collect(node: SceneNode) -> None:
        metadata[node.name] = node.extras
        for child in node.children:
            collect(child)

    for node in nodes:
        collect(node)
    return metadata


def _mesh_node_names(nodes: list[SceneNode]) -> set[str]:
    names: set[str] = set()

    def collect(node: SceneNode) -> None:
        if node.mesh is not None:
            names.add(node.name)
        for child in node.children:
            collect(child)

    for node in nodes:
        collect(node)
    return names


def _validate_serialized_scene(payload: bytes, nodes: list[SceneNode]) -> None:
    document = read_glb_document(payload)
    by_name = {
        node.get("name"): node
        for node in document.get("nodes", [])
        if node.get("name")
    }
    expected_names = set(_node_metadata(nodes))
    missing = expected_names - set(by_name)
    if missing:
        raise ValueError(f"Exported GLB lost semantic scene nodes: {sorted(missing)}")

    indices = {node.get("name"): index for index, node in enumerate(document["nodes"])}

    def validate_children(node: SceneNode) -> None:
        for child in node.children:
            if indices[child.name] not in by_name[node.name].get("children", []):
                raise ValueError(
                    f"Exported GLB lost scene hierarchy: {node.name} -> {child.name}"
                )
            validate_children(child)

    for node in nodes:
        validate_children(node)


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
    materials: dict[str, MaterialSpec] | None = None,
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
    document.setdefault("asset", {}).setdefault("extras", {})["scene3d"] = scene_metadata
    nodes_by_name = {
        node.get("name"): node
        for node in document.get("nodes", [])
        if node.get("name")
    }
    missing = set(node_metadata) - set(nodes_by_name)
    if missing:
        raise ValueError(f"GLB metadata references missing nodes: {sorted(missing)}")
    for name, extras in node_metadata.items():
        nodes_by_name[name].setdefault("extras", {}).update(extras)
    _inject_unlit_materials(document, materials or {})
    encoded = json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    encoded += b" " * ((-len(encoded)) % 4)
    chunks[json_index] = (JSON_CHUNK, encoded)
    return _build_glb(chunks)


def inject_glb_animations(
    payload: bytes,
    animations: list[AnimationSpec],
) -> bytes:
    version, chunks = _parse_glb(payload)
    if version != 2:
        raise ValueError("Only GLB version 2 is supported")
    json_index = next(
        (index for index, (kind, _chunk) in enumerate(chunks) if kind == JSON_CHUNK),
        None,
    )
    bin_index = next(
        (index for index, (kind, _chunk) in enumerate(chunks) if kind == BIN_CHUNK),
        None,
    )
    if json_index is None or bin_index is None:
        raise ValueError("Animated GLB requires JSON and BIN chunks")

    document = json.loads(
        chunks[json_index][1].decode("utf-8").rstrip(" \t\r\n\x00")
    )
    nodes_by_name = {
        node.get("name"): (index, node)
        for index, node in enumerate(document.get("nodes", []))
        if node.get("name")
    }
    binary = bytearray(chunks[bin_index][1])
    buffer_views = document.setdefault("bufferViews", [])
    accessors = document.setdefault("accessors", [])
    serialized_animations = document.setdefault("animations", [])

    def append_accessor(values: numpy.ndarray, accessor_type: str, *, time: bool) -> int:
        while len(binary) % 4:
            binary.append(0)
        offset = len(binary)
        encoded = numpy.ascontiguousarray(values, dtype="<f4").tobytes()
        binary.extend(encoded)
        view_index = len(buffer_views)
        buffer_views.append(
            {
                "buffer": 0,
                "byteOffset": offset,
                "byteLength": len(encoded),
            }
        )
        accessor = {
            "bufferView": view_index,
            "componentType": 5126,
            "count": int(values.shape[0]),
            "type": accessor_type,
        }
        if time:
            accessor["min"] = [float(values.min())]
            accessor["max"] = [float(values.max())]
        accessors.append(accessor)
        return len(accessors) - 1

    for animation in animations:
        if not animation.name or not animation.tracks:
            raise ValueError("GLB animation requires a name and tracks")
        samplers = []
        channels = []
        for track in animation.tracks:
            target = nodes_by_name.get(track.node_name)
            if target is None:
                raise ValueError(
                    f"GLB animation references missing node: {track.node_name}"
                )
            times = numpy.asarray(track.times, dtype=numpy.float32)
            values = numpy.asarray(track.values, dtype=numpy.float32)
            component_count = 4 if track.path == "rotation" else 3
            if (
                times.ndim != 1
                or len(times) < 2
                or values.shape != (len(times), component_count)
                or not numpy.isfinite(times).all()
                or not numpy.isfinite(values).all()
                or times[0] < 0
                or numpy.any(numpy.diff(times) <= 0)
            ):
                raise ValueError(
                    f"Invalid GLB animation track: {animation.name}/{track.node_name}"
                )
            if track.interpolation not in {"LINEAR", "STEP"}:
                raise ValueError(
                    f"Unsupported GLB animation interpolation: {track.interpolation}"
                )
            node_index, node = target
            matrix = numpy.asarray(node.get("matrix", numpy.eye(4)), dtype=numpy.float64)
            if matrix.shape != (4, 4) or not numpy.allclose(matrix, numpy.eye(4)):
                raise ValueError(
                    f"Animated GLB node transform must be identity: {track.node_name}"
                )
            node.pop("matrix", None)
            node[track.path] = (
                [1.0, 1.0, 1.0]
                if track.path == "scale"
                else values[0].astype(float).tolist()
            )
            input_accessor = append_accessor(times, "SCALAR", time=True)
            output_accessor = append_accessor(
                values,
                "VEC4" if component_count == 4 else "VEC3",
                time=False,
            )
            sampler_index = len(samplers)
            samplers.append(
                {
                    "input": input_accessor,
                    "output": output_accessor,
                    "interpolation": track.interpolation,
                }
            )
            channels.append(
                {
                    "sampler": sampler_index,
                    "target": {"node": node_index, "path": track.path},
                }
            )
        serialized_animations.append(
            {"name": animation.name, "samplers": samplers, "channels": channels}
        )

    while len(binary) % 4:
        binary.append(0)
    if len(document.get("buffers", [])) != 1:
        raise ValueError("Animated GLB requires exactly one binary buffer")
    document["buffers"][0]["byteLength"] = len(binary)
    encoded = json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    encoded += b" " * ((-len(encoded)) % 4)
    chunks[json_index] = (JSON_CHUNK, encoded)
    chunks[bin_index] = (BIN_CHUNK, bytes(binary))
    return _build_glb(chunks)


def _inject_unlit_materials(document: dict, materials: dict[str, MaterialSpec]) -> None:
    unlit = {
        name: material
        for name, material in materials.items()
        if material.shading == "unlit"
    }
    if not unlit:
        return

    found: set[str] = set()
    for material in document.get("materials", []):
        specification = unlit.get(material.get("name"))
        if specification is None:
            continue
        found.add(specification.name)
        material.setdefault("extensions", {})["KHR_materials_unlit"] = {}
        assert specification.emissive_rgb is not None
        material["emissiveFactor"] = [
            channel / 255 for channel in specification.emissive_rgb
        ]
    missing = set(unlit) - found
    if missing:
        raise ValueError(f"Exported GLB lost scene materials: {sorted(missing)}")
    document["extensionsUsed"] = sorted(
        set(document.get("extensionsUsed", [])) | {"KHR_materials_unlit"}
    )


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
