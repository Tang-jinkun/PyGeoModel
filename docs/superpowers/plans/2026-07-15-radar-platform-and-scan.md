# Radar Platform And Scan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce independently controlled radar platform and detection-domain GLBs with synchronized, data-driven scan animation and a fuller internal result visualization.

**Architecture:** Extend the shared exporter with standard glTF TRS animation injection, then build the platform and scan/fill geometry from the existing radar ray grid. Generalize frontend scene state from task IDs to task/output-kind asset IDs while preserving the legacy `scene_glb` default path.

**Tech Stack:** Python, NumPy, trimesh, glTF 2.0/GLB, FastAPI/Pydantic, Vue 3, Three.js, Vitest, pytest.

## Global Constraints

- Keep `radar_detection_domain.glb` and `radar_platform.glb` separate.
- Use actual `radius[elevation][azimuth]` values for scan slice lengths.
- Preserve terrain, NoData, DEM boundary, and scan-sector openings.
- Use an eight-second looping scan period and standard glTF animation channels.
- Preserve legacy radar tasks and the 50 MB GLB limit.

---

### Task 1: Standard GLB Animation Export And Playback

**Files:**
- Modify: `backend/app/scene3d/exporter.py`
- Test: `backend/tests/test_scene3d_exporter.py`
- Modify: `frontend/src/map/sceneGlbAsset.ts`
- Modify: `frontend/src/map/sceneGlbLayer.ts`
- Test: `frontend/src/map/sceneGlbAsset.test.ts`
- Test: `frontend/src/map/sceneGlbLayer.test.ts`

**Interfaces:**
- Produces: `AnimationTrack(node_name, path, times, values, interpolation)` and `AnimationSpec(name, tracks)` accepted by `export_glb(..., animations=[])`.
- Produces: `PreparedSceneGlb.animations: THREE.AnimationClip[]` played from a shared wall-clock phase by `sceneGlbLayer`.

- [ ] Add a failing exporter test asserting a rotation channel, sampler, accessors, and target node in serialized GLB JSON.
- [ ] Run `pytest -q backend/tests/test_scene3d_exporter.py` and confirm the missing animation API failure.
- [ ] Implement float32 BIN-chunk animation accessors and channels for `rotation` and `scale`, removing target-node matrices in favor of initial TRS values.
- [ ] Run the exporter test and confirm it passes.
- [ ] Add failing frontend tests proving parsed animation clips are retained and the layer creates a synchronized `AnimationMixer`.
- [ ] Implement clip retention, mixer playback, cleanup, and wall-clock `setTime`.
- [ ] Run `npm test -- --run src/map/sceneGlbAsset.test.ts src/map/sceneGlbLayer.test.ts`.

### Task 2: Radar Platform And Full Detection Visualization

**Files:**
- Create: `backend/app/scene3d/radar_platform.py`
- Modify: `backend/app/scene3d/radar.py`
- Modify: `backend/app/schemas/radar.py`
- Modify: `backend/app/services/output_files.py`
- Modify: `backend/app/workers/coverage_task.py`
- Test: `backend/tests/test_radar_scene3d.py`

**Interfaces:**
- Produces: `write_radar_platform_glb(path, task_id, prepared, radar_ground_m, payload) -> dict`.
- Produces: output kind `radar_platform_glb` at `radar_platform.glb`.
- Extends detection metadata with `scan_animation.period_s`, `scan_animation.slice_count`, and `interior_sample_count`.

- [ ] Add failing tests for the platform output descriptor, realistic semantic nodes, rotation animation, detection fill node, and variable-length scan-slice nodes.
- [ ] Run `pytest -q backend/tests/test_radar_scene3d.py` and confirm contract failures.
- [ ] Build physical-scale platform primitives with static and rotating PBR nodes and export the eight-second rotation animation.
- [ ] Build batched octahedral interior samples along closed rays and one animated narrow scan mesh per azimuth cell.
- [ ] Publish both GLBs in the radar task transaction and add both descriptors to task outputs.
- [ ] Run `pytest -q backend/tests/test_radar_scene3d.py backend/tests/test_coverage_task_outputs.py`.

### Task 3: Independent Frontend Asset Controls

**Files:**
- Modify: `frontend/src/api/radar.ts`
- Modify: `frontend/src/composables/useMapWorkspace.ts`
- Modify: `frontend/src/components/tasks/TaskResultPanel.vue`
- Modify: `frontend/src/components/tasks/SceneGlbControl.vue`
- Modify: `frontend/src/App.vue`
- Test: `frontend/src/composables/useMapWorkspace.test.ts`
- Test: `frontend/src/components/tasks/TaskResultPanel.test.ts`
- Test: `frontend/src/App.test.ts`

**Interfaces:**
- Produces: `SceneGlbKind = "scene_glb" | "radar_platform_glb"`.
- Produces: `sceneGlbStateFor(taskId, kind)` and `setSceneGlbVisibility(..., visible, kind)` using composite asset IDs while validating metadata against the original task ID.

- [ ] Add failing component and workspace tests for two output controls with independent state and URLs.
- [ ] Run the focused Vitest files and confirm single-asset assumptions fail.
- [ ] Generalize scene state/controller/layer IDs to task-plus-kind asset IDs and render controls from available GLB outputs.
- [ ] Preserve `scene_glb` defaults so non-radar and legacy tasks remain unchanged.
- [ ] Run focused Vitest files, then `npm run build`.

### Task 4: Runtime Demonstration

**Files:**
- No source files; use the feature Docker environment and persisted task outputs.

**Interfaces:**
- Consumes both output kinds and the shared eight-second animation phase.

- [ ] Rebuild feature backend and frontend images without touching ports `5173/8000`.
- [ ] Generate a 40 km target-independent DEM radar task.
- [ ] Verify both GLBs return `200 model/gltf-binary`, remain below 50 MB, and expose animation metadata.
- [ ] Enable both controls, focus the detection domain, capture a desktop screenshot, and confirm no browser errors.
- [ ] Commit implementation and report the task ID, URL, output sizes, test results, and screenshot.

