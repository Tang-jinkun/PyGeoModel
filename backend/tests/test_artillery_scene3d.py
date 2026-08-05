from pathlib import Path

from app.scene3d.artillery import write_artillery_trajectory_glb
from app.scene3d.exporter import read_glb_document


def test_artillery_trajectory_glb_contains_semantic_nodes(tmp_path: Path) -> None:
    output = tmp_path / "artillery_trajectory.glb"
    metadata = write_artillery_trajectory_glb(
        output,
        task_id="artillery_task_demo",
        target_epsg=32644,
        battery=(500_000, 3_500_000, 100),
        target=(501_000, 3_500_000, 100),
        trajectory=[
            (500_000, 3_500_000, 100),
            (500_500, 3_500_000, 280),
            (501_000, 3_500_000, 100),
        ],
    )

    document = read_glb_document(output.read_bytes())
    node_names = {node.get("name") for node in document["nodes"]}

    assert metadata["model_id"] == "artillery"
    assert {"artillery_result/trajectory", "artillery_result/battery", "artillery_result/target"} <= node_names
