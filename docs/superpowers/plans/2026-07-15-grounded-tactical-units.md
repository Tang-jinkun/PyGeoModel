# Grounded Tactical Units Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace oversized point-anchored air-defense vehicles with terrain-fitted, truthfully exaggerated tactical units containing a visible model, ground anchor, dashed leader, symbol, label, and readable threat volumes in a portable GLB.

**Architecture:** Add a focused terrain-grounding module that samples the original COG and returns a validated local plane, then separate scene-wide display profile derivation from physical vehicle dimensions. Unit roots remain translation-only; terrain orientation applies only to the model and ground anchor, while leaders, symbols, labels, and threat volumes remain globally upright. The air-corridor worker supplies terrain anchors to the existing atomic GLB export transaction.

**Tech Stack:** Python 3.12, NumPy, Rasterio, PyProj, trimesh 4.12.2, pytest, Vue 3, Three.js, Vitest, Docker, Playwright.

## Global Constraints

- Preserve real unit coordinates, elevations, headings, route coordinates, route AGL/AMSL altitudes, warning/kill radii, and warning/kill altitude limits.
- Physical vehicle reference dimensions are `12 x 3.2 m`, with `2.8 m` chassis height and `7.5 m` equipment top.
- Vehicle exaggeration is exactly `clamp(scene_extent_m / 6000, 10, 15)` and is independent of corridor width.
- Symbol scale is exactly `clamp(display_vehicle_length_m * 2.2, 260, 400)` metres.
- Terrain fitting uses nine bilinear samples from the original COG; accepted demo units require slope `<=15 degrees`, RMSE `<=5 m`, maximum absolute residual `<=8 m`, and no nodata samples.
- Ground clearance is exactly `0.75 m` in display space and is not exaggerated.
- Each emitted unit root owns the seven direct roles `ground_anchor`, `model`, `leader`, `symbol_cross`, `label_cross`, `warning_zone`, and `kill_zone`.
- The leader has seven intervals and four merged dash segments; dash radius is `clamp(symbol_scale_m * 0.008, 2, 4)` metres.
- Warning fill alpha is `20/255`; kill fill alpha is `31/255`; zone bottoms are clipped to local ground without changing requested metadata.
- GLB metadata records actual/display dimensions, exaggeration, terrain anchor values, clearance, and symbol scale.
- Existing finished tasks are not migrated; existing GLBs remain loadable.
- The GLB remains self-contained, targets `<15 MB`, and never exceeds `50,000,000` bytes.
- Desktop acceptance only; do not add mobile work.

---

### Task 1: Original-DEM Terrain Anchors And Display Profile

**Files:**
- Create: `backend/app/scene3d/grounding.py`
- Modify: `backend/app/scene3d/units.py`
- Test: `backend/tests/test_scene3d_grounding.py`
- Test: `backend/tests/test_scene3d_units.py`

**Interfaces:**
- Produces `TerrainAnchor`, `UnitDimensions`, and `UnitDisplayProfile` immutable dataclasses.
- Produces `derive_air_defense_display_profile(scene_extent_m: float) -> UnitDisplayProfile`.
- Produces `sample_terrain_anchor(dem_path: Path, target_epsg: int, position_xy: tuple[float, float], heading_deg: float, footprint_length_m: float, footprint_width_m: float) -> TerrainAnchor`.
- `TerrainAnchor` contains `ground_elevation_amsl_m`, `normal_enu`, `slope_deg`, `fit_rmse_m`, and `max_residual_m`.

- [ ] **Step 1: Write failing display-profile tests**

Add tests proving the exact clamp and independence from corridor width:

```python
def test_display_profile_uses_scene_extent_clamp() -> None:
    assert derive_air_defense_display_profile(60_000).exaggeration == 10
    assert derive_air_defense_display_profile(72_000).exaggeration == 12
    assert derive_air_defense_display_profile(120_000).exaggeration == 15
    assert derive_air_defense_display_profile(72_000).display_dimensions_m.length == 144
    assert derive_air_defense_display_profile(72_000).symbol_scale_m == pytest.approx(316.8)
```

- [ ] **Step 2: Run the profile tests and verify RED**

Run:

```powershell
Set-Location backend
E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pytest tests/test_scene3d_units.py -k "display_profile" -q
```

Expected: collection/import failure because the profile API does not exist.

- [ ] **Step 3: Implement immutable dimensions and profile derivation**

Use these public shapes:

```python
@dataclass(frozen=True)
class UnitDimensions:
    length: float
    width: float
    chassis_height: float
    equipment_top: float

@dataclass(frozen=True)
class UnitDisplayProfile:
    actual_dimensions_m: UnitDimensions
    display_dimensions_m: UnitDimensions
    exaggeration: float
    symbol_scale_m: float

def derive_air_defense_display_profile(scene_extent_m: float) -> UnitDisplayProfile:
    exaggeration = min(15.0, max(10.0, scene_extent_m / 6000.0))
    actual = UnitDimensions(12.0, 3.2, 2.8, 7.5)
    displayed = UnitDimensions(*(value * exaggeration for value in astuple(actual)))
    symbol_scale = min(400.0, max(260.0, displayed.length * 2.2))
    return UnitDisplayProfile(actual, displayed, exaggeration, symbol_scale)
```

- [ ] **Step 4: Write failing flat, sloped, nodata, and rough-plane tests**

Create small GeoTIFF fixtures that prove:

```python
anchor = sample_terrain_anchor(path, 32644, (500_000, 3_500_000), 25, 144, 38.4)
assert anchor.ground_elevation_amsl_m == pytest.approx(expected_center, abs=0.01)
assert anchor.slope_deg == pytest.approx(expected_slope, abs=0.1)
assert anchor.fit_rmse_m <= 0.01
assert anchor.max_residual_m <= 0.01
```

Nodata in any of the nine samples must raise `ValueError` containing `terrain sample`. Non-planar fixtures must report measured RMSE/max residual rather than silently clamping them.

- [ ] **Step 5: Run grounding tests and verify RED**

Run:

```powershell
E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pytest tests/test_scene3d_grounding.py -q
```

Expected: import failure because `grounding.py` does not exist.

- [ ] **Step 6: Implement original-COG bilinear sampling and plane fitting**

Implementation requirements:

```python
@dataclass(frozen=True)
class TerrainAnchor:
    ground_elevation_amsl_m: float
    normal_enu: tuple[float, float, float]
    slope_deg: float
    fit_rmse_m: float
    max_residual_m: float
```

Rotate the `3 x 3` offsets by heading in target projected coordinates,
transform each sample to the source DEM CRS, bilinearly interpolate the four
surrounding source pixels, fit `z = ax + by + c` with `numpy.linalg.lstsq`, and
derive the normalized ENU normal `(-a, -b, 1)`. Do not substitute nodata or use
the planning raster.

- [ ] **Step 7: Run focused tests and commit**

Run:

```powershell
E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pytest tests/test_scene3d_grounding.py tests/test_scene3d_units.py -q
```

Expected: all focused tests pass.

Commit:

```powershell
git add backend/app/scene3d/grounding.py backend/app/scene3d/units.py backend/tests/test_scene3d_grounding.py backend/tests/test_scene3d_units.py
git commit -m "feat: derive grounded tactical display profiles"
```

---

### Task 2: Grounded Vehicle, Dashed Leader, And Readable Threat Volumes

**Files:**
- Modify: `backend/app/scene3d/units.py`
- Modify: `backend/app/scene3d/tactical_glyphs.py`
- Modify: `backend/app/scene3d/primitives.py`
- Test: `backend/tests/test_scene3d_units.py`
- Test: `backend/tests/test_scene3d_primitives.py`

**Interfaces:**
- Extends `UnitSpec` with `terrain_anchor: TerrainAnchor` and `display_profile: UnitDisplayProfile`.
- Keeps `build_unit_nodes(...) -> tuple[list[SceneNode], list[UnitOmission]]`.
- Produces `dashed_vertical_leader_mesh(...)` and zone boundary meshes.

- [ ] **Step 1: Write failing seven-role and transform-isolation tests**

Assert one valid root has exactly:

```python
assert {child.extras["role"] for child in root.children} == {
    "ground_anchor", "model", "leader", "symbol_cross", "label_cross",
    "warning_zone", "kill_zone",
}
```

Use a sloped `TerrainAnchor` and assert the root, leader, symbol, label, and
zones remain globally upright while the model and anchor have non-identity
slope transforms. Assert the root translation includes exactly `0.75 m`
clearance, not `0.75 * exaggeration`.

- [ ] **Step 2: Run unit tests and verify RED**

Run:

```powershell
E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pytest tests/test_scene3d_units.py -k "seven_roles or transform_isolation or clearance" -q
```

Expected: failures because the new roles and isolated transforms are absent.

- [ ] **Step 3: Implement the procedural vehicle and isolated transforms**

Build a generic air-defense vehicle from displayed dimensions with semantic
children for chassis, left/right tracks, cabin, launcher, mast, and panel.
Keep the unit root translation-only. Apply heading plus fitted pitch/roll to
the model child; align the ground ring to the fitted plane; keep all tactical
and zone children globally upright.

- [ ] **Step 4: Write failing dashed-leader and threat-style tests**

Assert the leader contains four dashes from seven intervals, has one merged
mesh, uses an unlit neutral material, and remains visible as geometry from
orthogonal bearings. Assert fill alpha values are exactly `20` and `31` and
zone bottom altitude is `max(requested_min, ground)` while metadata preserves
both values. Assert top/bottom rings and four vertical strokes exist.

- [ ] **Step 5: Run geometry tests and verify RED**

Run:

```powershell
E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pytest tests/test_scene3d_units.py tests/test_scene3d_primitives.py -k "leader or zone or boundary" -q
```

Expected: failures for missing leader/boundary geometry and old material alpha.

- [ ] **Step 6: Implement leader, symbol placement, anchor, and zone styling**

Use the exact formulas from Global Constraints. Merge leader dashes per unit,
place the symbol lower edge above the leader gap, place the label `0.06 *
symbol_scale_m` above the symbol, and include actual/display/terrain metadata
on the root. Clip only display geometry; never rewrite requested zone values.

- [ ] **Step 7: Run focused tests and commit**

Run:

```powershell
E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pytest tests/test_scene3d_units.py tests/test_scene3d_primitives.py -q
```

Expected: all focused tests pass.

Commit:

```powershell
git add backend/app/scene3d/units.py backend/app/scene3d/tactical_glyphs.py backend/app/scene3d/primitives.py backend/tests/test_scene3d_units.py backend/tests/test_scene3d_primitives.py
git commit -m "feat: ground and connect tactical units"
```

---

### Task 3: Air-Corridor Integration, Demo Placement, And Fast Visual Acceptance

**Files:**
- Modify: `backend/app/workers/air_corridor_task.py`
- Modify: `backend/app/scene3d/air_corridor.py`
- Modify: `backend/app/demo_scenarios/terrain.py`
- Modify: `backend/app/demo_scenarios/route_builders.py`
- Test: `backend/tests/test_air_corridor_task.py`
- Test: `backend/tests/test_air_corridor_scene3d.py`
- Test: `backend/tests/test_demo_scenario_terrain.py`
- Test: `backend/tests/test_demo_route_builders.py`
- Test: `frontend/src/map/sceneGlbAsset.test.ts`

**Interfaces:**
- Replaces `threat_ground_elevations_m` with `threat_terrain_anchors` in `write_air_corridor_glb`.
- Adds a deterministic nearest-valid-flat-cell helper to `TerrainGrid` for demo threat placement.
- Keeps API response, output filename, task metadata schema version, and frontend loading contract backward compatible.

- [ ] **Step 1: Write failing integration tests**

Cover these behaviors:

```python
assert metadata["display_profile"]["exaggeration"] == expected
assert metadata["tactical_unit_count"] == 10
assert metadata["omitted_units"] == []
assert all(required_role in roles for required_role in seven_roles)
assert root_extras["terrain_fit_rmse_m"] <= 5
assert root_extras["terrain_max_residual_m"] <= 8
```

Worker tests must prove the original COG path is used for anchors and that an
anchor failure reaches task warnings/omissions without partial unit geometry.

- [ ] **Step 2: Write failing deterministic flat-placement tests**

Add `TerrainGrid.nearest_flat(origin, search_radius, max_slope_deg,
max_relief_m)` tests proving deterministic selection, valid offsets, and
failure when no candidate satisfies `15 degrees` and `8 m` local relief.

- [ ] **Step 3: Run integration tests and verify RED**

Run:

```powershell
E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pytest tests/test_air_corridor_task.py tests/test_air_corridor_scene3d.py tests/test_demo_scenario_terrain.py tests/test_demo_route_builders.py -q
```

Expected: failures for old anchor input, five-role hierarchy, and unfiltered
demo threat offsets.

- [ ] **Step 4: Integrate source DEM anchors and deterministic demo placement**

Retain the original DEM path in `PreparedAirCorridorDem`, derive scene extent
from start/end/path/emitted unit positions, sample anchors from the original
COG, and pass anchors/profile into scene export. For the demo, treat each
existing threat offset as a target and select the nearest deterministic flat
cell within a bounded search radius while preserving ten spatially separated
threats and the enlarged `80-120 km` scenario span.

- [ ] **Step 5: Update metadata, reload, and frontend compatibility tests**

Assert additive metadata is inherited by prepared Three.js meshes and existing
schema-version-1 GLBs without the new fields still load. Do not add frontend
geometry corrections.

- [ ] **Step 6: Run full automated verification and commit**

Run:

```powershell
Set-Location backend
E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pytest -q
Set-Location ..\frontend
npm test
npm run build
Set-Location ..
```

Expected: zero failures; the existing deprecation and Vite chunk-size warnings
may remain documented.

Commit:

```powershell
git add backend frontend/src/map/sceneGlbAsset.test.ts
git commit -m "feat: export terrain-grounded air corridor units"
```

- [ ] **Step 7: Rebuild only feature containers and generate a new task**

Rebuild and replace `pygeomodel-glb-overlay-backend` on `8001` and
`pygeomodel-glb-overlay-frontend` on `5174`. Keep main `5173/8000` containers
running. Regenerate the air-corridor scenario, submit it, and require
`status=finished`, `warnings=[]`, ten tactical roots, and no omissions.

- [ ] **Step 8: Capture the fast visual comparison**

At `1440 x 900`, reproduce the user's top-oblique and low-side views. Also
capture four standalone horizontal bearings. Verify vehicle contact, readable
vehicle structure, visible dashed leaders, attached labels/symbols, reduced
zone occlusion, terrain exaggeration `1`, clean console/network checks, and no
control overlap. Save evidence outside the repository.

- [ ] **Step 9: Record acceptance and commit documentation**

Update the design status with the new task ID, GLB size/hash, test counts, unit
count, terrain-fit ranges, and evidence path. Do not commit generated GLBs,
screenshots, task records, Docker metadata, `dist`, or visualization files.

