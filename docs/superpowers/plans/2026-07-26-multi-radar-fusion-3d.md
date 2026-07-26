# Multi-Radar Fusion 3D Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render terrain-aware union and overlap volumes for multi-radar tasks while retaining selected station scan animations.

**Architecture:** The worker accumulates visibility counts over fixed height bands on its existing shared DEM grid. A dedicated GLB writer converts a bounded sample of those counts to a fusion shell/core scene. The frontend shows that task-level scene by default and loads both normal station GLBs for selected stations.

**Tech Stack:** FastAPI, NumPy, Rasterio, Trimesh, GLB exporter, Vue 3, TypeScript, MapLibre GL, Three.js, pytest, Vitest.

## Global Constraints

- Preserve the current single-radar GLB material and animation behavior.
- Fusion colors: jade for union, amber for overlap, brighter amber for 3+ coverage.
- Limit fusion mesh sampling to 192x192 per height band and station detail selections to five.
- Do not run extra GDAL viewsheds to build height bands.

---

### Task 1: Common-Grid Fusion Height Counts

**Files:**
- Modify: `backend/app/workers/multi_radar_coverage_task.py`
- Create: `backend/app/services/multi_radar_fusion_volume.py`
- Test: `backend/tests/test_multi_radar_fusion_volume.py`

**Interfaces:** `FusionHeightCounts(heights_m, coverage_counts, transform, target_epsg)` and `accumulate_fusion_height_counts(station_masks) -> FusionHeightCounts`.

- [ ] Write a failing test that uses two stations and two height bands, asserting union count `1`, overlap count `2`, and shape preservation.
- [ ] Run `python -m pytest tests/test_multi_radar_fusion_volume.py -q`; expect import failure.
- [ ] Evaluate `_coverage_masks` for the fixed height bands from each station's existing GROUND raster, align local masks to the common grid, and increment uint16 counts.
- [ ] Run the focused test; expect pass.

### Task 2: Fusion GLB Artifact

**Files:**
- Modify: `backend/app/services/multi_radar_fusion_volume.py`
- Modify: `backend/app/workers/multi_radar_coverage_task.py`
- Modify: `backend/app/schemas/radar.py`
- Test: `backend/tests/test_multi_radar_fusion_volume.py`

**Interfaces:** `write_multi_radar_fusion_glb(path, counts) -> dict` and `MultiRadarOutputs.fusion_scene_glb`.

- [ ] Write a failing test that writes a small count grid and asserts a nonempty GLB plus metadata that identifies `fusion_union` and `fusion_overlap` nodes.
- [ ] Run the focused test; expect missing writer failure.
- [ ] Sample height-count grids to at most 192x192, build union/overlap meshes with existing scene frame/exporter utilities, and write `fusion_scene.glb` to the batch outputs.
- [ ] Run the focused test; expect pass.

### Task 3: Fusion Scene Frontend Loading

**Files:**
- Modify: `frontend/src/models/multiRadar/types.ts`
- Modify: `frontend/src/components/MultiRadarPanel.vue`
- Modify: `frontend/src/App.vue`
- Test: `frontend/src/map/multiRadarLayerAdapter.test.ts`

**Interfaces:** `fusion_scene_glb` output and `showMultiRadarFusion(task)`.

- [ ] Write a failing adapter test that expects a default fusion scene load when the task exposes `fusion_scene_glb`.
- [ ] Run `npm test -- src/map/multiRadarLayerAdapter.test.ts`; expect failure.
- [ ] Load the fusion GLB through the existing scene GLB adapter with a task-scoped asset ID; keep it independent from station detail eviction and focus it after initial load.
- [ ] Run the focused test; expect pass.

### Task 4: Complete Selected Station Detail

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/components/tasks/MultiRadarStationList.vue`
- Test: `frontend/src/components/tasks/MultiRadarStationList.test.ts`

**Interfaces:** `showMultiRadarDetail(stationId, task)` loads `scene_glb` and `radar_platform_glb`; station list emits `show-scan-volume`.

- [ ] Write a failing test that asserts the control uses the visible scan-volume label.
- [ ] Run `npm test -- src/components/tasks/MultiRadarStationList.test.ts`; expect failure.
- [ ] Load both GLB kinds for a finished detail task, focus the scan scene, and leave the fusion scene visible.
- [ ] Run the focused test; expect pass.

### Task 5: Verification and Preview

**Files:**
- Modify: `docs/superpowers/specs/2026-07-26-multi-radar-fusion-3d-design.md` only if verification reveals a design correction.

- [ ] Run `python -m pytest -q` from `backend`.
- [ ] Run `npm test` and `npm run build` from `frontend`.
- [ ] Run `docker compose up --build -d`, using port 5174 for the preview if 5173 is occupied.
- [ ] Submit the existing two-station task and verify the task exposes `fusion_scene_glb`, the map loads it, and selecting a station fetches both GLB kinds.
