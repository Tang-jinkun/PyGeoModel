import json
import os
from pathlib import Path
import subprocess
import sys

import numpy

from app.scene3d.exporter import MaterialSpec, export_glb
from app.scene3d.primitives import marker_mesh


def test_inspect_glb_cli_reports_structure(tmp_path: Path) -> None:
    glb_path = tmp_path / "scene.glb"
    export_glb(
        glb_path,
        {
            "start": (
                marker_mesh(numpy.asarray([0, 10, 0]), 4),
                MaterialSpec("terminal", (230, 235, 240, 255)),
            )
        },
        scene_metadata={"schema_version": 1, "model_id": "air_corridor"},
        node_metadata={"start": {"kind": "terminal"}},
    )
    project_root = Path(__file__).resolve().parents[2]

    result = subprocess.run(
        [
            sys.executable,
            str(project_root / "scripts" / "inspect_glb.py"),
            str(glb_path),
            "--max-bytes",
            "50000000",
        ],
        cwd=project_root,
        env={**os.environ, "PYTHONPATH": str(project_root / "backend")},
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["valid"] is True
    assert payload["size_bytes"] == glb_path.stat().st_size
    assert payload["scene3d"]["model_id"] == "air_corridor"
    assert payload["nodes"] == ["start"]
    assert payload["geometry_count"] == 1
    assert payload["vertex_count"] > 0
    assert payload["face_count"] > 0
    assert len(payload["bounds"]) == 2
