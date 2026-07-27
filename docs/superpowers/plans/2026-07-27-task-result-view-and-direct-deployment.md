# Task Result View and Direct Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore a current-style task result inspector and make direct-port and Nginx-subpath API routing explicit and reliable.

**Architecture:** `GisWorkbenchShell` regains a named inspector region, while `WorkbenchInspector` renders live task metrics and output descriptors supplied by `useMapWorkspace`. Presentation state controls the inspector and Layers dock without adding API calls. Compose defaults to direct backend origin; subpath deployment remains an explicit environment override.

**Tech Stack:** Vue 3, TypeScript, Vitest, CSS Grid, Docker Compose, pytest.

## Global Constraints

- Match the current white, compact workbench visual language with 8px-or-less control radii.
- Use only canonical backend `download_path` values for result assets.
- Preserve existing GeoJSON and GLB loading behavior.
- Support Nginx `/PyGeoModel`, direct ports, and same-origin root proxy deployments.

---

### Task 1: Result Inspector Presentation

**Files:**
- Modify: `frontend/src/components/workbench/WorkbenchInspector.vue`
- Test: `frontend/src/components/workbench/WorkbenchInspector.test.ts`

**Interfaces:**
- Consumes: selected `{ modelId, task }`, live `metrics`, and live `outputFiles` props.
- Produces: compact result view and `show-parameters` event.

- [ ] **Step 1: Write failing component tests**

Add assertions for declared radar metric label/value, available download link, unavailable state, status styling, and the back event. Mount with:

```ts
props: {
  mode: "result",
  context: finishedContext(),
  metrics: { visible_area_m2: 2_500_000 },
  outputFiles: [outputFile()]
}
```

- [ ] **Step 2: Run the focused test and confirm failure**

Run: `cd frontend && npm test -- src/components/workbench/WorkbenchInspector.test.ts`

Expected: FAIL because live props and new result structure are absent.

- [ ] **Step 3: Implement the current-style inspector**

Add optional props and derive declared model metrics:

```ts
const props = withDefaults(defineProps<{
  mode: "parameters" | "result";
  context?: Context | null;
  metrics?: Record<string, unknown> | null;
  outputFiles?: readonly OutputFile[];
}>(), { context: null, metrics: null, outputFiles: () => [] });
```

Render compact sections for status, metrics, files, and unavailable results. Resolve links with `resolveApiUrl(file.download_path!)`. Replace the legacy heading/pills with the current workbench colors, separators, 12-14px type, and stable 32px icon button.

- [ ] **Step 4: Run the focused test**

Run: `cd frontend && npm test -- src/components/workbench/WorkbenchInspector.test.ts`

Expected: PASS.

### Task 2: Shell Inspector Region and Task Selection

**Files:**
- Modify: `frontend/src/components/workbench/GisWorkbenchShell.vue`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/workbench/useWorkbenchPresentation.ts`
- Test: `frontend/src/components/workbench/GisWorkbenchShell.test.ts`
- Test: `frontend/src/workbench/useWorkbenchPresentation.test.ts`

**Interfaces:**
- Consumes: `presentation.inspectorMode`, `selectedTaskContext`, `mapWorkspace.taskMetrics`, and `mapWorkspace.outputFiles`.
- Produces: `#inspector` shell slot and automatic `dockTab === "layers"` after task selection.

- [ ] **Step 1: Write failing shell and presentation tests**

Assert three-column desktop areas and inspector rendering:

```ts
expect(gridTemplate).toContain('"top top top"');
expect(wrapper.get("[data-workbench-region='inspector']").text()).toBe("inspector");
```

Assert `presentation.selectTask()` makes `inspectorMode` result and `dockTab` layers.

- [ ] **Step 2: Run focused tests and confirm failure**

Run: `cd frontend && npm test -- src/components/workbench/GisWorkbenchShell.test.ts src/workbench/useWorkbenchPresentation.test.ts`

Expected: FAIL because the shell has no inspector region and task selection does not select Layers.

- [ ] **Step 3: Restore the shell region and wire the inspector**

Use grid areas:

```css
grid-template-areas:
  "top top top"
  "dock map inspector"
  "tasks tasks tasks"
  "status status status";
grid-template-columns: 292px minmax(360px, 1fr) minmax(260px, 320px);
```

Add a narrow-screen inspector overlay/stack rule. Mount `WorkbenchInspector` in `App.vue` and pass live metrics/files. Update `selectTask()` to set both modes:

```ts
function selectTask() {
  inspectorMode.value = "result";
  dockTab.value = "layers";
}
```

- [ ] **Step 4: Run focused and App tests**

Run: `cd frontend && npm test -- src/components/workbench/GisWorkbenchShell.test.ts src/workbench/useWorkbenchPresentation.test.ts src/App.test.ts`

Expected: PASS.

### Task 3: Direct-Port Deployment Defaults

**Files:**
- Modify: `docker-compose.yml`
- Modify: `docs/deployment.md`
- Modify: `backend/tests/test_deployment_config.py`
- Modify: `scripts/verify_deployment.py`

**Interfaces:**
- Consumes: `PYGEOMODEL_API_BASE_URL` environment override.
- Produces: direct default `http://127.0.0.1:8000`, explicit `/PyGeoModel` subpath mode, and content-type validation.

- [ ] **Step 1: Write failing deployment tests**

Expect the Compose default to be direct:

```py
assert "${PYGEOMODEL_API_BASE_URL-http://127.0.0.1:8000}" in compose_text
```

Add a verifier test where an API request returns `text/html` and assert it raises `RuntimeError` rather than accepting the SPA fallback.

- [ ] **Step 2: Run focused tests and confirm failure**

Run: `docker compose exec -T backend pytest tests/test_deployment_config.py -q`

Expected: FAIL on the old `/PyGeoModel` default and missing JSON content validation.

- [ ] **Step 3: Implement configuration and verification changes**

Set:

```yaml
PYGEOMODEL_API_BASE_URL: ${PYGEOMODEL_API_BASE_URL-http://127.0.0.1:8000}
```

Document the explicit Nginx override and direct-port access. In the verifier, reject non-JSON health/task/output responses before parsing.

- [ ] **Step 4: Run deployment tests**

Run: `docker compose exec -T backend pytest tests/test_deployment_config.py -q`

Expected: PASS.

### Task 4: Full Verification

**Files:**
- Verify only.

**Interfaces:**
- Consumes: Tasks 1-3.
- Produces: verified frontend build/tests and deployment behavior.

- [ ] **Step 1: Run the frontend suite and build**

Run: `cd frontend && npm test && npm run build`

Expected: all tests pass and Vite build succeeds.

- [ ] **Step 2: Run backend tests**

Run: `docker compose exec -T backend pytest -q`

Expected: all tests pass.

- [ ] **Step 3: Recreate containers and verify both endpoints**

Run the Compose recreation with the direct default, then verify `runtime-config.js`, `/api/health`, the known radar task descriptor, and a GeoJSON download all return their expected content types. Verify the public `/PyGeoModel/` Nginx endpoint separately with the explicit override.
