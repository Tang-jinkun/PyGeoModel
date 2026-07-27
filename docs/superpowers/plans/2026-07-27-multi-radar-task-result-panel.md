# Multi-Radar Task Result Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make multi-radar history tasks open the existing right-side inspector with all outputs, while aligning terminal task-row actions without an empty progress column.

**Architecture:** `WorkbenchTaskCenter` emits an explicit multi-radar intent for layer viewing or file inspection. `App.vue` resolves canonical multi-radar output descriptors, stores a multi-radar result context, and either loads aggregate map layers or exposes the task to the existing `WorkbenchInspector`. A small shared result-context module gives the inspector a label and metric definitions without pretending a multi-radar task is a radar task.

**Tech Stack:** Vue 3 Composition API, TypeScript, Vitest, Vue Test Utils, existing multi-radar REST client and MapLibre layer adapter.

## Global Constraints

- Reuse `WorkbenchInspector` and its existing output-files section; do not add a second result panel, drawer, or modal.
- Use canonical `output_files` descriptors from `/api/radar/multi-coverage/{task_id}/outputs`.
- Only existing descriptors with `download_path` are downloadable.
- Only pending and running rows render a progress column.

---

### Task 1: Tighten Task-Center Rows And Expose Multi-Radar Actions

**Files:**
- Modify: `frontend/src/components/workbench/WorkbenchTaskCenter.vue`
- Modify: `frontend/src/components/workbench/WorkbenchTaskCenter.test.ts`

**Interfaces:**
- Consumes: `MultiRadarTask.status`, `MultiRadarTask.output_files`.
- Produces: `select-multi-radar-task(taskId, intent)` where `intent` is `"layers" | "files"`.

- [ ] **Step 1: Write failing component tests**

```ts
it("renders terminal multi-radar actions and emits their intent", async () => {
  const wrapper = mount(WorkbenchTaskCenter, {
    props: { rows: [], activeTab: "history", multiRadarTasks: [multiRadarTask("finished")] }
  });

  await wrapper.get('[data-multi-radar-task] [data-action="layers"]').trigger("click");
  await wrapper.get('[data-multi-radar-task] [data-action="files"]').trigger("click");

  expect(wrapper.emitted("select-multi-radar-task")).toEqual([
    ["multi-1", "layers"],
    ["multi-1", "files"]
  ]);
});

it("does not reserve a progress placeholder for a completed task", () => {
  const wrapper = mount(WorkbenchTaskCenter, { props: { rows: [finishedRadarRow()], activeTab: "history" } });
  expect(wrapper.get('[data-task-key="radar:radar-1"]').classes()).toContain("is-terminal");
  expect(wrapper.find('[data-task-key="radar:radar-1"] .progress').exists()).toBe(false);
});
```

- [ ] **Step 2: Run the focused component tests and verify failure**

Run: `npm run test -- --run src/components/workbench/WorkbenchTaskCenter.test.ts`

Expected: failures because multi-radar action elements and terminal-row class do not exist, and the event has no intent argument.

- [ ] **Step 3: Implement the minimal task-center contract and layout**

```ts
type MultiRadarTaskIntent = "layers" | "files";
const emit = defineEmits<{
  "select-multi-radar-task": [taskId: string, intent: MultiRadarTaskIntent];
}>();
function isTerminalMultiRadarTask(task: MultiRadarTask) {
  return !isMultiRadarRunning(task);
}
```

Render `data-action="layers"` and `data-action="files"` buttons only for ready finished or partial multi-radar tasks. Give all non-running rows the `is-terminal` class, remove the empty progress `<span>`, and use a terminal grid with no 200px progress track:

```css
.task-row { grid-template-columns: 92px 170px minmax(0, 1fr) 200px 140px max-content; }
.task-row.is-terminal { grid-template-columns: 92px 170px minmax(0, 1fr) 140px max-content; }
```

Keep a failed row action limited to its log command.

- [ ] **Step 4: Run the focused component tests and verify success**

Run: `npm run test -- --run src/components/workbench/WorkbenchTaskCenter.test.ts`

Expected: all task-center tests pass.

- [ ] **Step 5: Commit the task-center change**

```powershell
git add frontend/src/components/workbench/WorkbenchTaskCenter.vue frontend/src/components/workbench/WorkbenchTaskCenter.test.ts
git commit -m "fix: expose multi-radar task actions"
```

### Task 2: Represent Multi-Radar Results In The Existing Inspector

**Files:**
- Create: `frontend/src/workbench/resultContext.ts`
- Create: `frontend/src/workbench/resultContext.test.ts`
- Modify: `frontend/src/components/workbench/WorkbenchInspector.vue`
- Modify: `frontend/src/components/workbench/WorkbenchInspector.test.ts`

**Interfaces:**
- Consumes: `MultiRadarTask`, `OutputFile`, and existing model task contexts.
- Produces: `WorkbenchResultContext`, `resultContextLabel(context)`, and `resultContextMetrics(context)`.

- [ ] **Step 1: Write failing result-context tests**

```ts
it("labels a multi-radar context and exposes union metrics", () => {
  const context = multiRadarContext();
  expect(resultContextLabel(context)).toBe("多雷达协同");
  expect(resultContextMetrics(context)).toEqual(expect.arrayContaining([
    expect.objectContaining({ key: "visible_union_area_m2" }),
    expect.objectContaining({ key: "overlap_area_m2" }),
    expect.objectContaining({ key: "blind_area_m2" })
  ]));
});
```

Add an inspector test that passes a multi-radar context with two output descriptors and asserts the multi-radar label, union-visible metric, and both download links.

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `npm run test -- --run src/workbench/resultContext.test.ts src/components/workbench/WorkbenchInspector.test.ts`

Expected: failure because the context helpers and multi-radar inspector path do not exist.

- [ ] **Step 3: Implement the shared result context and inspector branch**

```ts
export type WorkbenchResultContext =
  | { kind: "model"; modelId: ModelId; task: GenericTask }
  | { kind: "multi-radar"; task: MultiRadarTask };

export const MULTI_RADAR_METRICS: MetricDefinition<Record<string, unknown>>[] = [
  { key: "visible_union_area_m2", label: "Union visible area", format: "area" },
  { key: "overlap_area_m2", label: "Overlap area", format: "area" },
  { key: "blind_area_m2", label: "Blind area", format: "area" },
  { key: "theoretical_union_area_m2", label: "Theoretical union area", format: "area" },
  { key: "successful_station_count", label: "Successful stations", format: "number" },
  { key: "failed_station_count", label: "Failed stations", format: "number" }
];
```

Use the context helpers in `WorkbenchInspector` for its header label and metric definitions. Keep the existing output-files section unchanged so it lists every existing canonical descriptor. Preserve existing behavior for all single-model contexts.

- [ ] **Step 4: Run the focused tests and verify success**

Run: `npm run test -- --run src/workbench/resultContext.test.ts src/components/workbench/WorkbenchInspector.test.ts`

Expected: all focused tests pass, including existing single-model inspector tests.

- [ ] **Step 5: Commit the result-context and inspector change**

```powershell
git add frontend/src/workbench/resultContext.ts frontend/src/workbench/resultContext.test.ts frontend/src/components/workbench/WorkbenchInspector.vue frontend/src/components/workbench/WorkbenchInspector.test.ts
git commit -m "feat: show multi-radar results in inspector"
```

### Task 3: Route Task-Center Intents Through The Existing Result And Map Flow

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/App.test.ts`

**Interfaces:**
- Consumes: `WorkbenchResultContext`, `getMultiRadarTask(taskId)`, and `getMultiRadarOutputs(taskId)`.
- Produces: multi-radar selection that populates the inspector, opens the task-result mode, and conditionally loads aggregate layers.

- [ ] **Step 1: Write a failing application test**

Mock `getMultiRadarTask` and `getMultiRadarOutputs`, emit `select-multi-radar-task` with `"files"`, then assert that the existing inspector receives a multi-radar context and its output file list. Repeat with `"layers"` and assert `showMultiRadarAggregate` is invoked with the canonical descriptors.

- [ ] **Step 2: Run the focused application test and verify failure**

Run: `npm run test -- --run src/App.test.ts`

Expected: failure because multi-radar selection does not provide an inspector context or distinguish file and layer intents.

- [ ] **Step 3: Implement intent-aware selection without a second panel**

```ts
async function selectMultiRadarTask(taskId: string, intent: "layers" | "files" = "layers") {
  const task = await getMultiRadarTask(taskId);
  const outputFiles = await getMultiRadarOutputs(taskId);
  const resolved = { ...task, output_files: outputFiles };
  selectedMultiRadarResultTask.value = resolved;
  activeMultiRadarTask.value = resolved;
  presentation.selectTask();
  if (intent === "layers" && resolved.result_state === "ready") {
    await showMultiRadarAggregate(resolved, outputFiles);
  }
}
```

Derive a `WorkbenchResultContext` that prefers `selectedMultiRadarResultTask` after a multi-radar selection, clears it when `selectWorkbenchTask` selects a single-model task, and supplies the inspector with either canonical multi-radar outputs or the existing map-workspace outputs. Update `showMultiRadarAggregate` to accept already fetched descriptors so the layer path does not fetch them twice.

- [ ] **Step 4: Run frontend verification and inspect the running application**

Run: `npm run test -- --run src/App.test.ts src/components/workbench/WorkbenchTaskCenter.test.ts src/components/workbench/WorkbenchInspector.test.ts src/workbench/resultContext.test.ts`

Expected: all selected tests pass.

Then rebuild the frontend container and inspect `http://127.0.0.1:5173`: a completed multi-radar history row has adjacent status/actions, `View layers` renders aggregate layers, and `Download` exposes all existing descriptors in the right inspector.

- [ ] **Step 5: Commit the application wiring**

```powershell
git add frontend/src/App.vue frontend/src/App.test.ts
git commit -m "fix: route multi-radar task results to inspector"
```
