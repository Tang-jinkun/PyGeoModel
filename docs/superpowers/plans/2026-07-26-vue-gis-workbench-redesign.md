# Vue GIS Workbench Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the static GIS workbench design as a responsive Vue workspace while preserving every real PyGeoModel model, task, map, layer, GLB, and cooperative-radar workflow.

**Architecture:** A new `components/workbench` presentation layer replaces the old four-column `WorkspaceShell`. `App.vue` remains the domain coordinator for the existing composables and map adapters, while small pure helpers derive task presentation state and result summaries. The left dock owns all map-layer controls; the right inspector switches between a real model form and a selected task's result detail; the bottom task center remains a compact queue.

**Tech Stack:** Vue 3.5, TypeScript 5.7, Vite 6, Vitest 4, Vue Test Utils, Element Plus, MapLibre GL 4, Three.js.

## Global Constraints

- Use `PyGeoModel-前端重设计/gis-workbench.html` as the sole visual and responsive reference.
- Do not replace the current `MapWorkspace` / MapLibre / Three.js rendering with the static canvas demo.
- Preserve all seven registered model workflows in `frontend/src/models/registry.ts`.
- The Layers dock is the only place for 2D-layer, GLB, scan-plane, and radar-scene visibility/opacity/focus controls.
- The task center must show one primary result metric per completed task at most; full metrics, warnings, and downloads belong in the selected task's right-side detail view.
- Cooperative three-to-five-radar tasks retain independent station scene/platform/scan layers and a separate gold intersection layer.
- Do not modify backend task APIs or workers for this redesign.
- Use test-driven development: write and run the failing focused test before production code for each behavior.

---

## File Structure

- Create: `frontend/src/workbench/taskPresentation.ts` - pure task row, status, and primary-metric derivation.
- Create: `frontend/src/workbench/taskPresentation.test.ts` - focused unit coverage for compact task presentation.
- Create: `frontend/src/workbench/useWorkbenchPresentation.ts` - Vue-only state for dock tab, task tab, inspector mode, and compact task-center state.
- Create: `frontend/src/workbench/useWorkbenchPresentation.test.ts` - presentation-state transition tests.
- Create: `frontend/src/components/workbench/GisWorkbenchShell.vue` - responsive six-region grid and named slot contract.
- Create: `frontend/src/components/workbench/GisWorkbenchShell.test.ts` - shell collapse and narrow-screen behavior.
- Create: `frontend/src/components/workbench/WorkbenchTopbar.vue` - static-design top bar and search input.
- Create: `frontend/src/components/workbench/WorkbenchDock.vue` - Model Library, Layers, and Data dock.
- Create: `frontend/src/components/workbench/WorkbenchDock.test.ts` - model filtering, tab switching, and layer-control delegation.
- Create: `frontend/src/components/workbench/WorkbenchInspector.vue` - parameter/result-detail right inspector.
- Create: `frontend/src/components/workbench/WorkbenchTaskCenter.vue` - compact running/history/log task center.
- Create: `frontend/src/components/workbench/WorkbenchTaskCenter.test.ts` - task selection, compact rows, and collapse behavior.
- Create: `frontend/src/components/workbench/WorkbenchMapStage.vue` - map visual chrome that wraps the real map component.
- Create: `frontend/src/components/workbench/WorkbenchStatusbar.vue` - cursor/DEM/connection status presentation.
- Modify: `frontend/src/components/tasks/TaskResultPanel.vue` - allow right-inspector use without duplicating layer controls.
- Modify: `frontend/src/components/tasks/LayerList.vue` - expose source-design row density without changing its layer event API.
- Modify: `frontend/src/components/tasks/SceneGlbControl.vue` - expose source-design row density without changing its GLB event API.
- Modify: `frontend/src/App.vue` - compose the new workbench and wire current domain state/events into it.
- Modify: `frontend/src/App.test.ts` - replace old-shell assertions with workbench integration assertions.
- Modify: `frontend/src/styles/app.css` - replace old layout/theme rules with the static source's tokens, grid, and responsive rules.

## Task 1: Compact Task Presentation Contracts

**Files:**
- Create: `frontend/src/workbench/taskPresentation.ts`
- Test: `frontend/src/workbench/taskPresentation.test.ts`

**Interfaces:**
- Consumes: `ModelId`, `TaskStatus`, `TaskSummary`, and `MODEL_REGISTRY`.
- Produces:
  ```ts
  export interface WorkbenchTaskRow {
    key: string;
    modelId: ModelId;
    task: TaskSummary<BaseModelRequest, unknown, unknown, unknown>;
    label: string;
    statusLabel: string;
    primaryMetric: string | null;
    timestamp: number;
  }
  export function buildWorkbenchTaskRows(tasksByModel: Partial<Record<ModelId, readonly TaskSummary[]>>): WorkbenchTaskRow[];
  export function isActiveTask(task: TaskSummary): boolean;
  ```

- [ ] **Step 1: Write the failing test for compact, model-aware completed-task rows**

  ```ts
  it("uses the first available registered metric as the only completed-task summary", () => {
    const rows = buildWorkbenchTaskRows({
      radar: [{ task_id: "radar-1", status: "finished", progress: 100, message: "done", output_files: [], warnings: [], metrics: { visible_area_m2: 2_500_000, blocked_ratio: 0.31 } }]
    });

    expect(rows[0]).toMatchObject({
      key: "radar:radar-1",
      label: "Radar coverage analysis",
      primaryMetric: "Visible area 2.50 km2"
    });
  });
  ```

- [ ] **Step 2: Run the focused test and verify it fails because the module is absent**

  Run: `npm test -- src/workbench/taskPresentation.test.ts`

  Expected: FAIL with an import/module-not-found error for `taskPresentation`.

- [ ] **Step 3: Implement metric formatting and stable task ordering**

  ```ts
  export function buildWorkbenchTaskRows(tasksByModel: Partial<Record<ModelId, readonly GenericTask[]>>) {
    return MODEL_IDS.flatMap((modelId) => (tasksByModel[modelId] ?? []).map((task) => ({
      key: `${modelId}:${task.task_id}`,
      modelId,
      task,
      label: MODEL_REGISTRY[modelId].label,
      statusLabel: STATUS_LABELS[task.status],
      primaryMetric: task.status === "finished" ? formatFirstMetric(modelId, task.metrics) : null,
      timestamp: taskTimestamp(task)
    }))).sort((left, right) => right.timestamp - left.timestamp);
  }
  ```

  `formatFirstMetric` must use the registered metric definitions and return `null` when a completed task has no usable metric; it must never concatenate every metric into the task row.

- [ ] **Step 4: Add and run coverage for running/failed tasks and timestamp ordering**

  ```ts
  it("keeps running tasks metric-free and sorts newest first", () => {
    const rows = buildWorkbenchTaskRows({
      radar: [runningTask("old", "2026-07-01T00:00:00Z"), runningTask("new", "2026-07-02T00:00:00Z")]
    });
    expect(rows.map(({ task }) => task.task_id)).toEqual(["new", "old"]);
    expect(rows.every(({ primaryMetric }) => primaryMetric === null)).toBe(true);
  });
  ```

  Run: `npm test -- src/workbench/taskPresentation.test.ts`

  Expected: PASS.

- [ ] **Step 5: Commit the isolated contract**

  ```bash
  git add frontend/src/workbench/taskPresentation.ts frontend/src/workbench/taskPresentation.test.ts
  git commit -m "feat: add compact workbench task presentation"
  ```

## Task 2: Workbench Presentation State and Six-Region Shell

**Files:**
- Create: `frontend/src/workbench/useWorkbenchPresentation.ts`
- Create: `frontend/src/workbench/useWorkbenchPresentation.test.ts`
- Create: `frontend/src/components/workbench/GisWorkbenchShell.vue`
- Create: `frontend/src/components/workbench/GisWorkbenchShell.test.ts`
- Modify: `frontend/src/styles/app.css`

**Interfaces:**
- Consumes: a `selectedTaskKey: Ref<string | null>` from `useTaskManager`.
- Produces:
  ```ts
  export type DockTab = "catalog" | "layers" | "data";
  export type InspectorMode = "parameters" | "result";
  export function useWorkbenchPresentation(selectedTaskKey: Readonly<Ref<string | null>>): {
    dockTab: Ref<DockTab>;
    taskTab: Ref<"running" | "history" | "logs">;
    taskCenterCollapsed: Ref<boolean>;
    inspectorMode: ComputedRef<InspectorMode>;
    selectModel(): void;
    selectTask(): void;
    showParameters(): void;
  };
  ```

- [ ] **Step 1: Write failing state tests**

  ```ts
  it("switches to result detail only after a task selection", () => {
    const selectedTaskKey = ref<string | null>(null);
    const state = useWorkbenchPresentation(selectedTaskKey);
    expect(state.inspectorMode.value).toBe("parameters");
    selectedTaskKey.value = "radar:task-8";
    expect(state.inspectorMode.value).toBe("result");
    state.showParameters();
    expect(state.inspectorMode.value).toBe("parameters");
  });
  ```

  ```ts
  it("renders the static-design six region slots and collapses the task center", async () => {
    const wrapper = mount(GisWorkbenchShell, { slots: { topbar: "top", dock: "dock", map: "map", inspector: "inspector", tasks: "tasks", status: "status" } });
    await wrapper.get('[aria-label="Collapse task center"]').trigger("click");
    expect(wrapper.attributes("data-tasks-collapsed")).toBe("true");
  });
  ```

- [ ] **Step 2: Run focused state and shell tests to verify red**

  Run: `npm test -- src/workbench/useWorkbenchPresentation.test.ts src/components/workbench/GisWorkbenchShell.test.ts`

  Expected: FAIL because the composable and shell do not exist.

- [ ] **Step 3: Implement presentation state and named-slot shell**

  ```vue
  <main class="gis-workbench" :data-tasks-collapsed="tasksCollapsed">
    <header class="gis-workbench__topbar"><slot name="topbar" /></header>
    <aside class="gis-workbench__dock"><slot name="dock" /></aside>
    <section class="gis-workbench__map"><slot name="map" /></section>
    <aside class="gis-workbench__inspector"><slot name="inspector" /></aside>
    <section class="gis-workbench__tasks"><slot name="tasks" /></section>
    <footer class="gis-workbench__status"><slot name="status" /></footer>
  </main>
  ```

  Add the static source's CSS tokens and desktop grid (`292px minmax(360px, 1fr) 328px`, 52px top row, task center row, 26px status row). At `max-width: 1279px`, use the source compact grid (`252px minmax(320px, 1fr) 300px`) and hide project context. Add the documented narrow-viewport behavior without retaining the old `workspace-shell` grid as the active app layout.

- [ ] **Step 4: Run focused tests and the type build**

  Run: `npm test -- src/workbench/useWorkbenchPresentation.test.ts src/components/workbench/GisWorkbenchShell.test.ts && npm run build`

  Expected: PASS.

- [ ] **Step 5: Commit shell and state**

  ```bash
  git add frontend/src/workbench frontend/src/components/workbench/GisWorkbenchShell.vue frontend/src/components/workbench/GisWorkbenchShell.test.ts frontend/src/styles/app.css
  git commit -m "feat: add GIS workbench shell"
  ```

## Task 3: Left Dock for Models, Data, and All Layers

**Files:**
- Create: `frontend/src/components/workbench/WorkbenchTopbar.vue`
- Create: `frontend/src/components/workbench/WorkbenchTopbar.test.ts`
- Create: `frontend/src/components/workbench/WorkbenchDock.vue`
- Create: `frontend/src/components/workbench/WorkbenchDock.test.ts`
- Modify: `frontend/src/components/tasks/LayerList.vue`
- Create: `frontend/src/components/tasks/LayerList.test.ts`
- Modify: `frontend/src/components/tasks/SceneGlbControl.vue`
- Modify: `frontend/src/components/tasks/RadarLayerControls.vue`
- Modify: `frontend/src/components/tasks/MultiRadarStationList.vue`

**Interfaces:**
- Consumes `MODEL_IDS`, `MODEL_REGISTRY`, `DemSelector` props/events, `TaskOutputLayerState[]`, `SceneGlbOverlayState`, radar controls, and multi-radar station state from the existing `App.vue` logic.
- Emits:
  ```ts
  // WorkbenchTopbar
  "update:search": [query: string]

  // WorkbenchDock
  "select-model": [modelId: ModelId]
  "update-layer-visibility": [kind: string, visible: boolean]
  "update-layer-opacity": [kind: string, opacity: number]
  "focus-layer": [kind: string]
  "update-scene-glb": [kind: SceneGlbKind, visible: boolean]
  "focus-scene-glb": [kind: SceneGlbKind]
  ```

- [ ] **Step 1: Write a failing dock test for catalog filtering and layer delegation**

  ```ts
  it("emits the static topbar search query", async () => {
    const wrapper = mount(WorkbenchTopbar, { props: { demLabel: "terrain.tif", connected: true, search: "" } });
    await wrapper.get('input[aria-label="Global search"]').setValue("radar");
    expect(wrapper.emitted("update:search")?.[0]).toEqual(["radar"]);
  });

  it("filters registered models and delegates GLB visibility from the Layers tab", async () => {
    const wrapper = mount(WorkbenchDock, { props: dockProps({ sceneGlbState: readyScene() }) });
    await wrapper.get('[data-dock-tab="catalog"]').trigger("click");
    await wrapper.get('input[aria-label="Search analysis models"]').setValue("radar");
    expect(wrapper.findAll('[data-model-id]').map((node) => node.attributes("data-model-id"))).toEqual(["radar"]);
    await wrapper.get('[data-dock-tab="layers"]').trigger("click");
    await wrapper.get('[data-layer-kind="scene_glb"] input[type="checkbox"]').setValue(false);
    expect(wrapper.emitted("update-scene-glb")?.[0]).toEqual(["scene_glb", false]);
  });

  it("keeps the existing LayerList visibility event contract in compact dock rows", async () => {
    const wrapper = mount(LayerList, { props: { definitions: [visibleLayer()], states: [readyLayerState()] } });
    await wrapper.get('input[type="checkbox"]').setValue(false);
    expect(wrapper.emitted("visibility")?.[0]).toEqual(["visible_geojson", false]);
  });
  ```

- [ ] **Step 2: Run the dock test and verify red**

  Run: `npm test -- src/components/workbench/WorkbenchTopbar.test.ts src/components/workbench/WorkbenchDock.test.ts`

  Expected: FAIL because `WorkbenchDock` is absent.

- [ ] **Step 3: Implement the three dock panes with static-design hierarchy**

  - Top bar: reproduce the source-design brand, project context, global search, active DEM chip, connection chip, and icon action. Bind its query to the catalog filter so the same model search result is visible in the left dock.
  - Catalog: use the actual registry and searchable category groups; selecting a model emits `select-model` and does not create a second model navigation system.
  - Layers: group selected-task 2D output layers, scene GLBs, radar volume/scan controls, and cooperative station/intersection controls under the selected task. Keep `LayerList` and `SceneGlbControl` event names unchanged, but render them as compact dock rows.
  - Data: render `DemSelector` plus real task output files. Keep current upload, refresh, selection, and delete events.

  The cooperative group must include independent station platform/scene/scan rows and a separate `cooperative_intersection` row; no GLB toggle may appear in `TaskResultPanel` after this migration.

- [ ] **Step 4: Add coverage for all registered model IDs and cooperative group labels**

  ```ts
  it("lists every registered model and keeps cooperative intersection separate from station scenes", () => {
    const wrapper = mount(WorkbenchDock, { props: dockProps({ cooperative: cooperativeFixture() }) });
    expect(MODEL_IDS.every((id) => wrapper.find(`[data-model-id="${id}"]`).exists())).toBe(true);
    expect(wrapper.find('[data-layer-kind="cooperative_intersection"]').exists()).toBe(true);
    expect(wrapper.findAll('[data-layer-kind="station-scene"]').length).toBe(3);
  });
  ```

  Run: `npm test -- src/components/workbench/WorkbenchTopbar.test.ts src/components/workbench/WorkbenchDock.test.ts src/components/tasks/LayerList.test.ts src/components/tasks/SceneGlbControl.test.ts`

  Expected: PASS.

- [ ] **Step 5: Commit dock migration**

  ```bash
  git add frontend/src/components/workbench/WorkbenchTopbar.vue frontend/src/components/workbench/WorkbenchTopbar.test.ts frontend/src/components/workbench/WorkbenchDock.vue frontend/src/components/workbench/WorkbenchDock.test.ts frontend/src/components/tasks
  git commit -m "feat: move map controls into workbench layers dock"
  ```

## Task 4: Compact Task Center and Right-Side Result Inspector

**Files:**
- Create: `frontend/src/components/workbench/WorkbenchTaskCenter.vue`
- Create: `frontend/src/components/workbench/WorkbenchTaskCenter.test.ts`
- Create: `frontend/src/components/workbench/WorkbenchInspector.vue`
- Modify: `frontend/src/components/tasks/TaskResultPanel.vue`

**Interfaces:**
- Consumes `WorkbenchTaskRow[]`, selected `TaskSummary`, `ModelId`, `TaskOutputLayerState[]`, output files, and task-manager actions.
- Emits:
  ```ts
  "select-task": [modelId: ModelId, taskId: string]
  "restore-task": [modelId: ModelId, taskId: string]
  "retry-task": [modelId: ModelId, taskId: string]
  "download-file": [file: OutputFile]
  "show-parameters": []
  ```

- [ ] **Step 1: Write failing task-center and inspector tests**

  ```ts
  it("keeps history rows to one primary metric and selects a completed task", async () => {
    const wrapper = mount(WorkbenchTaskCenter, { props: { rows: [finishedRadarRow()], activeTab: "history" } });
    expect(wrapper.text()).toContain("Visible area 2.50 km2");
    expect(wrapper.text()).not.toContain("Blocked ratio");
    await wrapper.get('[data-task-key="radar:radar-1"]').trigger("click");
    expect(wrapper.emitted("select-task")?.[0]).toEqual(["radar", "radar-1"]);
  });

  it("shows metrics and files but no layer toggle in result mode", () => {
    const wrapper = mount(WorkbenchInspector, { props: { mode: "result", context: finishedContext() } });
    expect(wrapper.find('[data-result-detail]').exists()).toBe(true);
    expect(wrapper.find('[data-layer-kind]').exists()).toBe(false);
  });
  ```

- [ ] **Step 2: Run focused tests and verify red**

  Run: `npm test -- src/components/workbench/WorkbenchTaskCenter.test.ts src/components/workbench/WorkbenchInspector.test.ts`

  Expected: FAIL because the task-center and inspector components do not exist.

- [ ] **Step 3: Implement compact task center and inspector swap**

  - Running tab: task ID, model, message, progress bar, status, cancel action when supported.
  - History tab: task ID, model, one `primaryMetric`, status/time, and icon actions for focus, restore, download, log, and retry. Retry must call `taskManager.restoreRequest(modelId, taskId)` and submit the returned request through the existing `taskManager.submit(modelId, request)` path; it must not invent a backend retry API.
  - Logs tab: real `task.message`, warnings, and task lifecycle messages; remove the old modal history drawer from the visible path.
  - Inspector parameter mode: render `DemSelector`, `ModelParameterPanel`, and radar-specific submission controls unchanged in behavior.
  - Inspector result mode: render task state, all metrics, warnings, and files. Pass `showLayers=false` to `TaskResultPanel` (or split its detail body) so layers are not duplicated outside the dock.

- [ ] **Step 4: Add failed-task and return-to-parameters coverage**

  ```ts
  it("shows failure detail and returns to the current model form", async () => {
    const wrapper = mount(WorkbenchInspector, { props: { mode: "result", context: failedContext() } });
    expect(wrapper.text()).toContain("failed");
    await wrapper.get('[aria-label="Back to model parameters"]').trigger("click");
    expect(wrapper.emitted("show-parameters")).toHaveLength(1);
  });
  ```

  Run: `npm test -- src/components/workbench/WorkbenchTaskCenter.test.ts src/components/workbench/WorkbenchInspector.test.ts src/components/tasks/TaskResultPanel.test.ts`

  Expected: PASS.

- [ ] **Step 5: Commit task/result interaction**

  ```bash
  git add frontend/src/components/workbench/WorkbenchTaskCenter.vue frontend/src/components/workbench/WorkbenchTaskCenter.test.ts frontend/src/components/workbench/WorkbenchInspector.vue frontend/src/components/tasks/TaskResultPanel.vue
  git commit -m "feat: add compact workbench task and result views"
  ```

## Task 5: Real Map Stage, Status Bar, and Application Composition

**Files:**
- Create: `frontend/src/components/workbench/WorkbenchMapStage.vue`
- Create: `frontend/src/components/workbench/WorkbenchStatusbar.vue`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/App.test.ts`
- Modify: `frontend/src/styles/app.css`

**Interfaces:**
- Consumes existing `MapWorkspace` map-ready/spatial-edit events; existing `mapWorkspace`, `taskManager`, `demManager`, `radarAnalysis`, `multiRadarAdapter`, and `showMultiRadarCooperativeScene` state in `App.vue`.
- Produces a single root composition:
  ```vue
  <GisWorkbenchShell>
    <template #topbar><WorkbenchTopbar /></template>
    <template #dock><WorkbenchDock /></template>
    <template #map><WorkbenchMapStage><MapWorkspace /></WorkbenchMapStage></template>
    <template #inspector><WorkbenchInspector /></template>
    <template #tasks><WorkbenchTaskCenter /></template>
    <template #status><WorkbenchStatusbar /></template>
  </GisWorkbenchShell>
  ```

- [ ] **Step 1: Write failing App integration tests for real map/task wiring**

  ```ts
  it("selects a completed task from the task center, focuses its map result, and opens result detail", async () => {
    const wrapper = mountAppWithFinishedRadarTask();
    await wrapper.get('[data-task-key="radar:task-1"]').trigger("click");
    expect(mapWorkspaceMock.loadTaskOutputs).toHaveBeenCalledWith("radar", expect.objectContaining({ task_id: "task-1" }));
    expect(wrapper.find('[data-result-detail]').exists()).toBe(true);
  });

  it("routes scene visibility only through the Layers dock", async () => {
    const wrapper = mountAppWithFinishedRadarTask();
    await wrapper.get('[data-dock-tab="layers"]').trigger("click");
    await wrapper.get('[data-layer-kind="scene_glb"] input').setValue(true);
    expect(mapWorkspaceMock.setSceneGlbVisibility).toHaveBeenCalled();
  });
  ```

- [ ] **Step 2: Run App integration tests and verify red**

  Run: `npm test -- src/App.test.ts`

  Expected: FAIL because the workbench shell and selectors are not wired in `App.vue`.

- [ ] **Step 3: Replace the old shell composition without rewriting domain logic**

  - Remove `WorkspaceShell` and `TaskHistoryDrawer` from the active `App.vue` template.
  - Preserve the existing watchers, `submitTask`, `focusTask`, `setLayerVisibility`, `setSceneGlbVisibility`, map event handlers, radar profile/fusion actions, and multi-radar cooperative scene loading code.
  - Convert `historyTasks` through `buildWorkbenchTaskRows` and pass the selected task context into `WorkbenchInspector`.
  - When a model is selected, call `presentation.selectModel()` before existing `selectModel`; when a task is selected, call `taskManager.select()` and `presentation.selectTask()` before existing map-output loading reacts.
  - After `loadTaskOutputs` finishes for a selected completed task, focus the model definition's primary output layer through `mapWorkspace.focusTaskLayer(map, primary.kind)`; when a model has no primary output layer, focus its first ready output layer. Cooperative radar selection keeps its existing complete-scene `focusSceneGlbs` call instead.
  - Move `RadarLayerControls`, `MultiRadarStationList`, and `SceneGlbControl` from the map/results panes into `WorkbenchDock` props/slots; do not change their map adapter methods.
  - Put `MapWorkspace` inside `WorkbenchMapStage`, retaining all existing events and overlay components needed for real radar profile/fusion previews.

- [ ] **Step 4: Add single-radar and cooperative-radar integration cases**

  ```ts
  it("keeps three cooperative station scenes and the gold intersection independently available in Layers", async () => {
    const wrapper = mountAppWithCooperativeTask();
    await wrapper.get('[data-dock-tab="layers"]').trigger("click");
    expect(wrapper.findAll('[data-layer-kind="station-scene"]')).toHaveLength(3);
    expect(wrapper.find('[data-layer-kind="cooperative_intersection"]').exists()).toBe(true);
  });
  ```

  Run: `npm test -- src/App.test.ts src/components/workbench/WorkbenchDock.test.ts`

  Expected: PASS.

- [ ] **Step 5: Commit composition migration**

  ```bash
  git add frontend/src/App.vue frontend/src/App.test.ts frontend/src/components/workbench/WorkbenchMapStage.vue frontend/src/components/workbench/WorkbenchStatusbar.vue frontend/src/styles/app.css
  git commit -m "feat: compose real GIS workflows in redesigned workbench"
  ```

## Task 6: Responsive, Visual, and End-to-End Verification

**Files:**
- Modify: `frontend/src/components/workbench/GisWorkbenchShell.test.ts`
- Modify: `frontend/src/App.test.ts`
- Modify: `docs/superpowers/specs/2026-07-26-vue-gis-workbench-redesign-design.md` only if implementation reveals a necessary contract clarification.

**Interfaces:**
- Consumes the complete workbench app from Tasks 1-5.
- Produces verified visual conformance and no regression in existing front-end behavior.

- [ ] **Step 1: Write failing responsive contract tests**

  ```ts
  it.each([360, 390, 430, 600, 820, 1024, 1366, 1440, 1920])("keeps stable regions at %ipx width", (width) => {
    installViewport(width, 900);
    const wrapper = mount(GisWorkbenchShell);
    expect(wrapper.find(".gis-workbench__map").exists()).toBe(true);
    expect(wrapper.find(".gis-workbench__tasks").exists()).toBe(true);
  });
  ```

- [ ] **Step 2: Run responsive tests and verify red**

  Run: `npm test -- src/components/workbench/GisWorkbenchShell.test.ts`

  Expected: FAIL until the final breakpoint contract is implemented.

- [ ] **Step 3: Implement only the required responsive fixes**

  Keep all six regions readable at the documented viewport matrix. At narrow widths, use the static source's compact/collapsed panel behavior; do not hide the map or introduce text overflow. Keep icon controls accessible with labels/tooltips.

- [ ] **Step 4: Run automated verification**

  Run: `npm test && npm run build`

  Expected: all Vitest suites PASS and Vite type/build succeeds.

- [ ] **Step 5: Run manual visual and workflow verification**

  Run: `npm run dev -- --port 5174`

  Verify at 360x800, 1024x768, 1440x900, and 1920x1080:

  1. Compare shell, spacing, controls, tabs, collapsed task center, and panel behavior against `PyGeoModel-前端重设计/gis-workbench.html`.
  2. Run one task for each of radar, UAV, watchpost, artillery, recon vehicle, mobility, and air corridor; confirm parameter form, task row, result detail, and layer group.
  3. Run a single radar task; confirm coverage, radar GLB, scene GLB, and scan plane controls only appear under Layers.
  4. Run a three-to-five-radar cooperative task; confirm each station retains its full scene and the gold intersection is independently controllable.
  5. Confirm DEM selection/upload, task failure, log view, retry, focus, and downloads remain usable.

- [ ] **Step 6: Commit verification fixes**

  ```bash
  git add frontend/src/components/workbench/GisWorkbenchShell.test.ts frontend/src/App.test.ts frontend/src/styles/app.css docs/superpowers/specs/2026-07-26-vue-gis-workbench-redesign-design.md
  git commit -m "test: verify redesigned GIS workbench"
  ```

## Self-Review

### Spec Coverage

- Static visual/source layout: Tasks 2, 3, 5, and 6.
- All registered models and real forms: Tasks 3 and 5.
- Existing interactive/3D map preserved: Task 5.
- Single layer-control home for 2D, GLB, scan, and cooperative artifacts: Tasks 3 and 5.
- Compact task center and full result detail: Tasks 1 and 4.
- Cooperative station and gold intersection behavior: Tasks 3 and 5.
- Responsive/accessibility and visual verification: Task 6.
- No backend rewrite: Global Constraints and all task file scopes.

### Placeholder Scan

The plan specifies concrete component names, props/events, focused test names,
commands, expected outcomes, and commit scopes. No task depends on an unnamed
future component or an unspecified test behavior.

### Type Consistency

`ModelId`, `TaskSummary`, `SceneGlbKind`, output-layer state, and the existing
task-manager selection key remain the only cross-boundary domain types. New
presentation types are restricted to `workbench/taskPresentation.ts` and
`workbench/useWorkbenchPresentation.ts`; all map and GLB calls continue to
use the existing `useMapWorkspace` interface.
