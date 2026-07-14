# Tactical Scene3D Symbols Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export a self-contained, tactically readable air-corridor GLB whose threat units, symbols, labels, routes, and risk zones retain their intended colors both offline and over the workbench DEM.

**Architecture:** Extend the backend `scene3d` kernel with hierarchical scene nodes, standard unlit materials, and reusable tactical unit assemblies. The air-corridor adapter maps each threat and its sampled DEM elevation into that kernel; the frontend only preserves semantics during geographic flattening and supplies neutral baseline light for PBR content.

**Tech Stack:** Python 3.12, NumPy, trimesh 4.12.2, rasterio 1.4.3, pytest 8.3.4, TypeScript 5.7.3, Three.js 0.171, MapLibre GL 4.7.1, Vitest 4.1.10, Docker Desktop.

## Global Constraints

- Work only in `E:\Github\PyGeoModel\.worktrees\independent-model-demo-scenarios` on `codex/independent-model-demo-scenarios`.
- Keep `scene3d.schema_version` at `1`; geographic axes, units, origin, output kind, filename, manifest, and download contracts do not change.
- Use standard `KHR_materials_unlit` in `extensionsUsed`, not `extensionsRequired`, plus matching base color and an emissive fallback.
- Keep tactical assemblies self-contained in the GLB. Do not create frontend symbols, frontend semantic recoloring, external fonts, external textures, or camera-facing billboards.
- Air-corridor is the only model adapter in this increment. Do not add director cameras, playback, recording, DEM geometry, formal MIL-STD-2525/APP-6, or other model adapters.
- Default missing unit type/status/heading to `unknown`/`unknown`/north. Record an invalid individual unit in `scene3d.omitted_units` and task warnings without emitting a partial assembly.
- Fail the complete staged artifact for duplicate normalized unit IDs, malformed GLB structure, incomplete unlit serialization, metadata injection failure, or reload failure.
- Air-defense unit altitude comes from the prepared DEM surface at the threat coordinate; influence-zone altitude remains the request's absolute interval.
- Compute `display_scale_m` as `clamp(corridor_width_m, 400, 1200)` and bound model/symbol/label identity geometry to `1.25 * display_scale_m` footprint and `2.0 * display_scale_m` height; model-defined influence zones are exempt.
- Desktop workbench acceptance only. Do not add mobile-specific code or verification.
- Do not stop or replace the existing main containers on ports `5173` and `8000`; only the feature containers on `5174` and `8001` may be rebuilt.

## File Structure

- Create `backend/app/scene3d/tactical_glyphs.py`: restricted geometry glyph set and crossed symbol/label groups.
- Create `backend/app/scene3d/units.py`: `UnitSpec`, influence zones, display options, validation, unit assembly, and structured omissions.
- Create `backend/tests/test_scene3d_units.py`: tactical unit defaults, transforms, hierarchy, bounds, labels, zones, and omission tests.
- Modify `backend/app/scene3d/exporter.py`: hierarchical `SceneNode`, PBR/unlit material contract, structured extension injection, and reload validation.
- Modify `backend/tests/test_scene3d_exporter.py`: hierarchy and `KHR_materials_unlit` serialization coverage.
- Modify `backend/app/scene3d/air_corridor.py`: migrate flat output to scene nodes and map threats to tactical units.
- Modify `backend/app/workers/air_corridor_task.py`: sample threat ground elevations and propagate omission warnings.
- Modify `backend/app/schemas/air_corridor.py`: type the additive tactical count and omission metadata.
- Modify `backend/tests/test_air_corridor_scene3d.py`: verify complete tactical hierarchies and removal of standalone threat nodes.
- Modify `backend/tests/test_air_corridor_task.py`: verify DEM anchoring and warning propagation.
- Modify `frontend/src/map/sceneGlbAsset.ts`: inherit parent semantics while flattening GLB meshes.
- Modify `frontend/src/map/sceneGlbAsset.test.ts`: test inherited unit identity and unchanged materials.
- Modify `frontend/src/map/sceneGlbLayer.ts`: add neutral baseline lighting to the shared custom scene.
- Modify `frontend/src/map/sceneGlbLayer.test.ts`: test light composition and lifecycle.
- Modify `docs/superpowers/specs/2026-07-15-tactical-scene3d-symbols-design.md`: record final implementation acceptance after real-artifact verification.

---

### Task 1: Hierarchical Scene Export And Semantic Materials

**Files:**
- Modify: `backend/app/scene3d/exporter.py`
- Modify: `backend/tests/test_scene3d_exporter.py`

**Interfaces:**
- Produces: `MaterialSpec(name, rgba, shading="pbr", emissive_rgb=None, double_sided=True)`.
- Produces: `SceneNode(name, mesh=None, material=None, transform=identity, extras={}, children=[])`.
- Preserves: legacy `export_glb(path, meshes, *, scene_metadata: dict, node_metadata: dict[str, dict])` calls until Task 3 migrates the air-corridor adapter.
- Adds: `export_glb(path, nodes, *, scene_metadata: dict)` for hierarchical callers.

- [ ] **Step 1: Write failing hierarchy and unlit tests**

Add tests that construct one group root and one mesh child, then inspect the GLB JSON rather than relying only on `trimesh.load`:

```python
def test_export_glb_keeps_hierarchy_and_unlit_material(tmp_path: Path) -> None:
    path = tmp_path / "scene.glb"
    root = SceneNode(
        name="unit_ad_01",
        extras={"kind": "unit", "unit_id": "ad-01"},
        children=[SceneNode(
            name="unit_ad_01_symbol",
            mesh=marker_mesh(numpy.zeros(3), 4),
            material=MaterialSpec(
                "symbol",
                (220, 48, 64, 255),
                shading="unlit",
                emissive_rgb=(110, 24, 32),
            ),
            extras={"kind": "unit_component", "role": "symbol_cross"},
        )],
    )
    export_glb(path, [root], scene_metadata={"schema_version": 1})
    document = glb_json(path)
    by_name = {node.get("name"): node for node in document["nodes"]}
    root_index = document["nodes"].index(by_name["unit_ad_01"])
    child_index = document["nodes"].index(by_name["unit_ad_01_symbol"])
    assert child_index in by_name["unit_ad_01"]["children"]
    assert by_name["unit_ad_01"]["extras"]["unit_id"] == "ad-01"
    assert document["extensionsUsed"] == ["KHR_materials_unlit"]
    material = next(item for item in document["materials"] if item["name"] == "symbol")
    assert material["extensions"]["KHR_materials_unlit"] == {}
    assert material["emissiveFactor"] == pytest.approx([110 / 255, 24 / 255, 32 / 255])
```

Also test that an unlit material without `emissive_rgb`, a mesh without a material, a group with no children, duplicate node names, non-finite transforms, and a node whose serialized hierarchy disappears all raise specific `ValueError`s.

- [ ] **Step 2: Run the tests and verify the new API is absent**

Run from the worktree root:

```powershell
docker run --rm -v "${PWD}\backend:/app" -w /app pygeomodel-glb-overlay-backend:latest pytest tests/test_scene3d_exporter.py -q
```

Expected: FAIL during import because `SceneNode` and the expanded `MaterialSpec` do not exist.

- [ ] **Step 3: Add the hierarchical exporter contract**

Implement these public types and validation rules in `exporter.py`:

```python
from dataclasses import dataclass, field
from typing import Literal

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
```

Normalize the legacy mesh dictionary into root `SceneNode`s. Recursively validate unique non-empty names, finite `4x4` transforms, mesh/material pairing, finite non-empty mesh geometry, and non-empty group children. Add groups with `scene.graph.update(frame_to=name, frame_from=parent, matrix=transform, metadata=extras)` and mesh nodes with `scene.add_geometry(node.mesh, node_name=node.name, geom_name=node.name, parent_node_name=parent, transform=node.transform, metadata=node.extras)`.

After `trimesh.exchange.gltf.export_glb`, modify the structured JSON chunk once. Preserve asset extras and node extras, then locate materials by `name`. For every unlit material, require `emissive_rgb`, set `extensions.KHR_materials_unlit = {}`, set normalized `emissiveFactor`, and append one sorted `KHR_materials_unlit` entry to `extensionsUsed`. Use `material.double_sided` when creating `PBRMaterial`.

- [ ] **Step 4: Run focused and legacy exporter tests**

```powershell
docker run --rm -v "${PWD}\backend:/app" -w /app pygeomodel-glb-overlay-backend:latest pytest tests/test_scene3d_exporter.py tests/test_air_corridor_scene3d.py -q
```

Expected: PASS; the existing flat air-corridor tests remain green.

- [ ] **Step 5: Commit the exporter foundation**

```powershell
git add backend/app/scene3d/exporter.py backend/tests/test_scene3d_exporter.py
git commit -m "feat: support tactical scene hierarchies"
```

---

### Task 2: Tactical Glyphs And Unit Assemblies

**Files:**
- Create: `backend/app/scene3d/tactical_glyphs.py`
- Create: `backend/app/scene3d/units.py`
- Create: `backend/tests/test_scene3d_units.py`
- Modify: `backend/app/scene3d/__init__.py`

**Interfaces:**
- Consumes: `SceneNode` and `MaterialSpec` from Task 1; `SceneFrame.to_gltf`; `annular_prism_mesh`.
- Produces: `InfluenceZoneSpec`, `UnitSpec`, `UnitDisplayOptions`, `UnitOmission`, and `build_unit_nodes(specs, frame, options)`.
- Produces: geometry-only crossed symbols and labels with no font, image, or external URI.

- [ ] **Step 1: Write failing tests for defaults, binding, geometry, and omissions**

Cover these exact outcomes in `test_scene3d_units.py`:

```python
def test_air_defense_unit_binds_all_components_to_one_root() -> None:
    nodes, omissions = build_unit_nodes([UnitSpec(
        unit_id="ad-05",
        unit_type="air_defense",
        position=(500_000, 3_500_000),
        altitude_amsl_m=5_900,
        heading_deg=45,
        status="active",
        short_label="AD-05",
        display_scale_m=800,
        warning_zone=InfluenceZoneSpec(0, 7_750, 0, 6_600),
        kill_zone=InfluenceZoneSpec(0, 4_500, 0, 6_600),
    )], frame())
    assert omissions == []
    root = nodes[0]
    assert root.name == "unit_ad-05"
    assert root.extras["display_scale_m"] == 800
    assert {child.extras["role"] for child in root.children} == {
        "model", "symbol_cross", "label_cross", "warning_zone", "kill_zone"
    }
```

Add tests proving: omitted type/status/heading become `unknown`/`unknown`/`0`; non-positive or non-finite `display_scale_m` is rejected as one omission; model/symbol/label bounds stay within the approved ratios while zones retain their configured radii and altitudes; both symbol planes exist at 90 degrees; all allowed label characters produce finite geometry; sanitization and deterministic fallback are stable; each display option removes its node and unused material; invalid coordinates or zones produce one `UnitOmission` and no root; duplicate normalized IDs raise a scene-level error.

- [ ] **Step 2: Run the new tests and verify the module is absent**

```powershell
docker run --rm -v "${PWD}\backend:/app" -w /app pygeomodel-glb-overlay-backend:latest pytest tests/test_scene3d_units.py -q
```

Expected: FAIL because `app.scene3d.units` does not exist.

- [ ] **Step 3: Implement the restricted geometry glyph layer**

In `tactical_glyphs.py`, define a complete literal glyph map whose keys are exactly `ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_`. Represent each glyph with a fixed 5-by-7 cell mask. Convert each occupied cell into a shallow `trimesh.creation.box`, merge cells per label, center the label, then duplicate and rotate it 90 degrees around local Y for `label_cross`.

Define `ALLOWED_LABEL_CHARACTERS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")`. Implement `sanitize_short_label(value: str | None, unit_id: str, index: int) -> str` by filtering the uppercase requested value to the allowed set and returning it only when its complete length is `1..8`; apply the same rule to the filtered unit ID, then fall back to `f"U{index + 1:02d}"`. Never truncate a longer candidate into a potentially duplicate label. Export the exact geometry entry points `crossed_label_nodes(label: str, scale_m: float) -> SceneNode`, `crossed_air_defense_symbol_nodes(scale_m: float) -> SceneNode`, and `crossed_unknown_symbol_nodes(scale_m: float) -> SceneNode`.

Use separate nested mesh nodes for light backplate, red threat border/glyph, dark label outline, and light label foreground. Assign unlit semantic materials to every glyph component. Assert glyph-map key equality at module load so missing characters fail immediately during tests.

- [ ] **Step 4: Implement unit validation and assembly**

In `units.py`, add these types:

```python
@dataclass(frozen=True)
class InfluenceZoneSpec:
    inner_radius_m: float
    outer_radius_m: float
    min_altitude_amsl_m: float
    max_altitude_amsl_m: float

@dataclass(frozen=True)
class UnitSpec:
    unit_id: str
    position: tuple[float, float]
    altitude_amsl_m: float
    display_scale_m: float
    unit_type: str | None = None
    heading_deg: float | None = None
    status: str | None = None
    short_label: str | None = None
    warning_zone: InfluenceZoneSpec | None = None
    kill_zone: InfluenceZoneSpec | None = None
    source: dict = field(default_factory=dict)

@dataclass(frozen=True)
class UnitDisplayOptions:
    model: bool = True
    symbol: bool = True
    label: bool = True
    warning_zone: bool = True
    kill_zone: bool = True

@dataclass(frozen=True)
class UnitOmission:
    unit_id: str
    reason: str
```

Implement `build_unit_nodes(specs, frame, options=UnitDisplayOptions()) -> tuple[list[SceneNode], list[UnitOmission]]`. Normalize heading with `% 360`, translate the parent to `frame.to_gltf((east, north, ground_altitude))`, and apply clockwise heading as local Y rotation. Build child geometry in local coordinates. Zone bottom/top Y values are absolute zone altitudes minus ground altitude. Catch unit validation/geometry errors into `UnitOmission`, but preflight empty or normalization-colliding IDs and raise before building any units.

Use a neutral generic low-detail body for `unknown` and a low-detail launcher/radar assembly for `air_defense`. Record `kind`, `unit_id`, `unit_type`, `status`, `display_scale_m`, and source metadata on the root; record the same identity plus `role` on each direct child.

- [ ] **Step 5: Run tactical unit and primitive tests**

```powershell
docker run --rm -v "${PWD}\backend:/app" -w /app pygeomodel-glb-overlay-backend:latest pytest tests/test_scene3d_units.py tests/test_scene3d_primitives.py -q
```

Expected: PASS with finite geometry and no external asset dependency.

- [ ] **Step 6: Commit the reusable tactical kernel**

```powershell
git add backend/app/scene3d/tactical_glyphs.py backend/app/scene3d/units.py backend/app/scene3d/__init__.py backend/tests/test_scene3d_units.py
git commit -m "feat: add reusable tactical unit assemblies"
```

---

### Task 3: Air-Corridor Tactical Scene Integration

**Files:**
- Modify: `backend/app/scene3d/air_corridor.py`
- Modify: `backend/app/workers/air_corridor_task.py`
- Modify: `backend/app/schemas/air_corridor.py`
- Modify: `backend/tests/test_air_corridor_scene3d.py`
- Modify: `backend/tests/test_air_corridor_task.py`

**Interfaces:**
- Consumes: `build_unit_nodes`, `UnitSpec`, and `InfluenceZoneSpec` from Task 2.
- Changes: `write_air_corridor_glb(path: Path, *, task_id: str, target_epsg: int, path_points: list[ProjectedPoint], sample_features: list[dict], prepared_threat_xy: dict[str, tuple[float, float]], threat_ground_elevations_m: dict[str, float | None], start_ground_elevation_m: float, end_ground_elevation_m: float, payload: AirCorridorPlanningRequest, route_found: bool) -> dict`.
- Produces: additive `scene3d.tactical_unit_count` and `scene3d.omitted_units` metadata plus matching task warnings.

- [ ] **Step 1: Replace standalone-zone expectations with failing tactical hierarchy tests**

Update every `write_air_corridor_glb` test call with finite threat ground mappings. Assert direct-child roles by resolving each root's JSON `children` indices:

```python
assert metadata["tactical_unit_count"] == 2
assert metadata["omitted_units"] == []
for unit_id in ("a", "b"):
    root = nodes_by_name[f"unit_{unit_id}"]
    roles = {document["nodes"][index]["extras"]["role"] for index in root["children"]}
    assert roles == {"model", "symbol_cross", "label_cross", "warning_zone", "kill_zone"}
assert "threat_a_warning" not in nodes_by_name
```

Add a test with ground altitude `6_100` and influence minimum altitude `0` that verifies the model parent is anchored at `6_100` AMSL while the zone still spans the original absolute interval. Add an invalid `None` ground sample test that expects one omission, one warning metadata entry, and no partial `unit_<id>` root.
Add a multi-threat test with long shared-name prefixes that expects distinct
`AD-01` and `AD-02` labels and verifies each root `source` retains the complete
original threat fields.

- [ ] **Step 2: Run focused air-corridor tests and verify the signature mismatch**

```powershell
docker run --rm -v "${PWD}\backend:/app" -w /app pygeomodel-glb-overlay-backend:latest pytest tests/test_air_corridor_scene3d.py tests/test_air_corridor_task.py -q
```

Expected: FAIL because tactical hierarchy metadata and `threat_ground_elevations_m` are absent.

- [ ] **Step 3: Sample threat ground elevations in the worker**

Add a side-effect-free helper beside `_value_at`:

```python
def _threat_ground_elevations(dem, transform, nodata, prepared, payload):
    values: dict[str, float | None] = {}
    for threat in payload.threats:
        rc = _xy_to_rc(transform, *prepared.threat_xy[threat.id])
        if not _is_inside(dem.shape, rc):
            values[threat.id] = None
            continue
        value = float(dem[rc])
        values[threat.id] = None if (
            not numpy.isfinite(value) or (nodata is not None and value == nodata)
        ) else value
    return values
```

Call it while the projected DEM array and transform are already loaded, then pass the mapping to `write_air_corridor_glb`. Do not reopen or reproject the DEM.

- [ ] **Step 4: Migrate air-corridor scene construction**

Replace the flat `meshes`/`node_metadata` dictionaries with root `SceneNode`s. Keep route, ribbon, grouped risks, start, and end as root mesh nodes. Mark their existing semantic materials `unlit` and provide explicit emissive fallback colors.

For each threat, create this mapping, where `index` is its zero-based request
order and `sanitized_name` is the allowed-character form of `threat.name` only
when its complete length is at most eight:

```python
UnitSpec(
    unit_id=threat.id,
    unit_type="air_defense",
    position=prepared_threat_xy[threat.id],
    altitude_amsl_m=threat_ground_elevations_m.get(threat.id, float("nan")),
    heading_deg=0,
    status="active",
    short_label=sanitized_name or f"AD-{index + 1:02d}",
    display_scale_m=min(1200.0, max(400.0, payload.planning.corridor_width_m)),
    warning_zone=InfluenceZoneSpec(
        threat.min_range_m,
        threat.warning_zone_radius_m or threat.max_range_m,
        threat.min_altitude_m,
        threat.max_altitude_m,
    ),
    kill_zone=InfluenceZoneSpec(
        threat.min_range_m,
        threat.kill_zone_radius_m or threat.max_range_m * 0.7,
        threat.min_altitude_m,
        threat.max_altitude_m,
    ),
    source=threat.model_dump(),
)
```

Include finite ground anchor points when creating `SceneFrame`. Append accepted unit roots once, never emit the old `_add_threat_meshes` nodes, and serialize omissions as dictionaries. Add `tactical_unit_count` and `omitted_units` to scene metadata.

- [ ] **Step 5: Type and propagate additive omission metadata**

Add a Pydantic omission type and fields:

```python
class Scene3dUnitOmission(BaseModel):
    unit_id: str
    reason: str

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
    tactical_unit_count: int = 0
    omitted_units: list[Scene3dUnitOmission] = Field(default_factory=list)
```

In `_write_air_corridor_outputs`, derive warnings as
`Scene3D omitted unit '<id>': <reason>`, write the same list to model metadata and manifest, and return it so the task store exposes it. Keep artifact-level exceptions on the existing staging rollback path.

- [ ] **Step 6: Run the backend scene and worker suites**

```powershell
docker run --rm -v "${PWD}\backend:/app" -w /app pygeomodel-glb-overlay-backend:latest pytest tests/test_scene3d_exporter.py tests/test_scene3d_units.py tests/test_air_corridor_scene3d.py tests/test_air_corridor_task.py -q
```

Expected: PASS; route-found, route-not-found, unit omission, metadata, warnings, and rollback cases are green.

- [ ] **Step 7: Commit the air-corridor integration**

```powershell
git add backend/app/scene3d/air_corridor.py backend/app/workers/air_corridor_task.py backend/app/schemas/air_corridor.py backend/tests/test_air_corridor_scene3d.py backend/tests/test_air_corridor_task.py
git commit -m "feat: export tactical air corridor units"
```

---

### Task 4: Frontend Semantic Preservation And Baseline Light

**Files:**
- Modify: `frontend/src/map/sceneGlbAsset.ts`
- Modify: `frontend/src/map/sceneGlbAsset.test.ts`
- Modify: `frontend/src/map/sceneGlbLayer.ts`
- Modify: `frontend/src/map/sceneGlbLayer.test.ts`

**Interfaces:**
- Produces: `inheritedUserData(object, root)` used during geographic flattening.
- Produces: `createSceneGlbLights() -> THREE.Group` used once per custom-layer scene.
- Preserves: original mesh material objects, textures, effective parent visibility, names, disposal, and existing map-layer lifecycle.

- [ ] **Step 1: Write failing inherited-semantics and lighting tests**

Add a parent group with unit extras and a child mesh with role extras:

```ts
const unit = new THREE.Group();
unit.userData = { kind: "unit", unit_id: "ad-05", status: "active" };
const material = new THREE.MeshStandardMaterial({ color: 0x777777 });
const mesh = new THREE.Mesh(new THREE.BoxGeometry(), material);
mesh.userData = { kind: "unit_component", role: "model" };
unit.add(mesh);
root.add(unit);
const asset = prepareStaticScene(root, metadata, []);
const flattened = asset.group.children[0] as THREE.Mesh;
expect(flattened.userData).toMatchObject({ unit_id: "ad-05", role: "model" });
expect(flattened.material).toBe(material);
```

Test `createSceneGlbLights()` returns exactly one `HemisphereLight` and one `DirectionalLight`, both neutral, with the directional light positioned above and off-axis. Verify adding/removing a layer still disposes the GLB asset exactly once and does not dispose shared material resources twice.

- [ ] **Step 2: Run focused frontend tests and verify failure**

```powershell
Set-Location frontend
npm test -- --run src/map/sceneGlbAsset.test.ts src/map/sceneGlbLayer.test.ts
Set-Location ..
```

Expected: FAIL because parent unit extras are dropped and `createSceneGlbLights` does not exist.

- [ ] **Step 3: Preserve inherited node semantics during flattening**

Implement a root-to-leaf merge where child keys win:

```ts
export function inheritedUserData(object: THREE.Object3D, root: THREE.Object3D) {
  const chain: THREE.Object3D[] = [];
  for (let current: THREE.Object3D | null = object; current; current = current.parent) {
    chain.push(current);
    if (current === root) break;
  }
  return Object.assign({}, ...chain.reverse().map((item) => item.userData));
}
```

Use this value for each flattened mesh. Leave geometry projection, material identity, texture collection, visibility, names, and render order unchanged.

- [ ] **Step 4: Add restrained baseline light**

Implement and export:

```ts
export function createSceneGlbLights() {
  const lights = new THREE.Group();
  lights.name = "scene-glb-baseline-lights";
  const hemisphere = new THREE.HemisphereLight(0xffffff, 0x52606b, 1.35);
  const directional = new THREE.DirectionalLight(0xffffff, 1.6);
  directional.position.set(0.6, 1, 0.4);
  lights.add(hemisphere, directional);
  return lights;
}
```

Add the group to the custom Three.js scene immediately before `asset.group`. Do not inspect node names, replace materials, add an animation loop, or change terrain/layer ordering.

- [ ] **Step 5: Run frontend tests and production build**

```powershell
Set-Location frontend
npm test -- --run src/map/sceneGlbAsset.test.ts src/map/sceneGlbLayer.test.ts
npm run build
Set-Location ..
```

Expected: 16 or more focused tests pass and `vue-tsc -b && vite build` exits `0`.

- [ ] **Step 6: Commit the frontend renderer compatibility work**

```powershell
git add frontend/src/map/sceneGlbAsset.ts frontend/src/map/sceneGlbAsset.test.ts frontend/src/map/sceneGlbLayer.ts frontend/src/map/sceneGlbLayer.test.ts
git commit -m "fix: render tactical glb materials clearly"
```

---

### Task 5: Full Regression And Real Artifact Acceptance

**Files:**
- Modify after acceptance: `docs/superpowers/specs/2026-07-15-tactical-scene3d-symbols-design.md`
- Do not commit generated GLBs, screenshots, task records, Docker metadata, or visualization workspace files.

**Interfaces:**
- Consumes: all Tasks 1 through 4.
- Produces: one newly generated accepted air-corridor task, desktop visual evidence, and final design status.

- [ ] **Step 1: Run complete backend and frontend verification**

```powershell
docker run --rm -v "${PWD}\backend:/app" -w /app pygeomodel-glb-overlay-backend:latest pytest -q
Set-Location frontend
npm test
npm run build
Set-Location ..
```

Expected: every backend test and frontend test passes with zero failures; the production build exits `0`.

- [ ] **Step 2: Rebuild and restart only feature containers**

```powershell
docker build -f backend/Dockerfile -t pygeomodel-glb-overlay-backend:latest .
docker build -f frontend/Dockerfile -t pygeomodel-glb-overlay-frontend:latest --build-arg VITE_API_BASE=/PyGeoModel --build-arg VITE_BASE_PATH=/PyGeoModel/ --build-arg VITE_PROXY_TARGET=http://pygeomodel-glb-overlay-backend:8000 .
docker rm -f pygeomodel-glb-overlay-frontend pygeomodel-glb-overlay-backend
docker run -d --name pygeomodel-glb-overlay-backend --network pygeomodel-glb-overlay-net -p 127.0.0.1:8001:8000 -e PYGEOMODEL_DATA_DIR=/workspace/data -v "E:\Github\PyGeoModel\data:/workspace/data" pygeomodel-glb-overlay-backend:latest
docker run -d --name pygeomodel-glb-overlay-frontend --network pygeomodel-glb-overlay-net -p 127.0.0.1:5174:5173 pygeomodel-glb-overlay-frontend:latest
Invoke-RestMethod http://127.0.0.1:8001/api/health
```

Expected: health response reports success; main containers on `5173` and `8000` remain running.

- [ ] **Step 3: Submit the enlarged accepted air-corridor request**

```powershell
$scenarioPath = 'E:\Github\PyGeoModel\data\demo-scenarios\dem_20260713_080113_884937cf\air-corridor.json'
$scenario = Get-Content -Raw $scenarioPath | ConvertFrom-Json
$task = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8001/api/air-corridor/planning' -ContentType 'application/json' -Body ($scenario.request | ConvertTo-Json -Depth 20)
$taskId = $task.task_id
do {
  Start-Sleep -Seconds 3
  $detail = Invoke-RestMethod "http://127.0.0.1:8001/api/air-corridor/planning/$taskId"
} while ($detail.status -in @('pending', 'running'))
$detail | ConvertTo-Json -Depth 20
```

Expected: status is `finished`, `warnings` is empty for the accepted demo, and `scene_glb` exists.

- [ ] **Step 4: Inspect the self-contained GLB contract**

```powershell
$glb = "data/outputs/$taskId/air_corridor_result.glb"
docker run --rm -v "${PWD}:/workspace" -v "E:\Github\PyGeoModel\data:/workspace/data" -w /workspace pygeomodel-glb-overlay-backend:latest python scripts/inspect_glb.py $glb --max-bytes 50000000
```

Expected from `inspect_glb.py`: `valid=true`, `tactical_unit_count` equals the request threat count, `omitted_units=[]`, and size remains below `50,000,000` bytes. Separately inspect all JSON nodes, including group-only nodes, and confirm every `unit_<id>` root exists, `KHR_materials_unlit` appears once in `extensionsUsed`, every semantic material has the extension and emissive fallback, each unit root owns the five expected direct-child roles, and no old standalone `threat_<id>_warning|kill` node remains.

- [ ] **Step 5: Perform independent and workbench desktop visual acceptance**

Create a temporary standalone Three.js GLTFLoader page in the visualization workspace, outside the repository. It must contain only an orbit camera, neutral lights, a solid neutral background, and the generated GLB; it must not import PyGeoModel map or workbench code. Verify from four horizontal bearings that the body, crossed symbol, and short ID remain attached and recognizable, and that no semantic geometry is black.

Then open `http://127.0.0.1:5174/PyGeoModel/`, select the new task, manually enable its `3D result`, and focus it over the DEM. At `1440x900`, capture a screenshot and run canvas pixel checks proving terrain and non-black green/amber/orange/red/light tactical pixels are simultaneously present. Pan, zoom, pitch, and rotate; confirm the GLB remains aligned, terrain exaggeration is `1.0`, no text or controls overlap, the browser console is clean, and no resource request fails.

Expected: both the standalone viewer and workbench satisfy every real-artifact criterion in the approved spec.

- [ ] **Step 6: Record acceptance and commit documentation**

After Steps 1 through 5 pass, obtain the date with `Get-Date -Format yyyy-MM-dd` and change the design status to `Implemented and accepted on YYYY-MM-DD`, substituting that command's returned value. Include the accepted task ID and final backend/frontend test counts. Then run:

```powershell
git add docs/superpowers/specs/2026-07-15-tactical-scene3d-symbols-design.md
git commit -m "docs: record tactical scene acceptance"
git status --short --branch
```

Expected: the acceptance commit succeeds and the worktree has no uncommitted implementation changes.

## Final Review Gate

Before integration, invoke `superpowers:requesting-code-review`. Review the complete branch diff against `docs/superpowers/specs/2026-07-15-tactical-scene3d-symbols-design.md`, resolve findings through `superpowers:receiving-code-review`, rerun Task 5 Step 1 after every fix, and use `superpowers:verification-before-completion` before claiming success or pushing.
