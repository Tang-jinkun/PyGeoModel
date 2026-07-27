# Air Corridor GLB Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a downloadable, geographically referenced GLB for each new air-corridor task and prove it with an enlarged 80-120 km synthetic scenario.

**Architecture:** A reusable `app.scene3d` package converts projected coordinates into a local glTF Y-up frame, creates bounded semantic meshes with `trimesh`, validates them, and exports a metadata-bearing GLB. The air-corridor worker invokes one model adapter inside its existing staging transaction, adds `scene_glb` to the typed output contract, and the existing generic Files tab exposes the download without a product viewer.

**Tech Stack:** Python 3.12, NumPy, PyProj, Shapely, Rasterio, trimesh 4.12.2, FastAPI/Pydantic, pytest, Docker, Three.js validation harness.

## Global Constraints

- GLB output kind is `scene_glb`; filename is `air_corridor_result.glb`; media type is `model/gltf-binary`.
- GLB contains result geometry only and MUST NOT contain a DEM terrain mesh.
- glTF axes are `X=east`, `Y=up`, `Z=south`; values are metres in a local frame with reconstructable geographic metadata.
- Vertical origin is the minimum emitted AMSL altitude rounded down to the nearest 100 metres.
- Geometry may use existing computed values or deterministic derivation from request/model values; it MUST NOT invent physical volumes.
- New-contract tasks fail atomically if required GLB generation or validation fails.
- Existing finished tasks remain readable and are not backfilled.
- Enlarged demo span is 80-120 km with 8-12 threats, 6-8 altitude layers, 300-600 risk samples, at least four altitude changes, and horizontal detour ratio at least 1.05.
- Target GLB size is below 15 MB; the hard acceptance ceiling is 50 MB.
- No production GLB viewer, guided camera, narration, or recording UI is added.
- All Python test commands run from `backend` with the absolute `E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe` interpreter.
- Manual source edits use `apply_patch`; generated runtime outputs remain Git ignored.

---

### Task 1: Scene Coordinate Frame And Dependency

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/app/scene3d/__init__.py`
- Create: `backend/app/scene3d/frame.py`
- Create: `backend/tests/test_scene3d_frame.py`

**Interfaces:**
- Produces: `SceneFrame.from_projected_points(target_epsg, points)`, `SceneFrame.to_gltf(point)`, `SceneFrame.metadata(task_id, model_id)`.
- Consumes: projected `(east_m, north_m, altitude_amsl_m)` points from model adapters.

- [ ] **Step 1: Add the failing frame tests**

Create `backend/tests/test_scene3d_frame.py`:

```python
import numpy

from app.scene3d.frame import SceneFrame


def test_frame_maps_enu_to_gltf_y_up() -> None:
    frame = SceneFrame.from_projected_points(
        32644,
        [(500_000.0, 3_500_000.0, 6123.0), (500_200.0, 3_500_400.0, 6380.0)],
    )

    assert frame.origin_x == 500_100.0
    assert frame.origin_y == 3_500_200.0
    assert frame.origin_altitude_m == 6100.0
    assert numpy.allclose(frame.to_gltf((500_200.0, 3_500_400.0, 6380.0)), [100.0, 280.0, -200.0])


def test_frame_metadata_round_trips_origin() -> None:
    frame = SceneFrame.from_projected_points(
        32644,
        [(500_000.0, 3_500_000.0, 6200.0), (501_000.0, 3_501_000.0, 6400.0)],
    )
    metadata = frame.metadata("air_corridor_task_a", "air_corridor")

    assert metadata["schema_version"] == 1
    assert metadata["source_crs"] == "EPSG:32644"
    assert metadata["axes"] == {"x": "east", "y": "up", "z": "south"}
    assert metadata["origin"]["altitude_amsl_m"] == 6200.0
    assert -180 <= metadata["origin"]["longitude"] <= 180
    assert -90 <= metadata["origin"]["latitude"] <= 90
```

- [ ] **Step 2: Run the frame tests and verify RED**

Run:

```powershell
cd backend
E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pytest tests/test_scene3d_frame.py -v
```

Expected: collection fails with `ModuleNotFoundError: No module named 'app.scene3d'`.

- [ ] **Step 3: Pin trimesh and implement the frame**

Append to `backend/requirements.txt`:

```text
trimesh==4.12.2
```

Create `backend/app/scene3d/frame.py` with this interface and behavior:

```python
from dataclasses import dataclass
from math import floor

import numpy
from pyproj import Transformer


ProjectedPoint = tuple[float, float, float]


@dataclass(frozen=True)
class SceneFrame:
    target_epsg: int
    origin_x: float
    origin_y: float
    origin_altitude_m: float
    origin_longitude: float
    origin_latitude: float

    @classmethod
    def from_projected_points(cls, target_epsg: int, points: list[ProjectedPoint]) -> "SceneFrame":
        values = numpy.asarray(points, dtype=numpy.float64)
        if values.ndim != 2 or values.shape[1] != 3 or len(values) == 0 or not numpy.isfinite(values).all():
            raise ValueError("Scene frame requires finite projected XYZ points")
        origin_x = float((values[:, 0].min() + values[:, 0].max()) / 2)
        origin_y = float((values[:, 1].min() + values[:, 1].max()) / 2)
        origin_altitude_m = float(floor(values[:, 2].min() / 100.0) * 100.0)
        to_wgs84 = Transformer.from_crs(f"EPSG:{target_epsg}", "EPSG:4326", always_xy=True)
        longitude, latitude = to_wgs84.transform(origin_x, origin_y)
        return cls(target_epsg, origin_x, origin_y, origin_altitude_m, float(longitude), float(latitude))

    def to_gltf(self, point: ProjectedPoint) -> numpy.ndarray:
        east, north, altitude = point
        result = numpy.asarray(
            [east - self.origin_x, altitude - self.origin_altitude_m, -(north - self.origin_y)],
            dtype=numpy.float64,
        )
        if not numpy.isfinite(result).all():
            raise ValueError("Scene point contains a non-finite coordinate")
        return result

    def metadata(self, task_id: str, model_id: str) -> dict:
        return {
            "schema_version": 1,
            "task_id": task_id,
            "model_id": model_id,
            "units": "metre",
            "source_crs": f"EPSG:{self.target_epsg}",
            "geographic_crs": "EPSG:4326",
            "origin": {
                "projected_x": self.origin_x,
                "projected_y": self.origin_y,
                "longitude": self.origin_longitude,
                "latitude": self.origin_latitude,
                "altitude_amsl_m": self.origin_altitude_m,
            },
            "axes": {"x": "east", "y": "up", "z": "south"},
        }
```

Create `backend/app/scene3d/__init__.py`:

```python
from .frame import SceneFrame

__all__ = ["SceneFrame"]
```

- [ ] **Step 4: Install the dependency and verify GREEN**

Run:

```powershell
cd backend
E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple --proxy http://127.0.0.1:7897 trimesh==4.12.2
E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pytest tests/test_scene3d_frame.py -v
```

Expected: `2 passed`.

- [ ] **Step 5: Commit the frame**

```powershell
git add backend/requirements.txt backend/app/scene3d backend/tests/test_scene3d_frame.py
git commit -m "feat: add local gltf scene frame"
```

---

### Task 2: Semantic Mesh Primitives And GLB Export

**Files:**
- Create: `backend/app/scene3d/primitives.py`
- Create: `backend/app/scene3d/exporter.py`
- Create: `backend/tests/test_scene3d_primitives.py`
- Create: `backend/tests/test_scene3d_exporter.py`

**Interfaces:**
- Produces: `tube_mesh(points, radius_m)`, `ribbon_mesh(points, width_m)`, `marker_mesh(point, radius_m)`, `annular_prism_mesh(center, inner_radius_m, outer_radius_m, bottom_y, top_y)`, `export_glb(path, meshes, scene_metadata, node_metadata)`.
- Consumes: finite glTF-frame points from Task 1.

- [ ] **Step 1: Write failing primitive tests**

Create `backend/tests/test_scene3d_primitives.py`:

```python
import numpy
import pytest

from app.scene3d.primitives import annular_prism_mesh, ribbon_mesh, tube_mesh


def test_tube_and_ribbon_are_finite_bounded_meshes() -> None:
    points = numpy.asarray([[0, 100, 0], [500, 120, -200], [1000, 160, -100]], dtype=float)
    tube = tube_mesh(points, radius_m=12, sections=8)
    ribbon = ribbon_mesh(points, width_m=400)

    assert len(tube.vertices) > 0 and len(tube.faces) > 0
    assert len(ribbon.vertices) == 6 and len(ribbon.faces) == 4
    assert numpy.isfinite(tube.vertices).all()
    assert numpy.isfinite(ribbon.vertices).all()


def test_annular_prism_preserves_inner_gap_and_height() -> None:
    mesh = annular_prism_mesh(
        center=numpy.asarray([0, 0, 0], dtype=float),
        inner_radius_m=100,
        outer_radius_m=500,
        bottom_y=50,
        top_y=850,
        sections=24,
    )

    radii = numpy.hypot(mesh.vertices[:, 0], mesh.vertices[:, 2])
    assert radii.min() == pytest.approx(100)
    assert radii.max() == pytest.approx(500)
    assert mesh.bounds[:, 1].tolist() == pytest.approx([50, 850])


def test_primitives_reject_invalid_geometry() -> None:
    with pytest.raises(ValueError, match="at least two"):
        tube_mesh(numpy.asarray([[0, 0, 0]], dtype=float), radius_m=1)
    with pytest.raises(ValueError, match="outer radius"):
        annular_prism_mesh(numpy.zeros(3), 20, 10, 0, 100)
```

- [ ] **Step 2: Write the failing exporter test**

Create `backend/tests/test_scene3d_exporter.py`:

```python
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
        {"start": (marker_mesh(numpy.asarray([0, 10, 0]), 4), MaterialSpec("terminal", (230, 235, 240, 255)))},
        scene_metadata={"schema_version": 1, "model_id": "air_corridor"},
        node_metadata={"start": {"kind": "terminal", "role": "start"}},
    )

    document = glb_json(path)
    assert document["asset"]["extras"]["scene3d"]["model_id"] == "air_corridor"
    node = next(item for item in document["nodes"] if item.get("name") == "start")
    assert node["extras"] == {"kind": "terminal", "role": "start"}
    loaded = trimesh.load(path, force="scene")
    assert "start" in loaded.graph.nodes_geometry
```

- [ ] **Step 3: Run primitive/export tests and verify RED**

Run:

```powershell
cd backend
E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pytest tests/test_scene3d_primitives.py tests/test_scene3d_exporter.py -v
```

Expected: import failures for `app.scene3d.primitives` and `app.scene3d.exporter`.

- [ ] **Step 4: Implement bounded mesh primitives**

Create `backend/app/scene3d/primitives.py`. The implementation MUST:

```python
from collections.abc import Iterable

import numpy
import trimesh


def _points(values: Iterable[Iterable[float]], minimum: int) -> numpy.ndarray:
    points = numpy.asarray(list(values), dtype=numpy.float64)
    if points.ndim != 2 or points.shape[1] != 3 or len(points) < minimum:
        raise ValueError(f"Geometry requires at least {minimum} points")
    if not numpy.isfinite(points).all():
        raise ValueError("Geometry contains non-finite coordinates")
    return points


def marker_mesh(point: numpy.ndarray, radius_m: float) -> trimesh.Trimesh:
    if radius_m <= 0:
        raise ValueError("Marker radius must be positive")
    mesh = trimesh.creation.icosphere(subdivisions=1, radius=radius_m)
    mesh.apply_translation(numpy.asarray(point, dtype=float))
    return mesh


def tube_mesh(points, radius_m: float, sections: int = 8) -> trimesh.Trimesh:
    values = _points(points, 2)
    if radius_m <= 0 or sections < 6:
        raise ValueError("Tube radius must be positive and sections at least six")
    pieces = [marker_mesh(point, radius_m) for point in values]
    for left, right in zip(values, values[1:]):
        vector = right - left
        length = float(numpy.linalg.norm(vector))
        if length == 0:
            continue
        cylinder = trimesh.creation.cylinder(radius=radius_m, height=length, sections=sections)
        transform = trimesh.geometry.align_vectors([0, 0, 1], vector / length)
        transform[:3, 3] = (left + right) / 2
        cylinder.apply_transform(transform)
        pieces.append(cylinder)
    return trimesh.util.concatenate(pieces)


def ribbon_mesh(points, width_m: float) -> trimesh.Trimesh:
    values = _points(points, 2)
    if width_m <= 0:
        raise ValueError("Ribbon width must be positive")
    offsets = []
    previous = numpy.asarray([0.0, 0.0, 1.0])
    for index in range(len(values)):
        before = values[max(0, index - 1)]
        after = values[min(len(values) - 1, index + 1)]
        tangent = after - before
        horizontal = numpy.asarray([tangent[0], 0.0, tangent[2]])
        norm = float(numpy.linalg.norm(horizontal))
        if norm > 0:
            previous = numpy.asarray([-horizontal[2], 0.0, horizontal[0]]) / norm
        offsets.append(previous * width_m / 2)
    vertices = numpy.asarray([value + side * offset for value, offset in zip(values, offsets) for side in (-1, 1)])
    faces = []
    for index in range(len(values) - 1):
        left = index * 2
        faces.extend([[left, left + 2, left + 1], [left + 1, left + 2, left + 3]])
    return trimesh.Trimesh(vertices=vertices, faces=numpy.asarray(faces), process=False)


def annular_prism_mesh(center: numpy.ndarray, inner_radius_m: float, outer_radius_m: float,
                       bottom_y: float, top_y: float, sections: int = 32) -> trimesh.Trimesh:
    center = numpy.asarray(center, dtype=numpy.float64)
    scalars = numpy.asarray([inner_radius_m, outer_radius_m, bottom_y, top_y], dtype=numpy.float64)
    if center.shape != (3,) or not numpy.isfinite(center).all() or not numpy.isfinite(scalars).all():
        raise ValueError("Annular prism requires finite coordinates")
    if inner_radius_m < 0 or outer_radius_m <= inner_radius_m:
        raise ValueError("Annular prism outer radius must exceed inner radius")
    if top_y <= bottom_y or sections < 8:
        raise ValueError("Annular prism requires positive height and at least eight sections")
    if inner_radius_m == 0:
        mesh = trimesh.creation.cylinder(radius=outer_radius_m, height=top_y - bottom_y, sections=sections)
        mesh.apply_transform(trimesh.transformations.rotation_matrix(-numpy.pi / 2, [1, 0, 0]))
        mesh.apply_translation([center[0], (bottom_y + top_y) / 2, center[2]])
        return mesh

    angles = numpy.linspace(0, 2 * numpy.pi, sections, endpoint=False)
    outer_x = center[0] + numpy.cos(angles) * outer_radius_m
    outer_z = center[2] + numpy.sin(angles) * outer_radius_m
    inner_x = center[0] + numpy.cos(angles) * inner_radius_m
    inner_z = center[2] + numpy.sin(angles) * inner_radius_m
    rings = [
        numpy.column_stack([outer_x, numpy.full(sections, bottom_y), outer_z]),
        numpy.column_stack([outer_x, numpy.full(sections, top_y), outer_z]),
        numpy.column_stack([inner_x, numpy.full(sections, bottom_y), inner_z]),
        numpy.column_stack([inner_x, numpy.full(sections, top_y), inner_z]),
    ]
    vertices = numpy.vstack(rings)
    faces = []
    for index in range(sections):
        nxt = (index + 1) % sections
        ob, on = index, nxt
        ot, otn = sections + index, sections + nxt
        ib, ibn = 2 * sections + index, 2 * sections + nxt
        it, itn = 3 * sections + index, 3 * sections + nxt
        faces.extend([
            [ob, on, ot], [on, otn, ot],
            [ib, it, ibn], [ibn, it, itn],
            [ot, otn, it], [otn, itn, it],
            [ob, ib, on], [on, ib, ibn],
        ])
    return trimesh.Trimesh(vertices=vertices, faces=numpy.asarray(faces), process=False)
```

- [ ] **Step 5: Implement GLB export and structured extras injection**

Create `backend/app/scene3d/exporter.py` with:

```python
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


def export_glb(path: Path, meshes: dict[str, tuple[trimesh.Trimesh, MaterialSpec]], *,
               scene_metadata: dict, node_metadata: dict[str, dict]) -> None:
    if not meshes:
        raise ValueError("GLB scene requires at least one mesh")
    scene = trimesh.Scene()
    for name, (mesh, material) in meshes.items():
        if mesh.is_empty or not numpy.isfinite(mesh.vertices).all() or len(mesh.faces) == 0:
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
    payload = _inject_extras(payload, scene_metadata, node_metadata)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    loaded = trimesh.load(path, force="scene")
    if set(meshes) - set(loaded.graph.nodes_geometry):
        raise ValueError("Exported GLB lost semantic scene nodes")
```

`_inject_extras` MUST parse the 12-byte GLB header and every 8-byte chunk header, decode the JSON chunk with `json.loads`, set `document["asset"]["extras"]["scene3d"]`, attach matching node extras by node name, re-encode/pad JSON to four-byte alignment, preserve binary chunks byte-for-byte, and rewrite the total GLB length. It MUST reject non-v2 GLB headers, missing JSON chunks, and node metadata names absent from the document.

- [ ] **Step 6: Verify GREEN and commit**

Run:

```powershell
cd backend
E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pytest tests/test_scene3d_primitives.py tests/test_scene3d_exporter.py -v
```

Expected: all primitive and exporter tests pass.

Commit:

```powershell
git add backend/app/scene3d backend/tests/test_scene3d_primitives.py backend/tests/test_scene3d_exporter.py
git commit -m "feat: add semantic glb mesh exporter"
```

---

### Task 3: Air-Corridor Scene Adapter

**Files:**
- Create: `backend/app/scene3d/air_corridor.py`
- Create: `backend/tests/test_air_corridor_scene3d.py`
- Modify: `backend/app/scene3d/__init__.py`

**Interfaces:**
- Produces: `write_air_corridor_glb(path, *, task_id, target_epsg, path_points, sample_features, prepared_threat_xy, start_ground_elevation_m, end_ground_elevation_m, payload, route_found) -> dict` returning scene metadata.
- Consumes: Task 1 frame, Task 2 primitives/exporter, existing `AirCorridorPlanningRequest` and in-memory worker result.

- [ ] **Step 1: Write route-found and route-not-found failing tests**

Create `backend/tests/test_air_corridor_scene3d.py` with a three-point path, low/medium/high risk samples, and two threats (one with `min_range_m=0`, one with a non-zero inner radius). Assert:

```python
def test_air_corridor_scene_writes_semantic_nodes(tmp_path: Path) -> None:
    output = tmp_path / "air_corridor_result.glb"
    metadata = write_air_corridor_glb(
        output,
        task_id="air_corridor_task_a",
        target_epsg=32644,
        path_points=[(500000, 3500000, 6200), (501000, 3500200, 6800), (502000, 3500000, 6400)],
        sample_features=sample_features([0.0, 5.0, 10.0]),
        prepared_threat_xy={"a": (501000, 3500000), "b": (501500, 3500300)},
        start_ground_elevation_m=5900,
        end_ground_elevation_m=6000,
        payload=payload_with_two_threats(),
        route_found=True,
    )
    scene = trimesh.load(output, force="scene")
    names = set(scene.graph.nodes_geometry)
    assert {"corridor_path", "corridor_ribbon", "risk_low", "risk_medium", "risk_high", "start", "end"} <= names
    assert {"threat_a_warning", "threat_a_kill", "threat_b_warning", "threat_b_kill"} <= names
    assert metadata["route_found"] is True
    assert metadata["risk_sample_count"] == 3


def test_route_not_found_scene_contains_context_only(tmp_path: Path) -> None:
    output = tmp_path / "air_corridor_result.glb"
    write_air_corridor_glb(
        output,
        task_id="air_corridor_task_a",
        target_epsg=32644,
        path_points=[],
        sample_features=[],
        prepared_threat_xy={"a": (501000, 3500000)},
        start_ground_elevation_m=5900,
        end_ground_elevation_m=6000,
        payload=payload_with_one_threat(),
        route_found=False,
    )
    names = set(trimesh.load(output, force="scene").graph.nodes_geometry)
    assert {"start", "end", "threat_a_warning", "threat_a_kill"} <= names
    assert "corridor_path" not in names
```

The test helpers MUST build valid `AirCorridorPlanningRequest` values and sample geometries whose coordinates correspond to the supplied path points.

- [ ] **Step 2: Run the adapter tests and verify RED**

Run:

```powershell
cd backend
E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pytest tests/test_air_corridor_scene3d.py -v
```

Expected: import failure for `app.scene3d.air_corridor`.

- [ ] **Step 3: Implement the adapter**

Create `backend/app/scene3d/air_corridor.py` around this exact data flow:

```python
PATH = MaterialSpec("corridor_path", (36, 144, 95, 255))
RIBBON = MaterialSpec("corridor_ribbon", (45, 123, 170, 88))
RISK_LOW = MaterialSpec("risk_low", (36, 144, 95, 255))
RISK_MEDIUM = MaterialSpec("risk_medium", (233, 162, 43, 255))
RISK_HIGH = MaterialSpec("risk_high", (201, 73, 73, 255))
WARNING = MaterialSpec("threat_warning", (225, 126, 52, 72))
KILL = MaterialSpec("threat_kill", (201, 73, 73, 96))
START = MaterialSpec("start", (235, 240, 245, 255))
END = MaterialSpec("end", (43, 55, 70, 255))
```

Implementation requirements:

1. Compute terminal AMSL as `altitude_m` for `altitude_mode="amsl"` and `ground_elevation_m + altitude_m` for `altitude_mode="agl"`; collect those terminals, all path points, and all threat altitude endpoints to construct `SceneFrame`.
2. Convert path points and threat centers through `frame.to_gltf`.
3. Emit `corridor_path` with `tube_mesh(gltf_path, radius_m=max(20, payload.planning.corridor_width_m * 0.04))`.
4. Emit `corridor_ribbon` with the exact configured corridor width.
5. Normalize finite sample risks by maximum finite risk. Use bins `<=0.33`, `<=0.66`, and `>0.66`; if maximum is zero, all samples are low.
6. Merge low-detail marker meshes by risk bin and omit empty bins.
7. Emit each warning and kill volume with exact inner radius, outer radius, minimum altitude, and maximum altitude. Warning radius is `warning_zone_radius_m or max_range_m`; kill radius is `kill_zone_radius_m or max_range_m * 0.7`.
8. Emit start/end markers at their computed/requested AMSL terminal points.
9. Call `export_glb` once with semantic node metadata including counts, original risk ranges, threat ID, radii, and altitude bounds.
10. Return metadata extending the frame metadata with `route_found`, `risk_sample_count`, `threat_count`, and `corridor_width_m`.

Update `backend/app/scene3d/__init__.py` to export `write_air_corridor_glb`.

- [ ] **Step 4: Verify GREEN and commit**

Run:

```powershell
cd backend
E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pytest tests/test_air_corridor_scene3d.py tests/test_scene3d_frame.py tests/test_scene3d_primitives.py tests/test_scene3d_exporter.py -v
```

Expected: all scene3d tests pass.

Commit:

```powershell
git add backend/app/scene3d backend/tests/test_air_corridor_scene3d.py
git commit -m "feat: build air corridor glb scenes"
```

---

### Task 4: Typed Output Contract And Worker Transaction

**Files:**
- Modify: `backend/app/schemas/air_corridor.py`
- Modify: `backend/app/services/air_corridor_output_files.py`
- Modify: `backend/app/workers/air_corridor_task.py`
- Modify: `backend/tests/test_air_corridor_api.py`
- Modify: `backend/tests/test_air_corridor_task.py`
- Create: `backend/tests/test_air_corridor_output_files.py`

**Interfaces:**
- Produces: `scene_glb` in task outputs, file list, output manifest, and download endpoint.
- Consumes: `write_air_corridor_glb` from Task 3.

- [ ] **Step 1: Add failing output-contract tests**

Create `backend/tests/test_air_corridor_output_files.py`:

```python
from pathlib import Path

from app.services.air_corridor_output_files import describe_air_corridor_output_file


def test_scene_glb_descriptor_uses_standard_contract(tmp_path: Path) -> None:
    path = tmp_path / "air_corridor_result.glb"
    path.write_bytes(b"glTF")
    item = describe_air_corridor_output_file("air_corridor_task_a", "scene_glb", path)
    assert item.filename == "air_corridor_result.glb"
    assert item.media_type == "model/gltf-binary"
    assert item.label == "Air Corridor 3D Result GLB"
    assert item.download_url.endswith("/outputs/scene_glb")
```

Extend `backend/tests/test_air_corridor_api.py` with a finished `air_corridor_task_a` record and `data/outputs/air_corridor_task_a/air_corridor_result.glb` containing `b"glTF-test"`. Assert `GET /api/air-corridor/planning/air_corridor_task_a/outputs/scene_glb` returns status 200, content type `model/gltf-binary`, and exactly `b"glTF-test"`.

- [ ] **Step 2: Add a failing worker integration test**

Add this helper and focused worker test to `backend/tests/test_air_corridor_task.py`:

```python
from types import SimpleNamespace

import rasterio

from app.workers.air_corridor_task import _write_air_corridor_outputs


def prepared_dem(tmp_path: Path):
    path = tmp_path / "projected.tif"
    data = numpy.zeros((10, 10), dtype=numpy.float32)
    with rasterio.open(
        path, "w", driver="GTiff", width=10, height=10, count=1, dtype="float32",
        crs="EPSG:32644", transform=from_origin(0, 100, 10, 10),
    ) as dataset:
        dataset.write(data, 1)
    return SimpleNamespace(
        projected_dem=path, target_epsg=32644,
        start_x=5.0, start_y=95.0, end_x=95.0, end_y=95.0,
        threat_xy={},
        bounds=SimpleNamespace(left=0, bottom=0, right=100, top=100),
        resolution_m=(10.0, 10.0),
    )


def test_worker_stages_scene_glb_and_metadata(tmp_path: Path, monkeypatch) -> None:
    task_id = "air_corridor_task_a"
    output_dir = tmp_path / task_id
    staging_dir = output_dir / ".staging-test"
    staging_dir.mkdir(parents=True)
    payload = AirCorridorPlanningRequest(
        dem_id="dem_a",
        start={"lon": 79.8, "lat": 31.48, "altitude_m": 300},
        end={"lon": 79.81, "lat": 31.48, "altitude_m": 300},
        altitude_layers_m=[300], threats=[],
    )
    scene_metadata = {
        "schema_version": 1, "task_id": task_id, "model_id": "air_corridor",
        "units": "metre", "source_crs": "EPSG:32644", "geographic_crs": "EPSG:4326",
        "origin": {"projected_x": 50.0, "projected_y": 95.0, "longitude": 79.8,
                   "latitude": 31.48, "altitude_amsl_m": 0.0},
        "axes": {"x": "east", "y": "up", "z": "south"},
        "route_found": True, "risk_sample_count": 10, "threat_count": 0,
        "corridor_width_m": 500.0,
    }

    def fake_glb(path: Path, **_kwargs):
        path.write_bytes(b"glTF")
        return scene_metadata

    monkeypatch.setattr("app.workers.air_corridor_task.write_air_corridor_glb", fake_glb)
    outputs, output_files, _metrics, _model, _warnings = _write_air_corridor_outputs(
        task_id, staging_dir, output_dir, prepared_dem(tmp_path), payload,
    )

assert outputs.scene_glb == f"/outputs/{task_id}/air_corridor_result.glb"
assert any(item.kind == "scene_glb" and item.exists for item in output_files)
manifest = json.loads((output_dir / "output_manifest.json").read_text(encoding="utf-8"))
assert any(item["kind"] == "scene_glb" for item in manifest["files"])
assert json.loads((output_dir / "model_metadata.json").read_text())["scene3d"]["model_id"] == "air_corridor"
```

Add a second test that sets `settings.data_dir = tmp_path`, calls `settings.ensure_directories()`, creates a task with `create_air_corridor_task(payload)`, monkeypatches `find_dem_file` and `_prepare_air_corridor_dem` to use `prepared_dem(tmp_path)`, and monkeypatches `write_air_corridor_glb` to raise `ValueError("invalid scene")`. Call `run_air_corridor_task(task.task_id, payload)`, then assert `get_air_corridor_task(task.task_id).status == "failed"`, the message contains `invalid scene`, and `(settings.outputs_dir / task.task_id / "air_corridor_result.glb").exists()` is false.

- [ ] **Step 3: Run the contract tests and verify RED**

Run:

```powershell
cd backend
E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pytest tests/test_air_corridor_output_files.py tests/test_air_corridor_api.py tests/test_air_corridor_task.py -v
```

Expected: failures because `scene_glb` is not a valid output kind and no worker artifact exists.

- [ ] **Step 4: Extend schemas and file maps**

Make these exact contract changes:

```python
AirCorridorOutputKind = Literal[
    "corridor_path_geojson", "corridor_buffer_geojson", "threat_zones_geojson",
    "risk_samples_geojson", "cost_summary_json", "scene_glb",
    "model_metadata_json", "output_manifest_json",
]

class AirCorridorPlanningOutputs(BaseModel):
    scene_glb: str | None = None

class Scene3dMetadata(BaseModel):
    schema_version: int
    task_id: str
    model_id: str
    units: str
    source_crs: str
    geographic_crs: str
    origin: dict[str, float]
    axes: dict[str, str]
    route_found: bool
    risk_sample_count: int
    threat_count: int
    corridor_width_m: float

class AirCorridorModelMetadata(BaseModel):
    scene3d: Scene3dMetadata | None = None
```

The shown fields are inserted into the existing classes without removing their current fields.

Add `scene_glb` to all three output maps with filename, media type, and label from Global Constraints.

- [ ] **Step 5: Integrate the adapter before manifest commit**

In `_write_air_corridor_outputs`:

1. Define `scene_path = staging_dir / "air_corridor_result.glb"`.
2. Call `write_air_corridor_glb` after result computation and before model/manifest JSON writes.
3. Pass `task_id`, `prepared.target_epsg`, `result["path_points"]`, `result["sample_features"]`, `prepared.threat_xy`, `result["start_ground"]`, `result["end_ground"]`, `payload`, and `metrics.route_found`.
4. Set `model.scene3d` from the returned metadata.
5. Set `outputs.scene_glb=f"/outputs/{task_id}/air_corridor_result.glb"`.
6. Let existing typed `AIR_CORRIDOR_OUTPUT_FILENAMES` drive staged existence checks and manifest generation.

Do not catch exporter exceptions inside `_write_air_corridor_outputs`; the existing outer transaction must remove staging and mark the task failed.

- [ ] **Step 6: Verify GREEN and commit**

Run:

```powershell
cd backend
E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pytest tests/test_air_corridor_output_files.py tests/test_air_corridor_api.py tests/test_air_corridor_task.py tests/test_air_corridor_scene3d.py -v
```

Expected: all selected tests pass.

Commit:

```powershell
git add backend/app/schemas/air_corridor.py backend/app/services/air_corridor_output_files.py backend/app/workers/air_corridor_task.py backend/tests/test_air_corridor_output_files.py backend/tests/test_air_corridor_api.py backend/tests/test_air_corridor_task.py
git commit -m "feat: publish air corridor glb outputs"
```

---

### Task 5: Enlarged Scenario Metrics And Acceptance

**Files:**
- Modify: `backend/app/schemas/air_corridor.py`
- Modify: `backend/app/workers/air_corridor_task.py`
- Modify: `backend/app/demo_scenarios/route_builders.py`
- Modify: `backend/app/demo_scenarios/registry.py`
- Modify: `backend/tests/demo_scenario_helpers.py`
- Modify: `backend/tests/test_air_corridor_task.py`
- Modify: `backend/tests/test_demo_route_builders.py`
- Modify: `backend/tests/test_demo_scenario_registry.py`

**Interfaces:**
- Produces: enlarged version-2 request, `direct_distance_m`, `horizontal_detour_ratio`, `risk_sample_count`, strict demo acceptance.
- Consumes: existing deterministic `TerrainGrid.select(profile, candidate_index, required_offsets=required_offsets)` and the `scene_glb` output contract.

- [ ] **Step 1: Write failing metric tests**

Extend `backend/tests/test_air_corridor_task.py`:

```python
def test_air_corridor_reports_direct_detour_and_sample_metrics() -> None:
    dem = numpy.zeros((10, 10), dtype=numpy.float32)
    transform = from_origin(0, 100, 10, 10)
    payload = AirCorridorPlanningRequest(
        dem_id="dem_a",
        start={"lon": 79.8, "lat": 31.48, "altitude_m": 300},
        end={"lon": 79.81, "lat": 31.48, "altitude_m": 300},
        altitude_layers_m=[300],
        threats=[],
    )
    prepared = Prepared()
    prepared.threat_xy = {}
    result = _compute_air_corridor(dem, transform, None, prepared, payload)
    metrics = result["metrics"]
    assert metrics.direct_distance_m == pytest.approx(90.0)
    assert metrics.horizontal_detour_ratio >= 1.0
    assert metrics.risk_sample_count == len(result["sample_features"])
```

The expected direct distance uses `Prepared.start_x/start_y/end_x/end_y`; detour uses horizontal XY path length divided by that direct distance, while existing `corridor_length_m` remains 3D path length.

- [ ] **Step 2: Write failing enlarged-builder tests**

First change `write_dem` in `backend/tests/demo_scenario_helpers.py` to accept `size: int = 80`, use `numpy.indices((size, size))`, and pass `width=size, height=size` to Rasterio. Existing callers keep the 80-cell default.

Replace the old three-threat assertion in `backend/tests/test_demo_route_builders.py` with a 260 by 260 cell fixture and assertions:

```python
write_dem(path, size=260)
scenario = build_air_corridor(TerrainGrid.load(path, 260), "dem_a", 0)
request = AirCorridorPlanningRequest.model_validate(scenario.request)
geod = Geod(ellps="WGS84")
_, _, direct_m = geod.inv(request.start.lon, request.start.lat, request.end.lon, request.end.lat)

assert scenario.version == 2
assert 80_000 <= direct_m <= 120_000
assert 8 <= len(request.threats) <= 12
assert 6 <= len(request.altitude_layers_m) <= 8
assert request.planning.horizontal_resolution_m <= 300
assert len({(item.lon, item.lat) for item in request.threats}) == len(request.threats)
assert all(item.max_altitude_m > item.min_altitude_m for item in request.threats)
```

Add a registry test whose valid metrics include direct span 100 km, 400 samples, five altitude changes, detour 1.08, and required outputs including `scene_glb`; independently lower each threshold and assert rejection.

- [ ] **Step 3: Run enlarged-scenario tests and verify RED**

Run:

```powershell
cd backend
E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pytest tests/test_air_corridor_task.py tests/test_demo_route_builders.py tests/test_demo_scenario_registry.py -v
```

Expected: schema lacks new metrics and builder still emits a 25 km, three-threat version-1 scenario.

- [ ] **Step 4: Add observable metrics**

Add nullable/default-safe fields to `AirCorridorPlanningMetrics`:

```python
direct_distance_m: float = 0
horizontal_detour_ratio: float = 0
risk_sample_count: int = 0
```

In `_path_metrics`, compute:

```python
direct_distance = math.hypot(prepared.end_x - prepared.start_x, prepared.end_y - prepared.start_y)
horizontal_length = sum(math.hypot(right[0] - left[0], right[1] - left[1]) for left, right in zip(path_points, path_points[1:]))
horizontal_detour_ratio = horizontal_length / direct_distance if direct_distance > 0 else 0
```

Populate the three new fields, preserving existing 3D `corridor_length_m` semantics.

- [ ] **Step 5: Build the deterministic enlarged request**

Update `build_air_corridor` to use these deterministic offsets on both the 260-cell fixture and 512-cell real terrain grid:

```python
route_offsets = [(0, -100), (0, -60), (0, -20), (0, 20), (0, 60), (0, 100)]
threat_offsets = [
    (-10, -75), (8, -55), (-12, -35), (10, -15), (-8, 5),
    (12, 25), (-10, 45), (8, 65), (-6, 80), (10, 90),
]
required_offsets = sorted(set(route_offsets + threat_offsets))
anchor = terrain.select("rough", candidate_index, margin=112, required_offsets=required_offsets)
```

Emit exactly 10 threats from `threat_offsets`, using the local DEM elevation and these deterministic formulas:

```python
max_range_m = 10_000 + (index % 4) * 2_000
kill_zone_radius_m = 4_000 + (index % 3) * 500
warning_zone_radius_m = 7_000 + (index % 4) * 750
max_altitude_m = ground_elevation_m + 1_100 + (index % 4) * 450
threat_level = 5 + (index % 6)
```

Set `min_range_m=0`, `min_altitude_m=0`, and verify the formulas always satisfy `kill_zone_radius_m <= warning_zone_radius_m <= max_range_m`. Use:

```python
altitude_layers_m = [300, 600, 900, 1200, 1600, 2000, 2400, 2800]
horizontal_resolution_m = 250
threat_weight = 24
altitude_change_weight = 0.01
corridor_width_m = 800
```

Each threat MUST derive maximum altitude from its local DEM elevation, use deterministic radius/level variation, satisfy `kill_zone_radius_m <= warning_zone_radius_m <= max_range_m`, and stay on valid DEM cells. Return `ScenarioEnvelope(..., version=2, ...)`.

- [ ] **Step 6: Enforce strict demo acceptance**

Update the air-corridor `ModelSpec`:

```python
required_outputs=frozenset({
    "threat_zones_geojson", "corridor_buffer_geojson", "corridor_path_geojson",
    "risk_samples_geojson", "scene_glb",
})
```

Its validator must reject unless:

```python
metrics["route_found"] is True
80_000 <= float(metrics["direct_distance_m"]) <= 120_000
300 <= int(metrics["risk_sample_count"]) <= 600
int(metrics["altitude_change_count"]) >= 4
float(metrics["horizontal_detour_ratio"]) >= 1.05
float(metrics["corridor_length_m"]) > 0
```

- [ ] **Step 7: Verify GREEN and commit**

Run:

```powershell
cd backend
E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pytest tests/test_air_corridor_task.py tests/test_demo_route_builders.py tests/test_demo_scenario_registry.py tests/test_demo_scenario_generator.py -v
```

Expected: all selected tests pass.

Commit:

```powershell
git add backend/app/schemas/air_corridor.py backend/app/workers/air_corridor_task.py backend/app/demo_scenarios/route_builders.py backend/app/demo_scenarios/registry.py backend/tests/demo_scenario_helpers.py backend/tests/test_air_corridor_task.py backend/tests/test_demo_route_builders.py backend/tests/test_demo_scenario_registry.py
git commit -m "feat: enlarge synthetic air corridor scenario"
```

---

### Task 6: GLB Inspection CLI And Documentation

**Files:**
- Create: `scripts/inspect_glb.py`
- Create: `backend/tests/test_inspect_glb_cli.py`
- Modify: `README.md`

**Interfaces:**
- Produces: machine-readable GLB summary for verification and troubleshooting.
- Consumes: any generated GLB path.

- [ ] **Step 1: Write the failing CLI test**

Create `backend/tests/test_inspect_glb_cli.py` that exports a one-node test GLB with `export_glb`, invokes:

```powershell
$glbPath = 'E:\Github\PyGeoModel\data\outputs\air_corridor_task_a\air_corridor_result.glb'
python scripts/inspect_glb.py $glbPath
```

and asserts JSON stdout contains `valid=true`, byte size, scene metadata, node names, geometry count, vertex count, face count, and bounds.

- [ ] **Step 2: Run CLI test and verify RED**

Expected: subprocess fails because `scripts/inspect_glb.py` does not exist.

- [ ] **Step 3: Implement the inspector**

The script MUST parse arguments with `argparse`, load the GLB JSON chunk with the structured parser from `app.scene3d.exporter`, load geometry through `trimesh`, reject files above an optional `--max-bytes` value, and print one UTF-8 JSON object. It exits 0 only when GLB v2, extras, finite bounds, semantic nodes, and geometry are present.

Document in `README.md`:

```powershell
$taskId = (Get-ChildItem data\tasks\air_corridor_task_*.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1).BaseName
docker compose exec -T backend python /app/scripts/inspect_glb.py "/workspace/data/outputs/$taskId/air_corridor_result.glb" --max-bytes 50000000
```

State that the GLB is result-only, uses local Y-up coordinates, and requires `model_metadata.json` or embedded `asset.extras.scene3d` for georeferencing.

- [ ] **Step 4: Verify GREEN and commit**

Run:

```powershell
cd backend
E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pytest tests/test_inspect_glb_cli.py -v
```

Commit:

```powershell
git add scripts/inspect_glb.py backend/tests/test_inspect_glb_cli.py README.md
git commit -m "docs: add glb inspection workflow"
```

---

### Task 7: Real Docker Artifact And Visual Acceptance

**Files:**
- Runtime create: `data/outputs/$taskId/air_corridor_result.glb` (Git ignored; `$taskId` is captured from the POST response)
- Runtime update: `data/demo-scenarios/dem_20260713_080113_884937cf/*` (Git ignored)
- Verification only: visual companion content and screenshots outside tracked source

**Interfaces:**
- Produces: one accepted enlarged real task, downloadable GLB, structural report, interactive preview URL, desktop/mobile screenshots.
- Consumes: all previous tasks and the existing Zanda County DEM.

- [ ] **Step 1: Run full local regression before container build**

Run:

```powershell
cd backend
E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pytest -q
cd ..\frontend
npm test -- --run
npm run build
```

Expected: all backend/frontend tests pass and the production build exits 0. Existing chunk-size and NumPy deprecation warnings may remain but no new failures are accepted.

- [ ] **Step 2: Build a feature backend image through Clash**

Run from the feature worktree:

```powershell
$env:HTTP_PROXY='http://127.0.0.1:7897'
$env:HTTPS_PROXY='http://127.0.0.1:7897'
docker build -f backend/Dockerfile -t pygeomodel-air-glb-pilot:latest .
```

Expected: image build succeeds and contains `trimesh==4.12.2` plus the updated scripts.

- [ ] **Step 3: Start an isolated backend using the shared data directory**

Use port 8001 so the main app on 8000/5173 remains untouched:

```powershell
docker run -d --name pygeomodel-air-glb-pilot -p 127.0.0.1:8001:8000 -e PYGEOMODEL_DATA_DIR=/workspace/data -v E:\Github\PyGeoModel\data:/workspace/data pygeomodel-air-glb-pilot:latest
Invoke-RestMethod http://127.0.0.1:8001/api/health
```

Expected: `{"status":"ok"}`.

- [ ] **Step 4: Generate and submit only the enlarged air-corridor scenario**

Run:

```powershell
$demId = 'dem_20260713_080113_884937cf'
docker exec pygeomodel-air-glb-pilot python -c "from pathlib import Path; from app.demo_scenarios.generator import generate_one; generate_one(Path('/workspace/data'), '$demId', 'air_corridor', 0)"
$scenarioPath = "E:\Github\PyGeoModel\data\demo-scenarios\$demId\air-corridor.json"
$scenario = Get-Content -Raw -LiteralPath $scenarioPath | ConvertFrom-Json
$body = $scenario.request | ConvertTo-Json -Depth 100 -Compress
$created = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8001/api/air-corridor/planning' -ContentType 'application/json' -Body $body
$taskId = $created.task_id
$deadline = (Get-Date).AddMinutes(30)
do {
  Start-Sleep -Seconds 2
  $detail = Invoke-RestMethod -Uri "http://127.0.0.1:8001/api/air-corridor/planning/$taskId"
} while ($detail.status -in @('pending', 'running') -and (Get-Date) -lt $deadline)
if ($detail.status -ne 'finished') { throw "Air corridor task ended as $($detail.status): $($detail.message)" }
$metrics = Invoke-RestMethod -Uri "http://127.0.0.1:8001/api/air-corridor/planning/$taskId/metrics"
$metrics | ConvertTo-Json -Depth 10
```

Do not run or modify radar tasks.

Expected: task finishes with `route_found=true`; metrics meet all enlarged acceptance thresholds.

- [ ] **Step 5: Verify files, API download, metadata, and size**

Run:

```powershell
$taskId = (Get-ChildItem 'E:\Github\PyGeoModel\data\tasks\air_corridor_task_*.json' | Sort-Object LastWriteTime -Descending | Select-Object -First 1).BaseName
docker exec pygeomodel-air-glb-pilot python /app/scripts/inspect_glb.py "/workspace/data/outputs/$taskId/air_corridor_result.glb" --max-bytes 50000000
curl.exe --fail --output NUL "http://127.0.0.1:8001/api/air-corridor/planning/$taskId/outputs/scene_glb"
```

Expected inspector evidence:

- `valid=true`
- file size below 50 MB and target below 15 MB
- route, ribbon, start, end, risk, and all threat node groups present
- `schema_version=1`, `model_id=air_corridor`, source EPSG, origin, and axis metadata present
- finite non-zero bounds spanning tens of kilometres

- [ ] **Step 6: Create a temporary full-bleed Three.js preview**

Use the active visual-companion session, copy the GLB into its content assets, and push a new full-document HTML screen that:

- imports the workspace Three.js version and `GLTFLoader`/`OrbitControls`;
- loads the generated GLB;
- frames the complete bounding box with a perspective camera;
- uses neutral lighting and a ground-reference grid only (the grid is not exported);
- displays compact node toggles and metadata outside the canvas without covering it;
- exposes no guided camera or playback controls;
- reports load errors visibly.

Provide the keyed visual-companion URL to the user.

- [ ] **Step 7: Perform desktop/mobile visual verification**

Use Playwright at `1440x900` and `390x844`:

- wait for a `data-model-loaded=true` marker;
- verify the WebGL canvas has non-zero dimensions;
- sample canvas pixels and prove the frame is not blank or a single color;
- verify route/ribbon/threat geometry is inside the viewport;
- orbit the scene and prove pixels change;
- confirm labels and controls do not overlap the canvas or each other;
- save screenshots under the visualization workspace, not the repository.

- [ ] **Step 8: Re-run the scenario and verify task reuse**

Run the demo scenario runner against port 8001 without `--rebuild`. Confirm the accepted version-2 air-corridor request reuses the same task ID and does not create a duplicate.

- [ ] **Step 9: Final source-state checks and temporary cleanup**

Run:

```powershell
git status --short
git diff --check
docker stop pygeomodel-air-glb-pilot
docker rm pygeomodel-air-glb-pilot
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Expected: feature worktree is clean, runtime data is ignored, temporary port 8001 container is removed, and the main `pygeomodel-backend-1`/`pygeomodel-frontend-1` containers remain running on 8000/5173.

---

### Task 8: Final Review And Branch Update

**Files:**
- Verify only: all changed files and `docs/superpowers/specs/2026-07-14-air-corridor-glb-pilot-design.md`
- Modify only if verification finds a documented defect.

**Interfaces:**
- Produces: reviewed feature branch and updated PR with pilot evidence.
- Consumes: fresh verification from Task 7.

- [ ] **Step 1: Review `origin/main...HEAD` against the design**

Check every goal, non-goal, coordinate rule, scene node, output contract, scenario threshold, rollback rule, and verification requirement. Findings are ordered by severity and fixed through a new failing test before production changes.

- [ ] **Step 2: Run final verification after review fixes**

Run full backend tests, frontend tests/build, `git diff --check`, GLB inspector, output API check, and the real visual smoke check again. Completion claims require fresh command output.

- [ ] **Step 3: Push the feature branch and update PR #1**

Run through Clash:

```powershell
git -c http.proxy=http://127.0.0.1:7897 -c https.proxy=http://127.0.0.1:7897 push origin codex/independent-model-demo-scenarios
```

Update PR #1 summary and verification with the GLB pilot, enlarged scenario metrics, artifact size, node list, screenshot evidence, and preview status. Preserve the feature worktree for user review.
