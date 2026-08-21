# Radar Terrain Blocked Volume Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic red terrain-occluded volumes to single-radar and multi-radar GLBs without changing public radar task interfaces.

**Architecture:** Reuse the existing single-radar DEM height-field builder, retaining nominal and visible lower surfaces so it can emit independent green and red meshes. Extend the existing fixed-height multi-radar fusion masks with a theoretical-union mask, and keep cooperative intersection strictly green. Mark red GLB nodes with semantic extras and make the frontend preserve those materials during user color changes.

**Tech Stack:** Python 3, NumPy, rasterio, trimesh/GLB exporter, pytest, Vue 3, Three.js, Vitest, TypeScript.

## Global Constraints

- Do not add radar API parameters or change task creation, task query, or artifact download interfaces.
- Red means deterministic terrain occlusion only; never mark DEM NoData, DEM external, or indeterminate regions red.
- Use the existing single-radar DEM window/projection/height field and existing multi-radar fixed fusion heights.
- Aggregate red is valid only when every requested radar completed; partial tasks must not create deterministic joint red.
- Cooperative intersection remains common visible green coverage only.
- Preserve existing uncommitted user changes; do not reset or overwrite them.

---

### Task 1: Single-radar split height-field volume

**Files:**
- Modify: `backend/app/scene3d/radar_volume.py`
- Test: `backend/tests/test_radar_volume.py`

**Interfaces:**
- `build_radar_visibility_envelope(...)` continues returning `RadarVisibilityVolume`.
- The return value gains optional green/red mesh arrays and counts while retaining existing constructor compatibility.
- `build_height_field_envelope_mesh(...)` remains the shared height-field mesh builder.

- [ ] **Step 1: Write failing tests** for flat DEM no red, positive minimum-visible-height red bounds above terrain, range/sector/NoData filtering, and red-only valid output.
- [ ] **Step 2: Run the focused tests** with `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_radar_volume.py -q`; confirm failures are caused by missing blocked fields/logic.
- [ ] **Step 3: Implement minimal split calculation**: compute `nominal_lower`, `visible_lower`, `nominal_upper`; create independently valid green and blocked masks; keep NoData/analysis/range/sector/elevation masks; use a tiny boundary gap only where both meshes coexist.
- [ ] **Step 4: Populate diagnostics** with theoretical/green/red cell counts, calculation lower/upper bounds, and boundary gap; return empty arrays rather than fabricated red data when no surface cell exists.
- [ ] **Step 5: Run focused and existing volume tests** and keep all green.

### Task 2: Single-radar GLB nodes and metadata

**Files:**
- Modify: `backend/app/scene3d/radar.py`
- Test: `backend/tests/test_radar_scene3d.py`

**Interfaces:**
- `write_radar_coverage_glb(...)` continues returning scene metadata and writing the same `scene_glb` artifact.
- New node: `radar_result/blocked_volume` with extras `kind=blocked_volume` and `visibility_semantics=terrain_occluded`.

- [ ] **Step 1: Write failing GLB tests** for independent green/red nodes, red material metadata, red-only export, and statistics/boundaries in scene metadata.
- [ ] **Step 2: Run those tests** with `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_radar_scene3d.py -q`; confirm the new node and metadata are absent.
- [ ] **Step 3: Add the red material and dynamic scene-node construction**; include both green/red vertices in the scene frame and avoid visual-dome fallback when a valid red-only envelope exists.
- [ ] **Step 4: Add metadata** for red availability, face/cell counts, calculation bounds, and unknown/NoData diagnostics while preserving existing keys.
- [ ] **Step 5: Run radar scene tests and inspect serialized node names/material factors.**

### Task 3: Multi-radar aggregate theoretical union

**Files:**
- Modify: `backend/app/services/multi_radar_fusion_volume.py`
- Modify: `backend/app/workers/multi_radar_coverage_task.py`
- Test: `backend/tests/test_multi_radar_fusion_volume.py`
- Test: `backend/tests/test_multi_radar_coverage_task.py`

**Interfaces:**
- `FusionHeightCounts` gains optional `theoretical_union: numpy.ndarray | None` with the same `[z,y,x]` shape as `coverage_count`.
- `write_multi_radar_fusion_glb(...)` emits `multi_radar_fusion/blocked_volume` only when `theoretical_union` is supplied.
- `StationEvaluation` gains optional `fusion_theoretical_masks` while existing evaluator fixtures remain valid.

- [ ] **Step 1: Write failing tests** for `theoretical_union && coverage_count == 0`, node extras/material, and partial-task suppression.
- [ ] **Step 2: Run focused fusion/task tests** and confirm the red node and mask aggregation are missing.
- [ ] **Step 3: Implement fusion mask propagation** by returning visible and theoretical fixed-height masks per station, OR-ing theoretical masks only for complete tasks, and passing `None` for partial tasks.
- [ ] **Step 4: Implement fusion GLB red mesh/metadata** while preserving union, overlap, and triple-overlap nodes and allowing red-only output.
- [ ] **Step 5: Add the partial warning to the task message and run all multi-radar tests.**

### Task 4: Frontend semantic rendering compatibility

**Files:**
- Modify: `frontend/src/map/sceneGlbAsset.ts`
- Modify: `frontend/src/map/sceneGlbLayer.ts`
- Test: `frontend/src/map/sceneGlbAsset.test.ts`
- Test: `frontend/src/map/sceneGlbLayer.test.ts`

**Interfaces:**
- `PreparedSceneGlb` tracks color-locked semantic materials without changing public scene loading calls.
- `applyPreparedSceneColor(...)` preserves materials whose inherited GLB extras declare `visibility_semantics=terrain_occluded`.

- [ ] **Step 1: Write failing tests** showing red semantic materials remain red after custom green color changes, while historical GLBs still load and scan visibility affects only scan nodes.
- [ ] **Step 2: Run focused Vitest tests** and confirm current color application changes all materials.
- [ ] **Step 3: Track semantic materials during preparation**, set transparent depthWrite/renderOrder policy, and skip locked materials during color transforms.
- [ ] **Step 4: Run focused frontend tests and TypeScript build.**

### Task 5: Full verification and handoff

**Files:**
- No implementation files unless verification finds a covered defect.

- [ ] **Step 1: Run backend focused and full tests.**
- [ ] **Step 2: Run frontend full Vitest suite and production build.**
- [ ] **Step 3: Generate representative GLBs from tests and assert node/metadata invariants with the existing GLB reader.**
- [ ] **Step 4: Review `git diff`/`git status` to confirm only scoped additions plus preserved pre-existing changes remain.**
