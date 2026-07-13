# PyGeoModel Multi-Model GIS Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the radar-only frontend with one map-first workspace that can configure, execute, inspect, and visualize all seven backend models without Docker.

**Architecture:** Keep one Vue application shell and one MapLibre map. A typed model registry owns per-model defaults, validation, metrics, and output-layer metadata; shared composables own DEM state, task polling, workspace drafts, and map state. Complex spatial inputs and radar-only analysis remain explicit components instead of becoming an open-ended schema renderer.

**Tech Stack:** Vue 3.5, TypeScript 5.7, Vite 6, Element Plus 2.9, MapLibre GL 4.7, Three.js 0.171, Vitest, Vue Test Utils, Happy DOM.

## Global Constraints

- Keep all seven existing backend API paths unchanged.
- Keep Vue 3, TypeScript, Element Plus, MapLibre GL, and Three.js; do not add a global state library.
- Local startup remains `npm run dev` plus local Uvicorn; Docker is not required.
- The map remains the primary work area; parameter and result panels must be independently collapsible.
- Use neutral gray and white surfaces, a charcoal header, blue primary actions, and semantic green/orange/red statuses; do not add gradients or nested page cards.
- Panel/control radii stay between 4px and 6px; body text stays between 13px and 14px without viewport-scaled font sizes.
- Preserve radar coverage, height layers, profile, fusion, radar volume, voxel, and clipped-volume behavior.
- A missing local `gdal_viewshed` must appear as a task failure and must not be replaced with fabricated output.
- Do not stage or commit `backend/*.local*.log` or `frontend/*.local*.log` files.

---

## File Map

### Shared platform

- `frontend/src/api/http.ts`: fetch wrapper, API errors, and output URL resolution.
- `frontend/src/api/dem.ts`: DEM list/upload/delete and tile URL functions.
- `frontend/src/api/tasks.ts`: generic list/create/get/metrics/outputs/delete calls.
- `frontend/src/api/radar.ts`: profile and fusion calls only.
- `frontend/src/models/shared.ts`: common task, metric, output, layer, and model-definition types.
- `frontend/src/models/registry.ts`: the seven-model registry and lookup helpers.
- `frontend/src/models/<model>/types.ts`: exact request/metric types for one backend schema.
- `frontend/src/models/<model>/definition.ts`: defaults, validation, metrics, and output layers for one model.
- `frontend/src/composables/useTaskManager.ts`: concurrent task polling and history.
- `frontend/src/composables/useModelWorkspace.ts`: current model and one draft per model.
- `frontend/src/composables/useDemManager.ts`: DEM list, selection, upload, and deletion.
- `frontend/src/composables/useMapWorkspace.ts`: spatial input and result-layer orchestration.

### UI and map

- `frontend/src/components/layout/AppHeader.vue`: DEM summary, connection state, and history/settings commands.
- `frontend/src/components/layout/ModelNavigation.vue`: seven-model navigation.
- `frontend/src/components/layout/WorkspaceShell.vue`: desktop grid and narrow-screen drawers.
- `frontend/src/components/forms/*.vue`: one explicit form per model.
- `frontend/src/components/map/MapWorkspace.vue`: map host and spatial editing toolbar.
- `frontend/src/components/map/CoordinateEditor.vue`: coordinate fields plus map-pick action.
- `frontend/src/components/map/RouteEditor.vue`: ordered waypoint editing.
- `frontend/src/components/map/ThreatEditor.vue`: air-defense threat editing.
- `frontend/src/components/tasks/TaskResultPanel.vue`: task, metrics, layers, and files tabs.
- `frontend/src/components/tasks/TaskHistoryDrawer.vue`: filter, restore, focus, and delete task history.
- `frontend/src/map/spatialInput.ts`: pure spatial-input reducer and GeoJSON conversion.
- `frontend/src/map/modelLayers.ts`: generic GeoJSON layer lifecycle.
- Existing `frontend/src/map/radarVolumeLayer.ts`, `voxelLayer.ts`, and `clippedVolumeLayer.ts`: retained radar renderers.

### Tests

- `frontend/src/**/*.test.ts`: colocated unit/component tests.
- `frontend/src/test/setup.ts`: DOM and MapLibre test cleanup.

---

### Task 1: Test Harness and Typed Model Registry

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `frontend/vite.config.ts`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/src/models/shared.ts`
- Create: `frontend/src/models/registry.ts`
- Create: `frontend/src/models/registry.test.ts`
- Create: `frontend/src/models/{radar,uav,watchpost,artillery,reconVehicle,mobility,airCorridor}/types.ts`
- Create: `frontend/src/models/{radar,uav,watchpost,artillery,reconVehicle,mobility,airCorridor}/definition.ts`

**Interfaces:**
- Produces: `ModelId`, `ModelRequestMap`, `TaskSummary`, `ModelDefinition`, `MODEL_REGISTRY`, `getModelDefinition()`.
- Consumes: exact Pydantic field names and constraints from `backend/app/schemas/*.py`.

- [ ] **Step 1: Install the test and icon dependencies**

Run:

```powershell
cd frontend
npm install @element-plus/icons-vue
npm install -D vitest @vue/test-utils happy-dom
```

Expected: `package.json` contains `@element-plus/icons-vue`, `vitest`, `@vue/test-utils`, and `happy-dom`; lockfile changes only reflect those packages.

- [ ] **Step 2: Add the failing registry contract test**

Add script `"test": "vitest run"` and this test:

```ts
import { describe, expect, it } from "vitest";
import { MODEL_IDS, MODEL_REGISTRY, getModelDefinition } from "./registry";

describe("model registry", () => {
  it("registers every backend model with a unique task path", () => {
    expect(MODEL_IDS).toEqual([
      "radar", "uav", "watchpost", "artillery", "reconVehicle", "mobility", "airCorridor"
    ]);
    expect(MODEL_IDS.map((id) => MODEL_REGISTRY[id].taskBasePath)).toEqual([
      "/api/radar/coverage",
      "/api/uav/recon",
      "/api/watchpost/detection",
      "/api/artillery/coverage",
      "/api/recon-vehicle/coverage",
      "/api/mobility/accessibility",
      "/api/air-corridor/planning"
    ]);
    expect(new Set(MODEL_IDS.map((id) => getModelDefinition(id).taskBasePath)).size).toBe(7);
  });

  it("provides a new default request and at least one output layer per model", () => {
    for (const id of MODEL_IDS) {
      const first = MODEL_REGISTRY[id].createDefaultRequest();
      const second = MODEL_REGISTRY[id].createDefaultRequest();
      expect(first).not.toBe(second);
      expect(first.dem_id).toBe("");
      expect(MODEL_REGISTRY[id].outputLayers.length).toBeGreaterThan(0);
    }
  });
});
```

- [ ] **Step 3: Run the test and verify the missing registry failure**

Run: `npm test -- src/models/registry.test.ts`

Expected: FAIL because `./registry` does not exist.

- [ ] **Step 4: Implement shared contracts and model definitions**

Use these exact shared contracts:

```ts
export const MODEL_IDS = ["radar", "uav", "watchpost", "artillery", "reconVehicle", "mobility", "airCorridor"] as const;
export type ModelId = (typeof MODEL_IDS)[number];
export type TaskStatus = "pending" | "running" | "finished" | "failed";
export type SpatialInputKind = "point" | "point-or-route" | "start-end" | "start-end-threats";

export interface BaseModelRequest { dem_id: string }
export interface OutputFile {
  kind: string; label: string; url: string; download_url: string; filename: string;
  media_type: string; size_bytes?: number | null; exists: boolean;
}
export interface TaskSummary<Request extends BaseModelRequest = BaseModelRequest, Metrics = Record<string, unknown>> {
  task_id: string; dem_id?: string | null; status: TaskStatus; progress: number; message: string;
  created_at?: string | null; updated_at?: string | null; request?: Request | null;
  metrics?: Metrics | null; outputs?: Record<string, string | null> | null;
  output_files: OutputFile[]; warnings: string[];
}
export interface MetricDefinition<Metrics> {
  key: keyof Metrics & string; label: string; format: "area" | "distance" | "duration" | "percent" | "number" | "text";
}
export interface OutputLayerDefinition {
  kind: string; label: string; color: string; geometry: "fill" | "line" | "circle";
  defaultOpacity: number; primary?: boolean;
}
export interface ValidationIssue { path: string; message: string }
export interface ModelDefinition<Request extends BaseModelRequest, Metrics> {
  id: ModelId; label: string; taskBasePath: string; spatialInput: SpatialInputKind;
  createDefaultRequest(): Request; validate(request: Request): ValidationIssue[];
  metrics: MetricDefinition<Metrics>[]; outputLayers: OutputLayerDefinition[];
}
```

Each model `types.ts` must mirror its backend request and metrics schema. Each `definition.ts` must provide fresh nested defaults and enforce backend cross-field rules. Use this exact output-layer mapping:

| Model | Output kinds |
| --- | --- |
| radar | `range_geojson`, `blocked_geojson`, `visible_geojson` |
| uav | `footprint_geojson`, `blocked_geojson`, `visible_geojson` |
| watchpost | `range_geojson`, `blocked_geojson`, `visible_geojson` |
| artillery | `theoretical_geojson`, `terrain_masked_geojson`, `reachable_geojson`, `sample_points_geojson` |
| reconVehicle | `footprint_geojson`, `blocked_geojson`, `visible_geojson` |
| mobility | `road_mask_geojson`, `wheeled_path_geojson`, `tracked_path_geojson` |
| airCorridor | `threat_zones_geojson`, `corridor_buffer_geojson`, `corridor_path_geojson`, `risk_samples_geojson` |

Register imported definitions with a type-checked object:

```ts
export const MODEL_REGISTRY = {
  radar: radarDefinition,
  uav: uavDefinition,
  watchpost: watchpostDefinition,
  artillery: artilleryDefinition,
  reconVehicle: reconVehicleDefinition,
  mobility: mobilityDefinition,
  airCorridor: airCorridorDefinition
} satisfies { [K in ModelId]: ModelDefinition<ModelRequestMap[K], ModelMetricMap[K]> };

export function getModelDefinition<K extends ModelId>(id: K) {
  return MODEL_REGISTRY[id];
}
```

- [ ] **Step 5: Configure Vitest and run registry tests**

Add to `vite.config.ts`:

```ts
import { defineConfig } from "vitest/config";

test: {
  environment: "happy-dom",
  setupFiles: ["./src/test/setup.ts"],
  restoreMocks: true
}
```

Replace the existing `defineConfig` import from `vite`; keep the Vue plugin and proxy configuration unchanged. Add this setup file:

```ts
import { afterEach } from "vitest";

afterEach(() => {
  document.body.innerHTML = "";
});
```

Run: `npm test -- src/models/registry.test.ts`

Expected: PASS with 2 tests.

- [ ] **Step 6: Commit the registry foundation**

```powershell
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/src/test frontend/src/models
git commit -m "test: add typed model registry foundation"
```

---

### Task 2: Shared HTTP, DEM, Task, and Radar Clients

**Files:**
- Create: `frontend/src/api/http.ts`
- Create: `frontend/src/api/http.test.ts`
- Create: `frontend/src/api/dem.ts`
- Create: `frontend/src/api/tasks.ts`
- Create: `frontend/src/api/tasks.test.ts`
- Create: `frontend/src/api/radar.ts`
- Modify: `frontend/src/api/client.ts`

**Interfaces:**
- Consumes: `ModelDefinition`, `TaskSummary`, `OutputFile`, existing radar request/profile/fusion types.
- Produces: `requestJson<T>()`, `taskClient`, `listDems()`, `uploadDem()`, `deleteDem()`, `getCoverageProfile()`, `createFusionAnalysis()`.

- [ ] **Step 1: Write failing HTTP and generic task tests**

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, requestJson, resolveAssetUrl } from "./http";
import { createTaskClient } from "./tasks";

afterEach(() => vi.unstubAllGlobals());

describe("requestJson", () => {
  it("normalizes FastAPI detail messages", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: { message: "DEM missing" } }),
      { status: 404, headers: { "Content-Type": "application/json" } }
    )));
    await expect(requestJson("/api/test")).rejects.toEqual(expect.objectContaining<ApiError>({ message: "DEM missing", status: 404 }));
  });
  it("resolves relative output URLs", () => {
    expect(resolveAssetUrl("/outputs/a.geojson")).toBe("/outputs/a.geojson");
  });
});

describe("createTaskClient", () => {
  it("uses one model base path for the full lifecycle", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const client = createTaskClient("/api/uav/recon");
    await client.list();
    await client.outputs("t-1");
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/uav/recon", "/api/uav/recon/t-1/outputs"
    ]);
  });
});
```

- [ ] **Step 2: Run tests and verify missing-module failures**

Run: `npm test -- src/api/http.test.ts src/api/tasks.test.ts`

Expected: FAIL because `http.ts` and `tasks.ts` do not exist.

- [ ] **Step 3: Implement the shared clients**

Implement the task surface exactly as:

```ts
export function createTaskClient<Request extends BaseModelRequest, Metrics>(basePath: string) {
  return {
    list: () => requestJson<TaskSummary<Request, Metrics>[]>(basePath),
    create: (payload: Request) => requestJson<TaskSummary<Request, Metrics>>(basePath, { method: "POST", body: JSON.stringify(payload) }),
    get: (taskId: string) => requestJson<TaskSummary<Request, Metrics>>(`${basePath}/${taskId}`),
    metrics: (taskId: string) => requestJson<Metrics>(`${basePath}/${taskId}/metrics`),
    outputs: (taskId: string) => requestJson<OutputFile[]>(`${basePath}/${taskId}/outputs`),
    delete: (taskId: string) => requestJson<TaskDeleteResult>(`${basePath}/${taskId}`, { method: "DELETE" })
  };
}
```

`requestJson()` must add `Content-Type: application/json` only when a body is present, parse FastAPI `detail.message`, `detail`, or HTTP status text in that order, and throw `ApiError(status, message, payload)`. Move DEM functions unchanged into `dem.ts`; move profile/fusion functions unchanged into `radar.ts`. Keep `client.ts` as temporary re-exports so the existing radar UI builds during migration.

- [ ] **Step 4: Run client tests and the production build**

Run: `npm test -- src/api/http.test.ts src/api/tasks.test.ts`

Expected: PASS.

Run: `npm run build`

Expected: `vue-tsc -b` and Vite both exit 0.

- [ ] **Step 5: Commit the API split**

```powershell
git add frontend/src/api
git commit -m "refactor: add shared model task clients"
```

---

### Task 3: Concurrent Task Manager

**Files:**
- Create: `frontend/src/composables/useTaskManager.ts`
- Create: `frontend/src/composables/useTaskManager.test.ts`

**Interfaces:**
- Consumes: `ModelId`, `TaskSummary`, `getModelDefinition()`, `createTaskClient()`.
- Produces: `useTaskManager({ pollIntervalMs, maxRetryDelayMs })` with `tasksByModel`, `selectedTaskKey`, `submit`, `refreshModel`, `select`, `remove`, `restoreRequest`, and `dispose`.

- [ ] **Step 1: Write failing polling and model-switch tests**

```ts
import { describe, expect, it, vi } from "vitest";
import { useTaskManager } from "./useTaskManager";

describe("useTaskManager", () => {
  it("continues polling a UAV task when the visible model changes", async () => {
    vi.useFakeTimers();
    const get = vi.fn()
      .mockResolvedValueOnce({ task_id: "u1", status: "running", progress: 25, output_files: [], warnings: [] })
      .mockResolvedValueOnce({ task_id: "u1", status: "finished", progress: 100, output_files: [], warnings: [] });
    const manager = useTaskManager({ pollIntervalMs: 1000, clientFactory: () => ({ get }) });
    manager.track("uav", { task_id: "u1", status: "running", progress: 0, output_files: [], warnings: [] });
    manager.setVisibleModel("radar");
    await vi.advanceTimersByTimeAsync(2000);
    expect(get).toHaveBeenCalledTimes(2);
    expect(manager.getTask("uav", "u1")?.status).toBe("finished");
    manager.dispose();
  });
});
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `npm test -- src/composables/useTaskManager.test.ts`

Expected: FAIL because `useTaskManager.ts` does not exist.

- [ ] **Step 3: Implement keyed task state and bounded retry**

Use `const key = (modelId, taskId) => `${modelId}:${taskId}`` for identity. Store one timeout handle per active key, stop polling on `finished` or `failed`, and use retry delays `min(pollIntervalMs * 2 ** failures, maxRetryDelayMs)`. A successful request resets the failure count. `dispose()` clears every timer. `remove()` calls the backend first and only then removes the local task.

Expose readonly state plus commands:

```ts
return {
  tasksByModel: readonly(tasksByModel),
  selectedTaskKey: readonly(selectedTaskKey),
  connectionInterrupted: readonly(connectionInterrupted),
  submit, track, refreshModel, setVisibleModel, getTask, select, remove, restoreRequest, dispose
};
```

- [ ] **Step 4: Test finish, failure, retry, deletion, and cleanup**

Add tests asserting no timer remains after terminal states, retry delay never exceeds the configured maximum, delete failure retains the task, and `dispose()` prevents later fetch calls.

Run: `npm test -- src/composables/useTaskManager.test.ts`

Expected: PASS with all task manager tests.

- [ ] **Step 5: Commit the task manager**

```powershell
git add frontend/src/composables/useTaskManager.ts frontend/src/composables/useTaskManager.test.ts
git commit -m "feat: manage concurrent model tasks"
```

---

### Task 4: Workspace Shell and Visual System

**Files:**
- Create: `frontend/src/components/layout/AppHeader.vue`
- Create: `frontend/src/components/layout/ModelNavigation.vue`
- Create: `frontend/src/components/layout/ModelNavigation.test.ts`
- Create: `frontend/src/components/layout/WorkspaceShell.vue`
- Modify: `frontend/src/styles/app.css`

**Interfaces:**
- Consumes: `MODEL_IDS`, `MODEL_REGISTRY`, `ModelId`.
- Produces: layout slots `header`, `navigation`, `parameters`, `map`, `results`; emits `select-model`, `open-history`, `toggle-parameters`, and `toggle-results`.

- [ ] **Step 1: Write the failing navigation component test**

```ts
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import ModelNavigation from "./ModelNavigation.vue";

describe("ModelNavigation", () => {
  it("renders and selects all seven models", async () => {
    const wrapper = mount(ModelNavigation, { props: { modelValue: "radar" } });
    expect(wrapper.findAll("[data-model-id]")).toHaveLength(7);
    await wrapper.get('[data-model-id="mobility"]').trigger("click");
    expect(wrapper.emitted("update:modelValue")?.[0]).toEqual(["mobility"]);
  });
});
```

- [ ] **Step 2: Run the test and verify the missing component failure**

Run: `npm test -- src/components/layout/ModelNavigation.test.ts`

Expected: FAIL because `ModelNavigation.vue` does not exist.

- [ ] **Step 3: Implement shell components and CSS tokens**

Define stable tokens in `:root`:

```css
:root {
  --header-height: 52px;
  --model-nav-width: 88px;
  --parameter-width: 320px;
  --result-width: 360px;
  --surface: #ffffff;
  --workspace: #eef1f4;
  --header: #20262d;
  --border: #d7dde3;
  --text: #20262d;
  --muted: #66717d;
  --primary: #2563eb;
  --success: #16845b;
  --warning: #c56a12;
  --danger: #c43d4b;
  --radius: 5px;
}
```

Use CSS grid tracks `var(--model-nav-width) var(--parameter-width) minmax(320px, 1fr) var(--result-width)` and fixed `var(--header-height)`. Buttons use Element Plus icons with `aria-label` and tooltips. At `max-width: 1100px`, reduce the model navigation to icons while preserving tooltips and accessible labels. At `max-width: 800px`, render parameter and result regions as fixed drawers and allow only one open drawer.

- [ ] **Step 4: Run navigation tests and build**

Run: `npm test -- src/components/layout/ModelNavigation.test.ts`

Expected: PASS.

Run: `npm run build`

Expected: exit 0.

- [ ] **Step 5: Commit the shell**

```powershell
git add frontend/src/components/layout frontend/src/styles/app.css
git commit -m "feat: add GIS workspace shell"
```

---

### Task 5: DEM Manager and Workspace Drafts

**Files:**
- Create: `frontend/src/composables/useDemManager.ts`
- Create: `frontend/src/composables/useDemManager.test.ts`
- Create: `frontend/src/composables/useModelWorkspace.ts`
- Create: `frontend/src/composables/useModelWorkspace.test.ts`
- Create: `frontend/src/components/dem/DemSelector.vue`
- Create: `frontend/src/components/dem/DemSelector.test.ts`

**Interfaces:**
- Consumes: DEM API functions and model defaults.
- Produces: selected DEM shared across models and one isolated request draft per `ModelId`.

- [ ] **Step 1: Write failing state-isolation tests**

```ts
it("keeps a separate mutable draft for every model", () => {
  const workspace = useModelWorkspace();
  workspace.selectModel("uav");
  workspace.currentDraft.value.dem_id = "dem-a";
  workspace.selectModel("radar");
  expect(workspace.currentDraft.value.dem_id).toBe("");
  workspace.setDemForAll("dem-b");
  expect(workspace.drafts.uav.dem_id).toBe("dem-b");
  expect(workspace.drafts.radar.dem_id).toBe("dem-b");
});
```

Test DEM deletion so the selected DEM is cleared only after the API succeeds.

- [ ] **Step 2: Run tests and verify missing composables**

Run: `npm test -- src/composables/useDemManager.test.ts src/composables/useModelWorkspace.test.ts`

Expected: FAIL because both composables are missing.

- [ ] **Step 3: Implement DEM and draft state**

`useDemManager` exposes `dems`, `selectedDem`, `loading`, `uploading`, `load`, `select`, `upload`, and `remove`. `useModelWorkspace` creates all defaults once, returns the current draft via a writable computed, and deep-clones restored task requests before assigning them. DEM selection updates `dem_id` in every draft so switching models cannot submit against an old DEM.

- [ ] **Step 4: Implement and test `DemSelector.vue`**

The component accepts `dems`, `modelValue`, `loading`, and `uploading`; emits `update:modelValue`, `upload`, `delete`, and `refresh`. Use a select control, upload command, refresh icon, and delete confirmation. Display filename, CRS, resolution, and active task count without nesting cards.

```ts
const wrapper = mount(DemSelector, {
  props: { dems: [demA], modelValue: null, loading: false, uploading: false }
});
await wrapper.get('[data-dem-id="dem-a"]').trigger("click");
expect(wrapper.emitted("update:modelValue")?.[0]).toEqual(["dem-a"]);
expect(wrapper.text()).toContain(demA.crs);
```

Run: `npm test -- src/composables/useDemManager.test.ts src/composables/useModelWorkspace.test.ts src/components/dem/DemSelector.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit DEM and draft state**

```powershell
git add frontend/src/composables/useDemManager* frontend/src/composables/useModelWorkspace* frontend/src/components/dem
git commit -m "feat: manage DEMs and per-model drafts"
```

---

### Task 6: Map Workspace and Spatial Input Engine

**Files:**
- Create: `frontend/src/map/spatialInput.ts`
- Create: `frontend/src/map/spatialInput.test.ts`
- Create: `frontend/src/map/modelLayers.ts`
- Create: `frontend/src/components/map/CoordinateEditor.vue`
- Create: `frontend/src/components/map/RouteEditor.vue`
- Create: `frontend/src/components/map/ThreatEditor.vue`
- Create: `frontend/src/components/map/MapWorkspace.vue`
- Create: `frontend/src/composables/useMapWorkspace.ts`
- Modify: `frontend/src/map/mapLayers.ts`

**Interfaces:**
- Consumes: `SpatialInputKind`, `OutputLayerDefinition`, DEM tile helpers.
- Produces: `SpatialDraft`, `spatialDraftToGeoJson()`, map commands `pickPoint`, `appendWaypoint`, `moveWaypoint`, `removeWaypoint`, `undo`, `clear`, `focusBounds`.

- [ ] **Step 1: Write failing pure spatial reducer tests**

```ts
describe("spatial input", () => {
  it("supports ordered route edits and undo", () => {
    let state = createSpatialDraft("point-or-route");
    state = reduceSpatialDraft(state, { type: "append", coordinate: [79.8, 31.4] });
    state = reduceSpatialDraft(state, { type: "append", coordinate: [79.9, 31.5] });
    expect(spatialDraftToGeoJson(state).features[0].geometry.type).toBe("LineString");
    state = reduceSpatialDraft(state, { type: "undo" });
    expect(state.points).toHaveLength(1);
  });
});
```

- [ ] **Step 2: Run the test and verify the missing reducer failure**

Run: `npm test -- src/map/spatialInput.test.ts`

Expected: FAIL because `spatialInput.ts` is missing.

- [ ] **Step 3: Implement pure spatial state and generic layer lifecycle**

Use discriminated actions `set-point`, `append`, `move`, `remove`, `set-start`, `set-end`, `add-threat`, `update-threat`, `remove-threat`, `undo`, and `clear`. Reject latitude outside `[-90, 90]` and longitude outside `[-180, 180]`. `modelLayers.ts` must prefix source/layer IDs with `${modelId}-${taskId}-${kind}` and expose `upsertModelGeoJsonLayer`, `setModelLayerVisibility`, `setModelLayerOpacity`, `focusModelLayer`, and `removeTaskLayers`.

- [ ] **Step 4: Implement map and editor components**

`MapWorkspace.vue` creates exactly one MapLibre map, resizes it after drawer transitions, emits normalized coordinate edits, and destroys the map on unmount. `CoordinateEditor`, `RouteEditor`, and `ThreatEditor` remain controlled components; they do not own task requests. The toolbar always offers finish, undo, and clear icons while editing.

- [ ] **Step 5: Run reducer tests and build**

Run: `npm test -- src/map/spatialInput.test.ts`

Expected: PASS.

Run: `npm run build`

Expected: exit 0.

- [ ] **Step 6: Commit map input infrastructure**

```powershell
git add frontend/src/map frontend/src/components/map frontend/src/composables/useMapWorkspace.ts
git commit -m "feat: add shared spatial input workspace"
```

---

### Task 7: Radar, Watchpost, and Artillery Parameter Forms

**Files:**
- Create: `frontend/src/components/forms/RadarForm.vue`
- Create: `frontend/src/components/forms/WatchpostForm.vue`
- Create: `frontend/src/components/forms/ArtilleryForm.vue`
- Create: `frontend/src/components/forms/pointForms.test.ts`
- Create: `frontend/src/components/forms/ModelParameterPanel.vue`

**Interfaces:**
- Consumes: typed drafts, `ValidationIssue[]`, coordinate editor.
- Produces: controlled `update:modelValue`, `submit`, and `activate-map-tool` events.

- [ ] **Step 1: Write failing form validation tests**

Mount each form with its default request. Assert radar sector controls appear only when `scan_mode === "sector"`; watchpost reports `max_range_m <= 0`; artillery reports `min_range_m >= max_range_m`; clicking submit emits only when validation returns no issues.

```ts
await wrapper.get('[data-field="min-range"]').setValue(20000);
await wrapper.get('[data-field="max-range"]').setValue(15000);
await wrapper.get('[data-action="submit"]').trigger("click");
expect(wrapper.text()).toContain("最小射程必须小于最大射程");
expect(wrapper.emitted("submit")).toBeUndefined();
```

- [ ] **Step 2: Run the test and verify missing components**

Run: `npm test -- src/components/forms/pointForms.test.ts`

Expected: FAIL because the forms do not exist.

- [ ] **Step 3: Implement the three controlled forms**

Bind every backend request field. Group radar as location/target, coverage, advanced volume; watchpost as observer/target, coverage, analysis; artillery as battery/target, weapon, munition, analysis. Use number inputs with visible units, switches for booleans, and segmented controls for scan or altitude modes. `ModelParameterPanel.vue` selects the explicit form by model ID and owns the fixed submit footer.

- [ ] **Step 4: Run point-form tests**

Run: `npm test -- src/components/forms/pointForms.test.ts`

Expected: PASS for conditional controls, validation, and submit events.

- [ ] **Step 5: Commit point-model forms**

```powershell
git add frontend/src/components/forms
git commit -m "feat: add radar watchpost and artillery forms"
```

---

### Task 8: UAV, Recon Vehicle, Mobility, and Air Corridor Forms

**Files:**
- Create: `frontend/src/components/forms/UavForm.vue`
- Create: `frontend/src/components/forms/ReconVehicleForm.vue`
- Create: `frontend/src/components/forms/MobilityForm.vue`
- Create: `frontend/src/components/forms/AirCorridorForm.vue`
- Create: `frontend/src/components/forms/routeForms.test.ts`
- Modify: `frontend/src/components/forms/ModelParameterPanel.vue`

**Interfaces:**
- Consumes: route/start-end/threat editors and model validators.
- Produces: exact backend payloads with ordered waypoints and stable threat IDs.

- [ ] **Step 1: Write failing complex-form tests**

Test these exact constraints: UAV and recon routes are either absent or contain at least two waypoints; mobility enables at least one of wheeled/tracked; air-corridor start/end exist, altitude layers are unique and ascending, threat minimums are below maximums, and kill radius does not exceed warning radius.

```ts
const wrapper = mount(MobilityForm, { props: { modelValue: defaultMobilityRequest() } });
await wrapper.get('[data-field="wheeled-enabled"]').setValue(false);
await wrapper.get('[data-field="tracked-enabled"]').setValue(false);
expect(wrapper.text()).toContain("至少启用一种车辆");
```

- [ ] **Step 2: Run the test and verify missing forms**

Run: `npm test -- src/components/forms/routeForms.test.ts`

Expected: FAIL because the four forms do not exist.

- [ ] **Step 3: Implement route and multi-point forms**

UAV groups platform/route, sensor, and analysis; recon vehicle groups vehicle/route, sensor/target, and analysis; mobility groups start/end, wheeled, tracked, road network, and analysis; air corridor groups start/end, aircraft, altitude layers, threats, and planning weights. Map edits update the same request object represented by the form. Generate new threat IDs with `crypto.randomUUID()` and preserve existing IDs during edits and request restoration.

- [ ] **Step 4: Run all form tests**

Run: `npm test -- src/components/forms/pointForms.test.ts src/components/forms/routeForms.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit route-model forms**

```powershell
git add frontend/src/components/forms frontend/src/components/map/ThreatEditor.vue
git commit -m "feat: add route and corridor model forms"
```

---

### Task 9: Generic Results, Metrics, Files, and Layer Controls

**Files:**
- Create: `frontend/src/components/tasks/TaskStatusView.vue`
- Create: `frontend/src/components/tasks/MetricGrid.vue`
- Create: `frontend/src/components/tasks/LayerList.vue`
- Create: `frontend/src/components/tasks/OutputFileList.vue`
- Create: `frontend/src/components/tasks/TaskResultPanel.vue`
- Create: `frontend/src/components/tasks/TaskResultPanel.test.ts`
- Create: `frontend/src/components/tasks/TaskHistoryDrawer.vue`
- Modify: `frontend/src/composables/useMapWorkspace.ts`

**Interfaces:**
- Consumes: model metric/layer definitions, task manager, generic map-layer commands.
- Produces: `loadTaskOutputs(modelId, task)`, layer visibility/opacity/focus events, restore and delete commands.

- [ ] **Step 1: Write the failing result panel test**

```ts
it("isolates one failed GeoJSON layer without failing the task", async () => {
  const wrapper = mount(TaskResultPanel, {
    props: { modelId: "uav", task: finishedUavTask, layerStates: failedVisibleLayerState }
  });
  expect(wrapper.text()).toContain("任务已完成");
  await wrapper.get('[data-tab="layers"]').trigger("click");
  expect(wrapper.text()).toContain("可见区加载失败");
  expect(wrapper.text()).toContain("传感器足迹");
});
```

- [ ] **Step 2: Run the test and verify missing components**

Run: `npm test -- src/components/tasks/TaskResultPanel.test.ts`

Expected: FAIL because `TaskResultPanel.vue` is missing.

- [ ] **Step 3: Implement tabbed results and metric formatting**

Use fixed tabs `task`, `metrics`, `layers`, and `files`. Format area as km² above 1,000,000 m², distance as km above 1,000 m, duration as `h m s`, and percent from ratio values. A layer row includes color swatch, text state, visibility switch, opacity slider, and focus icon. Output links use `download_url` when present and fall back to `url`.

- [ ] **Step 4: Implement output loading and history**

When a task finishes, fetch metrics and outputs in parallel. For each registered GeoJSON kind, fetch and parse the file independently, update only that layer's state, and retain the finished task status when parsing fails. History rows show model, status, time, progress, restore, focus, and delete. Deletion uses explicit confirmation text stating that backend records and output files are removed.

- [ ] **Step 5: Run result tests and build**

Run: `npm test -- src/components/tasks/TaskResultPanel.test.ts`

Expected: PASS.

Run: `npm run build`

Expected: exit 0.

- [ ] **Step 6: Commit results and history**

```powershell
git add frontend/src/components/tasks frontend/src/composables/useMapWorkspace.ts
git commit -m "feat: add shared task results and layers"
```

---

### Task 10: Integrate the Seven-Model Workspace

**Files:**
- Rewrite: `frontend/src/App.vue`
- Modify: `frontend/src/main.ts`
- Create: `frontend/src/App.test.ts`
- Modify: `frontend/src/styles/app.css`

**Interfaces:**
- Consumes: shell, DEM manager, workspace drafts, task manager, map workspace, forms, results, and history.
- Produces: one end-to-end application flow for every `ModelId`.

- [ ] **Step 1: Write a failing application wiring test**

Mock MapLibre and API modules. Assert selecting each navigation item changes the form heading, submitting uses that definition's base path, switching models does not remove an active task, and restoring a task changes the draft without submitting.

```ts
await wrapper.get('[data-model-id="airCorridor"]').trigger("click");
expect(wrapper.get("[data-parameter-heading]").text()).toContain("空中航路");
await wrapper.get('[data-action="submit"]').trigger("click");
expect(fetchMock).toHaveBeenCalledWith("/api/air-corridor/planning", expect.objectContaining({ method: "POST" }));
```

- [ ] **Step 2: Run the test against the radar-only app**

Run: `npm test -- src/App.test.ts`

Expected: FAIL because the current app has no model navigation or generic submit path.

- [ ] **Step 3: Replace radar-only orchestration with the shared workspace**

`App.vue` creates the four composables once, connects their commands to shell events, loads DEMs and all model histories on mount, and calls every composable's cleanup on unmount. Submission validates the current model, focuses the first invalid path when needed, then calls `taskManager.submit(currentModel, deepClone(currentDraft))`. Model switching updates visible layers and preserves polling.

- [ ] **Step 4: Run the application test and full unit suite**

Run: `npm test`

Expected: all tests PASS.

Run: `npm run build`

Expected: exit 0 and no TypeScript errors.

- [ ] **Step 5: Commit the integrated workspace**

```powershell
git add frontend/src/App.vue frontend/src/App.test.ts frontend/src/main.ts frontend/src/styles/app.css
git commit -m "feat: integrate seven-model GIS workspace"
```

---

### Task 11: Migrate Radar Profile, Fusion, and 3D Layers

**Files:**
- Create: `frontend/src/models/radar/layerAdapter.ts`
- Create: `frontend/src/models/radar/useRadarAnalysis.ts`
- Create: `frontend/src/models/radar/useRadarAnalysis.test.ts`
- Modify: `frontend/src/components/ProfilePanel.vue`
- Modify: `frontend/src/components/FusionPanel.vue`
- Modify: `frontend/src/map/radarVolumeLayer.ts`
- Modify: `frontend/src/map/voxelLayer.ts`
- Modify: `frontend/src/map/clippedVolumeLayer.ts`
- Modify: `frontend/src/composables/useMapWorkspace.ts`
- Delete after parity: `frontend/src/components/ControlPanel.vue`
- Delete after parity: `frontend/src/components/LayerControlPanel.vue`
- Delete after parity: `frontend/src/components/ResultPanel.vue`
- Delete after parity: `frontend/src/api/client.ts`

**Interfaces:**
- Consumes: radar tasks, typed radar request, current map, radar API.
- Produces: profile point tool, multi-task fusion, height-layer selector, radar volume/voxel/clipped-volume layer adapters.

- [ ] **Step 1: Write failing radar parity tests**

Test that profile mode calls the profile endpoint with selected coordinates; fusion rejects fewer than two finished radar tasks; restoring a radar request does not submit; selecting another model removes radar-only 3D layers from view without deleting cached data.

- [ ] **Step 2: Run tests and verify missing analysis composable**

Run: `npm test -- src/models/radar/useRadarAnalysis.test.ts`

Expected: FAIL because `useRadarAnalysis.ts` is missing.

- [ ] **Step 3: Move radar-only orchestration behind the adapter**

`layerAdapter.ts` maps radar outputs and request state to existing render functions. It owns loading tokens for height manifests, voxel binaries, and clipped-volume binaries; stale responses must not update the active task. `useRadarAnalysis` owns profile/fusion request tokens, clear commands, and eligibility checks. Keep the existing render math unchanged.

- [ ] **Step 4: Remove temporary compatibility modules after parity**

Update all imports to `api/http.ts`, `api/dem.ts`, `api/tasks.ts`, or `api/radar.ts`. Remove the old radar-only panels and `api/client.ts` only after searches show no remaining imports:

Run: `Get-ChildItem frontend\src -Recurse -File | Select-String -Pattern 'api/client|ControlPanel|LayerControlPanel|components/ResultPanel'`

Expected: no matches before deletion.

- [ ] **Step 5: Run radar tests, full suite, and build**

Run: `npm test -- src/models/radar/useRadarAnalysis.test.ts`

Expected: PASS.

Run: `npm test`

Expected: all tests PASS.

Run: `npm run build`

Expected: exit 0.

- [ ] **Step 6: Commit radar migration**

```powershell
git add frontend/src
git commit -m "refactor: migrate radar analysis into workspace"
```

---

### Task 12: Responsive and Browser Acceptance

**Files:**
- Modify: `frontend/src/styles/app.css`
- Modify: `frontend/src/components/layout/WorkspaceShell.vue`
- Modify: `frontend/src/components/layout/AppHeader.vue`
- Modify: `frontend/src/components/layout/ModelNavigation.vue`
- Modify: `frontend/src/components/map/MapWorkspace.vue`
- Modify: `frontend/src/components/tasks/TaskResultPanel.vue`
- Create: `frontend/src/components/layout/WorkspaceShell.test.ts`
- Modify: `README.md`

**Interfaces:**
- Consumes: completed application.
- Produces: verified desktop/narrow layouts and local non-Docker startup documentation.

- [ ] **Step 1: Add a failing narrow-screen interaction test**

```ts
it("keeps parameter and result drawers mutually exclusive", async () => {
  const wrapper = mount(WorkspaceShell, { props: { viewport: "narrow" } });
  await wrapper.get('[data-action="toggle-parameters"]').trigger("click");
  expect(wrapper.get('[data-region="parameters"]').attributes("data-open")).toBe("true");
  await wrapper.get('[data-action="toggle-results"]').trigger("click");
  expect(wrapper.get('[data-region="parameters"]').attributes("data-open")).toBe("false");
  expect(wrapper.get('[data-region="results"]').attributes("data-open")).toBe("true");
});
```

Run: `npm test -- src/components/layout/WorkspaceShell.test.ts`

Expected: FAIL until `WorkspaceShell` closes the opposite drawer.

- [ ] **Step 2: Implement deterministic responsive behavior**

Add a `viewport` prop with type `"desktop" | "compact" | "narrow"` whose default is derived from `window.matchMedia`; the explicit prop keeps tests deterministic. In narrow mode, opening parameters sets results closed and opening results sets parameters closed. Add `aria-expanded` and `aria-controls` to both header commands. Resize MapLibre after either drawer transition finishes.

Run: `npm test -- src/components/layout/WorkspaceShell.test.ts`

Expected: PASS.

- [ ] **Step 3: Start local services without Docker**

Backend:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
cd frontend
npm run dev -- --host 127.0.0.1
```

Expected: backend health endpoint returns 200 and frontend loads at `http://127.0.0.1:5173`.

- [ ] **Step 4: Capture desktop and narrow-screen evidence**

Use Playwright or the available browser automation to inspect 1440x900, 1024x768, and 390x844. For each viewport verify: nonblank map, no text overlap, independent panel scrolling, visible submit action, drawers do not cover each other, and model navigation remains reachable. Check browser console for uncaught errors.

- [ ] **Step 5: Exercise all seven workflows**

For every model: select DEM, edit required spatial input, submit a real request, observe pending/running/terminal state, open metrics/files/layers, toggle and focus a layer, restore the request, and delete a disposable task. For GDAL-dependent failures, verify the backend failure message is visible and the UI remains usable. Exercise radar profile, fusion, height layer, volume, voxel, and clipped-volume controls with existing completed tasks when available.

- [ ] **Step 6: Resolve acceptance failures before continuing**

Do not continue while any browser acceptance assertion fails. For a functional failure, add the focused failing test to the owning component test file, run it to confirm failure, apply the correction in the owning component listed in this task, and rerun that test. For a visual failure, record the viewport and selector, adjust the owning component plus `app.css`, and recapture the same viewport. The acceptance record must show all three target viewports after the correction.

- [ ] **Step 7: Update local startup documentation**

Document Python venv/Uvicorn and Vite commands, `VITE_PROXY_TARGET`, URLs, and the `gdal_viewshed` prerequisite in `README.md`. State explicitly that Docker is optional and is not used by the local workflow.

- [ ] **Step 8: Run final verification**

Run:

```powershell
cd frontend
npm test
npm run build
```

Expected: all Vitest tests PASS; `vue-tsc -b` and Vite exit 0.

Run from repository root:

```powershell
git status --short
```

Expected: only intended source, test, lockfile, and README changes are present; local log files remain untracked and unstaged.

- [ ] **Step 9: Commit acceptance fixes and documentation**

```powershell
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/src README.md
git commit -m "feat: complete multi-model GIS workbench"
```

---

## Final Acceptance Checklist

- [ ] Seven model entries render and submit to their exact backend paths.
- [ ] Every model has typed defaults, validation, metric definitions, and visual output layers.
- [ ] Concurrent tasks continue polling across model switches and stop polling on terminal states.
- [ ] DEM selection stays synchronized across model drafts.
- [ ] Point, route, start/end, and threat editing work from fields and map tools.
- [ ] Task, metric, layer, file, history, restore, focus, and delete flows work consistently.
- [ ] Radar 2D, height, profile, fusion, volume, voxel, and clipped-volume features remain available.
- [ ] Network, parsing, missing-output, backend, and missing-GDAL failures remain isolated and visible.
- [ ] Desktop and narrow layouts have no overlap, overflow, blank map, or unreachable controls.
- [ ] `npm test` and `npm run build` pass from `frontend`.
- [ ] Local startup works through Uvicorn and Vite without Docker.
