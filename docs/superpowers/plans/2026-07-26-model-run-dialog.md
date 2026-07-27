# Model Run Dialog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the persistent right-hand parameter inspector with a reusable model run dialog that explicitly collects task inputs, spatial inputs, and analysis parameters.

**Architecture:** Add per-model input selections next to existing request drafts. The terrain slot bridges to `request.dem_id`, preserving current APIs. Extract parameter fields into a reusable component and control map picking through a compact command bar while the dialog is collapsed.

**Tech Stack:** Vue 3, TypeScript, Vitest, Vue Test Utils, Element Plus, Mapbox GL JS 3.27.0.

## Global Constraints

- No persistent inspector column and no map run button.
- Clicking a catalog model immediately opens its dialog.
- A task requires an explicit terrain selection sent through `request.dem_id`.
- Map picking shows neutral draft geometry only, never a radar volume, scan plane, GLB, or result layer.
- Point picks commit on one click; route picks provide undo, finish, and cancel.
- Closing the dialog preserves drafts and input selections.

## File Structure

- Create `frontend/src/models/inputSlots.ts` and `inputSlots.test.ts` for input-slot contracts and DEM bridging.
- Modify `frontend/src/models/shared.ts`, all `frontend/src/models/*/definition.ts`, and `frontend/src/composables/useModelWorkspace.ts` for per-model inputs.
- Create `frontend/src/components/workbench/ModelInputSlots.vue`, `ModelParameterFields.vue`, and `ModelRunDialog.vue`, each with a sibling test.
- Create `frontend/src/map/mapPickPolicy.ts` and `frontend/src/components/map/MapPickBar.vue`, each with a sibling test.
- Modify `frontend/src/components/map/MapWorkspace.vue`, `frontend/src/components/workbench/GisWorkbenchShell.vue`, `WorkbenchDock.vue`, `frontend/src/composables/useDemManager.ts`, and `frontend/src/App.vue` with their existing tests.
- Delete `frontend/src/components/workbench/WorkbenchInspector.vue` and `WorkbenchParameterPanel.vue` after migration.

## Task 1: Explicit input slots and isolated model drafts

**Files:**
- Create: `frontend/src/models/inputSlots.ts`
- Test: `frontend/src/models/inputSlots.test.ts`
- Modify: `frontend/src/models/shared.ts`
- Modify: every `frontend/src/models/*/definition.ts`
- Modify: `frontend/src/composables/useModelWorkspace.ts`
- Test: `frontend/src/composables/useModelWorkspace.test.ts`

**Interfaces:** Produces `InputSlotDefinition`, `ModelInputSelections`, `terrainInputSlot`, `createInputSelections`, `applyInputSelections`, `inputSelectionsFor`, and `updateInputSelections`.

- [ ] **Step 1: Write failing contract tests**

```ts
it("bridges explicit terrain selection into dem_id", () => {
  const inputs = createInputSelections([terrainInputSlot]);
  inputs.terrain = ["dem-42"];
  expect(applyInputSelections({ dem_id: "" }, inputs)).toEqual({ dem_id: "dem-42" });
});

it("keeps selections isolated by model", () => {
  const workspace = useModelWorkspace();
  workspace.updateInputSelections("radar", { terrain: ["dem-radar"] });
  expect(workspace.drafts.radar.dem_id).toBe("dem-radar");
  expect(workspace.inputSelectionsFor("uav").terrain).toEqual([]);
});
```

- [ ] **Step 2: Verify red state**

Run: `npm test -- --run src/models/inputSlots.test.ts src/composables/useModelWorkspace.test.ts`

Expected: FAIL because the input contract and workspace methods do not exist.

- [ ] **Step 3: Implement the contracts and workspace update**

```ts
export type AssetType = "dem" | "vector" | "table" | "route";
export interface InputSlotDefinition { key: string; label: string; assetTypes: readonly AssetType[]; required: boolean; multiple: boolean; }
export type ModelInputSelections = Record<string, string[]>;
export const terrainInputSlot: InputSlotDefinition = { key: "terrain", label: "Terrain DEM", assetTypes: ["dem"], required: true, multiple: false };
export const createInputSelections = (slots: readonly InputSlotDefinition[]) => Object.fromEntries(slots.map((slot) => [slot.key, []]));
export const applyInputSelections = <T extends { dem_id: string }>(request: T, inputs: ModelInputSelections): T => ({ ...request, dem_id: inputs.terrain?.[0] ?? "" });
```

Add `inputSlots: [terrainInputSlot]` to every current model definition and add `inputSlots` to `ModelDefinition`. In `useModelWorkspace`, clone input selections per model and apply them only to that model request. Remove `setDemForAll`.

- [ ] **Step 4: Verify green state and commit**

Run: `npm test -- --run src/models/inputSlots.test.ts src/composables/useModelWorkspace.test.ts`

Expected: PASS.

Commit: `git add frontend/src/models frontend/src/composables/useModelWorkspace.ts frontend/src/composables/useModelWorkspace.test.ts && git commit -m "feat: add explicit model input selections"`

## Task 2: Reusable model run dialog

**Files:**
- Create: `frontend/src/components/workbench/ModelInputSlots.vue`
- Test: `frontend/src/components/workbench/ModelInputSlots.test.ts`
- Create: `frontend/src/components/workbench/ModelParameterFields.vue`
- Test: `frontend/src/components/workbench/ModelParameterFields.test.ts`
- Create: `frontend/src/components/workbench/ModelRunDialog.vue`
- Test: `frontend/src/components/workbench/ModelRunDialog.test.ts`
- Modify: `frontend/src/components/workbench/WorkbenchParameterPanel.vue`

**Interfaces:** `ModelInputSlots` emits `update:selections`; `ModelParameterFields` emits `update:modelValue` and `activate-map-tool`; `ModelRunDialog` emits `update:open`, `update:request`, `update:inputs`, `activate-map-tool`, and `submit` with `{ request, inputs }`.

- [ ] **Step 1: Write failing dialog tests**

```ts
it("does not submit without required terrain", async () => {
  const wrapper = mount(ModelRunDialog, { props: dialogProps({ terrain: [] }) });
  await wrapper.get("[data-action='run-analysis']").trigger("click");
  expect(wrapper.emitted("submit")).toBeUndefined();
  expect(wrapper.get("[data-input-slot='terrain']").text()).toContain("required");
});

it("emits explicit request and inputs", async () => {
  const wrapper = mount(ModelRunDialog, { props: dialogProps({ terrain: ["dem-1"] }) });
  await wrapper.get("[data-action='run-analysis']").trigger("click");
  expect(wrapper.emitted("submit")?.[0]?.[0]).toMatchObject({ request: { dem_id: "dem-1" }, inputs: { terrain: ["dem-1"] } });
});
```

- [ ] **Step 2: Verify red state**

Run: `npm test -- --run src/components/workbench/ModelInputSlots.test.ts src/components/workbench/ModelParameterFields.test.ts src/components/workbench/ModelRunDialog.test.ts`

Expected: FAIL because these components do not exist.

- [ ] **Step 3: Implement reusable fields and dialog**

Move the current parameter schema and update helpers from `WorkbenchParameterPanel.vue` into `ModelParameterFields.vue`. Coordinate fields remain read-only and expose a labelled map-pick icon. `ModelInputSlots.vue` renders stable `data-input-slot` rows, uses `DemMetadata` for current terrain options, and honours the future `multiple` contract through a multi-select.

```ts
export interface ModelRunSubmission { request: BaseModelRequest; inputs: ModelInputSelections; }
function submit() {
  showValidation.value = true;
  if (props.slots.some((slot) => slot.required && !props.inputs[slot.key]?.length)) return;
  emit("submit", { request: props.request, inputs: props.inputs });
}
```

Cancel only emits `update:open` with `false`; it never clears the draft. Leave the current parameter panel as a thin compatibility wrapper until Task 3 deletes its final consumer.

- [ ] **Step 4: Verify green state and commit**

Run: `npm test -- --run src/components/workbench/ModelInputSlots.test.ts src/components/workbench/ModelParameterFields.test.ts src/components/workbench/ModelRunDialog.test.ts src/components/workbench/WorkbenchParameterPanel.test.ts`

Expected: PASS.

Commit: `git add frontend/src/components/workbench && git commit -m "feat: add reusable model run dialog"`

## Task 3: Dialog-driven map picking and shell integration

**Files:**
- Create: `frontend/src/map/mapPickPolicy.ts`
- Test: `frontend/src/map/mapPickPolicy.test.ts`
- Create: `frontend/src/components/map/MapPickBar.vue`
- Test: `frontend/src/components/map/MapPickBar.test.ts`
- Modify: `frontend/src/components/map/MapWorkspace.vue` and `MapWorkspace.test.ts`
- Modify: `frontend/src/components/workbench/GisWorkbenchShell.vue` and test
- Modify: `frontend/src/components/workbench/WorkbenchDock.vue` and test
- Modify: `frontend/src/composables/useDemManager.ts` and test
- Modify: `frontend/src/App.vue` and `App.test.ts`
- Delete: `frontend/src/components/workbench/WorkbenchInspector.vue`, `WorkbenchParameterPanel.vue`, and their tests

**Interfaces:** Produces `MapPickTarget`, `isCoordinateInDemBounds`, MapPickBar cancel/undo/finish events, and `MapWorkspace` `out-of-bounds` events.

- [ ] **Step 1: Write failing map and integration tests**

```ts
it("rejects a click outside selected DEM bounds", () => {
  expect(isCoordinateInDemBounds([80.1, 31.5], [79.7, 31.4, 79.9, 31.6])).toBe(false);
});

it("opens the selected model dialog immediately", async () => {
  const wrapper = mount(App, { global: appStubs });
  await wrapper.get("[data-model-id='radar']").trigger("click");
  expect(wrapper.get("[data-model-run-dialog='radar']").isVisible()).toBe(true);
});

it("has no inspector or map run action", () => {
  const wrapper = mount(App, { global: appStubs });
  expect(wrapper.find("[data-workbench-region='inspector']").exists()).toBe(false);
  expect(wrapper.find("[data-action='run-analysis-on-map']").exists()).toBe(false);
});
```

- [ ] **Step 2: Verify red state**

Run: `npm test -- --run src/map/mapPickPolicy.test.ts src/components/map/MapPickBar.test.ts src/components/workbench/GisWorkbenchShell.test.ts src/App.test.ts`

Expected: FAIL because the policy, command bar, dialog integration, and two-column layout are absent.

- [ ] **Step 3: Implement map policy and compact command bar**

```ts
export type MapPickTarget = "point" | "route" | "start" | "end" | "threat";
export const isSingleClickTarget = (target: MapPickTarget) => target !== "route";
export const isCoordinateInDemBounds = ([lon, lat]: [number, number], bounds: readonly number[]) => bounds.length === 4 && lon >= bounds[0] && lon <= bounds[2] && lat >= bounds[1] && lat <= bounds[3];
```

`MapWorkspace` emits `out-of-bounds` and no `spatial-edit` if no selected DEM exists or a click fails the bounds gate. `MapPickBar` always offers Cancel and adds Undo and Finish only for route selection. It is an editing command, never a run control.

- [ ] **Step 4: Wire dialog state and remove the inspector**

```ts
const runDialogOpen = ref(false);
const configuredModelId = ref<ModelId | null>(null);
const mapPickTarget = ref<MapPickTarget | null>(null);
function openModelRunDialog(modelId: ModelId) { workspace.selectModel(modelId); configuredModelId.value = modelId; runDialogOpen.value = true; }
function submitModelRun({ request, inputs }: ModelRunSubmission) { const modelId = configuredModelId.value; if (!modelId) return; workspace.updateInputSelections(modelId, inputs); workspace.currentDraft.value = { modelId, request } as ActiveDraft; runDialogOpen.value = false; void submitTask(request); }
```

Catalog selection calls `openModelRunDialog`. A dialog map-pick command sets `mapPickTarget` and closes the dialog; a point commit or route finish clears it and restores the dialog. Retain existing `applyMapEdit` for request conversion. Change `GisWorkbenchShell` to the two-column `dock map` layout, remove its inspector slot, remove `setDemForAll` use from `useDemManager`, and delete the retired inspector components.

- [ ] **Step 5: Verify green state and commit**

Run: `npm test -- --run src/map/mapPickPolicy.test.ts src/components/map/MapPickBar.test.ts src/components/map/MapWorkspace.test.ts src/components/workbench/GisWorkbenchShell.test.ts src/components/workbench/WorkbenchDock.test.ts src/composables/useDemManager.test.ts src/App.test.ts`

Expected: PASS.

Run: `npm run build`

Expected: exit code 0.

Run: `git diff --check`

Expected: no output.

Run: `git grep -n "WorkbenchInspector\|WorkbenchParameterPanel\|setDemForAll\|run-analysis-on-map" -- frontend/src`

Expected: no retired production references.

Commit: `git add frontend/src && git commit -m "feat: configure models through run dialogs"`

## Self-Review

- Task 1 implements explicit per-model inputs and the compatibility bridge.
- Task 2 implements the reusable configuration dialog and its validation.
- Task 3 implements the agreed map-picking behavior, removes the inspector, and validates the final production build.
- A generic backend asset registry is intentionally outside this phase. The current terrain slot is explicit now, while the slot type and cardinality contract supports future vector, table, route, and multiple-file inputs.
