import argparse
import json
import sys
from pathlib import Path

import numpy
import trimesh


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = (
    PROJECT_ROOT / "backend"
    if (PROJECT_ROOT / "backend").exists()
    else PROJECT_ROOT
)
sys.path.insert(0, str(BACKEND_ROOT))

from app.scene3d.exporter import read_glb_document


def inspect_glb(path: Path, max_bytes: int | None = None) -> dict:
    size_bytes = path.stat().st_size
    if max_bytes is not None and size_bytes > max_bytes:
        raise ValueError(
            f"GLB size {size_bytes} exceeds maximum {max_bytes} bytes"
        )
    document = read_glb_document(path.read_bytes())
    scene3d = document.get("asset", {}).get("extras", {}).get("scene3d")
    if not isinstance(scene3d, dict):
        raise ValueError("GLB is missing asset.extras.scene3d metadata")
    scene = trimesh.load(path, force="scene")
    geometries = list(scene.geometry.values())
    if not geometries:
        raise ValueError("GLB scene does not contain geometry")
    bounds = numpy.asarray(scene.bounds, dtype=numpy.float64)
    if bounds.shape != (2, 3) or not numpy.isfinite(bounds).all():
        raise ValueError("GLB scene bounds are invalid")
    nodes = sorted(scene.graph.nodes_geometry)
    if not nodes:
        raise ValueError("GLB scene does not contain semantic geometry nodes")
    return {
        "valid": True,
        "path": str(path.resolve()),
        "size_bytes": size_bytes,
        "scene3d": scene3d,
        "nodes": nodes,
        "geometry_count": len(geometries),
        "vertex_count": sum(len(mesh.vertices) for mesh in geometries),
        "face_count": sum(len(mesh.faces) for mesh in geometries),
        "bounds": bounds.tolist(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect and validate a PyGeoModel GLB artifact."
    )
    parser.add_argument("path", type=Path)
    parser.add_argument("--max-bytes", type=int)
    args = parser.parse_args()
    try:
        payload = inspect_glb(args.path, args.max_bytes)
    except Exception as exc:
        payload = {
            "valid": False,
            "path": str(args.path.resolve()),
            "error": str(exc),
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 1
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
