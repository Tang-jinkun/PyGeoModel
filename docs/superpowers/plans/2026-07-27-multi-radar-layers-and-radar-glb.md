# Multi-Radar Layers And Radar GLB Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface multi-radar aggregate layers in the workbench and restore a historical radar task's DEM before GLB loading.

**Architecture:** The multi-radar adapter owns aggregate overlay state and controls. `App.vue` supplies either that provider or the ordinary `useMapWorkspace` provider to the existing Dock. Standard historical task selection restores `task.dem_id` before GLB interaction.

**Tech Stack:** Vue 3, TypeScript, MapLibre/Mapbox APIs, Vitest, Vue Test Utils.

## Global Constraints

- Reuse `WorkbenchDock`; do not add a separate layer panel.
- Expose visible union, overlap, blind, and coverage-count overlays; keep station rows separate.
- Do not change backend artifact contracts or GLB generation.

---

### Task 1: Give The Multi-Radar Adapter Dock-Compatible State

**Files:**
- Modify: `frontend/src/map/multiRadarLayerAdapter.ts`
- Create: `frontend/src/map/multiRadarLayerAdapter.test.ts`

**Interfaces:** Produces `definitions()`, `layerStates()`, `setLayerVisibility(map, kind, visible)`, `setLayerOpacity(map, kind, opacity)`, and `focusLayer(map, kind)`.

- [ ] **Step 1: Write a failing adapter test**

```ts
adapter.showAggregate(map, aggregate());
expect(adapter.definitions()).toHaveLength(4);
expect(adapter.layerStates()).toEqual(expect.arrayContaining([
  expect.objectContaining({ kind: "visible_union_geojson", status: "ready" })
]));
adapter.setLayerVisibility(map, "visible_union_geojson", false);
expect(map.setLayoutProperty).toHaveBeenCalledWith("multi-radar-visible", "visibility", "none");
```

- [ ] **Step 2: Verify red**

Run: `npm run test -- --run src/map/multiRadarLayerAdapter.test.ts`

Expected: FAIL because the adapter has no Dock state contract.

- [ ] **Step 3: Implement aggregate state**

Maintain four definition/state records for `visible_union_geojson`, `overlap_geojson`, `blind_geojson`, and `coverage_count_geojson`. Retain their GeoJSON after `showAggregate`; map each kind to its existing MapLibre layer id. Use `setLayoutProperty`, `setPaintProperty`, and `fitGeoJsonBounds` for Dock commands.

- [ ] **Step 4: Verify green and commit**

Run: `npm run test -- --run src/map/multiRadarLayerAdapter.test.ts`

Commit: `git add frontend/src/map/multiRadarLayerAdapter.ts frontend/src/map/multiRadarLayerAdapter.test.ts && git commit -m "feat: expose multi-radar aggregate layers"`

### Task 2: Route Existing Dock Controls To The Selected Provider

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/App.test.ts`

**Interfaces:** Consumes the Task 1 adapter contract and supplies `WorkbenchDock` with selected layer definitions and states.

- [ ] **Step 1: Write a failing App test**

```ts
await wrapper.get('[data-action="layers"]').trigger("click");
await wrapper.get('[data-dock-tab="layers"]').trigger("click");
expect(wrapper.findAll('[data-layer-kind]').map((node) => node.attributes("data-layer-kind")))
  .toEqual(expect.arrayContaining(["visible_union_geojson", "overlap_geojson", "blind_geojson", "coverage_count_geojson"]));
```

- [ ] **Step 2: Verify red**

Run: `npm run test -- --run src/App.test.ts`

Expected: FAIL because the Dock only receives ordinary model definitions and states.

- [ ] **Step 3: Implement provider routing**

Derive `selectedLayerDefinitions` and `selectedLayerStates` from the active multi-radar adapter when `selectedMultiRadarResultTask` exists; otherwise retain current model behavior. Delegate `setLayerVisibility`, `setLayerOpacity`, and `focusLayer` to the same selected provider.

- [ ] **Step 4: Verify green and commit**

Run: `npm run test -- --run src/App.test.ts`

Commit: `git add frontend/src/App.vue frontend/src/App.test.ts && git commit -m "fix: show multi-radar layers in workbench"`

### Task 3: Restore DEM Before Radar GLB Interaction

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/App.test.ts`
- Modify: `frontend/src/composables/useMapWorkspace.ts`
- Modify: `frontend/src/composables/useMapWorkspace.test.ts`

**Interfaces:** `selectWorkbenchTask` selects `task.dem_id` before presentation. The scene state is initialized before its DEM-match guard so a mismatch remains visible in the Dock.

- [ ] **Step 1: Write failing tests**

```ts
await wrapper.get('[data-task-key="radar:task-1"]').trigger("click");
expect(selectDem).toHaveBeenCalledWith("dem-1");

await workspace.setSceneGlbVisibility(map, "dem-b", "radar", task, true, "scene_glb", [sceneFile]);
expect(workspace.sceneGlbStateFor(task.task_id)?.error).toContain("does not match");
```

- [ ] **Step 2: Verify red**

Run: `npm run test -- --run src/App.test.ts src/composables/useMapWorkspace.test.ts`

Expected: the task-selection assertion fails because the task DEM is not selected.

- [ ] **Step 3: Implement the recovery path**

Resolve the selected task with `taskManager.getTask`; call `demManager.select(task.dem_id)` when present, then perform current task selection. Initialize the available scene state before validating selected DEM so the existing scene row displays a mismatch error rather than silently returning.

- [ ] **Step 4: Verify green and commit**

Run: `npm run test -- --run src/App.test.ts src/composables/useMapWorkspace.test.ts`

Commit: `git add frontend/src/App.vue frontend/src/App.test.ts frontend/src/composables/useMapWorkspace.ts frontend/src/composables/useMapWorkspace.test.ts && git commit -m "fix: restore radar task DEM before GLB loading"`
