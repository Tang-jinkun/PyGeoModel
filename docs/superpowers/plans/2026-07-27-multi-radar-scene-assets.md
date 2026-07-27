# Multi-Radar Scene Assets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every multi-radar GLB a first-class result-layer entry and keep the radar platform visually proportional when enlarged.

**Architecture:** The multi-radar API will expose a derived scene-asset manifest whose entries identify the source coverage task, output descriptor, semantic render tier, and station label. The frontend will convert that manifest into the same scene-entry model consumed by the workbench dock, while the GLB layer retains its current renderer and receives a presentation-scale option for platforms.

**Tech Stack:** FastAPI/Pydantic, Python pytest, Vue 3/TypeScript, Vitest, MapLibre, Three.js.

## Global Constraints

- Preserve all existing task files and APIs; the scene-asset manifest is additive.
- Keep coverage geometry and radar coordinates unchanged.
- Treat display scale as presentation metadata, never as coverage-model input.
- Use one stable scene entry id per source task and artifact kind.

---

### Task 1: Expose Multi-Radar Scene Assets

**Files:** `backend/app/schemas/radar.py`, `backend/app/services/multi_radar_task_store.py`, `backend/tests/test_multi_radar_task_store.py`

- [x] Write a failing store test that expects `MultiRadarTaskStatus.scene_assets` to contain source task, radar id, output file, semantic kind, and render tier.
- [x] Add `MultiRadarSceneAsset` and derive station `scene_glb`/`radar_platform_glb` assets plus the cooperative intersection asset while hydrating a multi-radar task.
- [x] Run the focused backend test and commit the API contract.

### Task 2: Normalize Workbench Scene Entries

**Files:** `frontend/src/models/multiRadar/types.ts`, `frontend/src/models/multiRadar/sceneAssets.ts`, `frontend/src/components/workbench/WorkbenchDock.vue`, `frontend/src/App.vue`, related Vitest files.

- [x] Write failing tests for converting one scene asset into a generic scene task and for showing its stable asset id in the layers dock.
- [x] Change `WorkbenchSceneEntry` event identity from artifact kind to `id`; map multi-radar assets into those entries and delegate load/focus/toggle through the existing scene workspace.
- [x] Run focused frontend tests and commit the UI contract.

### Task 3: Keep Platform Presentation Scale Uniform

**Files:** `backend/app/scene3d/radar_platform.py`, `backend/tests/test_radar_platform.py`

- [x] Write a failing dimensions test showing that a tenfold display enlargement applies to width, depth, and height.
- [x] Apply the same display multiplier to the platform vertical axis while retaining its ground anchor and updating metadata dimensions.
- [x] Run the focused backend test and commit the scale correction.

### Task 4: Integrate And Verify

**Files:** implementation files and tests above.

- [x] Run `python -m pytest` in `backend`, then `npm run test` and `npm run build` in `frontend`.
- [x] Run `docker compose up -d --build`; verify both `127.0.0.1:5173` and `127.0.0.1:8000/docs` return `200`.
- [ ] Commit the verified implementation without staging the pre-existing lockfile or local logs.
