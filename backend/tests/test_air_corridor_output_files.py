from pathlib import Path

from app.services.air_corridor_output_files import (
    describe_air_corridor_output_file,
)


def test_scene_glb_descriptor_uses_standard_contract(tmp_path: Path) -> None:
    path = tmp_path / "air_corridor_result.glb"
    path.write_bytes(b"glTF")

    item = describe_air_corridor_output_file(
        "air_corridor_task_a",
        "scene_glb",
        path,
    )

    assert item.filename == "air_corridor_result.glb"
    assert item.media_type == "model/gltf-binary"
    assert item.label == "Air Corridor 3D Result GLB"
    assert item.download_url.endswith("/outputs/scene_glb")
