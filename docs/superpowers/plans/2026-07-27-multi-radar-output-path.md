# Multi-Radar Output Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent double resolution of multi-radar aggregate GeoJSON download paths.

**Architecture:** The multi-radar API module selects canonical output descriptor paths. `App.vue` passes those `/api/...` paths to `requestGeoJson`, which remains the only runtime API base resolver.

**Tech Stack:** Vue 3, TypeScript, Vitest.

## Global Constraints

- Keep `resolveApiUrl` strict: accepted paths begin with `/api/`.
- Use only live output descriptors and canonical `download_path` values.
- Do not change GLB result loading.

---

### Task 1: Canonical Multi-Radar Output Path

**Files:**
- Modify: `frontend/src/api/multiRadar.ts`
- Modify: `frontend/src/api/multiRadar.test.ts`
- Modify: `frontend/src/App.vue`

**Interfaces:**
- Consumes: `readonly OutputFile[]` and an artifact kind.
- Produces: `findMultiRadarOutputPath(files, kind): string | null`.

- [ ] **Step 1: Write the failing regression test**

```ts
expect(findMultiRadarOutputPath([{
  kind: "visible_union_geojson",
  filename: "visible_union.geojson",
  label: "Visible Union GeoJSON",
  media_type: "application/geo+json",
  required: true,
  exists: true,
  download_path: "/api/radar/multi-coverage/multi_task_a/outputs/visible_union_geojson"
}], "visible_union_geojson")).toBe(
  "/api/radar/multi-coverage/multi_task_a/outputs/visible_union_geojson"
);
```

- [ ] **Step 2: Run the focused test and verify red**

Run: `cd frontend && npm test -- src/api/multiRadar.test.ts`

Expected: FAIL because `findMultiRadarOutputPath` is not exported.

- [ ] **Step 3: Implement the selector and use it in App**

```ts
export function findMultiRadarOutputPath(files: readonly OutputFile[], kind: string): string | null {
  const file = files.find((candidate) => candidate.kind === kind && candidate.exists && candidate.download_path);
  return file?.download_path ?? null;
}
```

Import this helper in `App.vue`, replace `outputUrl(outputFiles, kind)` with
`findMultiRadarOutputPath(outputFiles, kind)`, and remove the local `outputUrl`
function and unused `resolveApiUrl` import.

- [ ] **Step 4: Run focused tests and build**

Run: `cd frontend && npm test -- src/api/multiRadar.test.ts src/App.test.ts src/api/http.test.ts && npm run build`

Expected: all tests pass and the build succeeds.

- [ ] **Step 5: Run full frontend tests and deploy**

Run: `cd frontend && npm test`

Expected: all tests pass. Rebuild only the frontend image with the explicit
production `PYGEOMODEL_API_BASE_URL=/PyGeoModel`, recreate the frontend
container, and verify the known multi-radar GeoJSON endpoints return
`application/geo+json` through the public prefix.
