# Multi-Radar Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Add batch radar coverage tasks that aggregate independent stations and render aggregate results with on-demand station detail.

**Architecture:** A separate multi-radar task store preserves the legacy single-radar API. The worker prepares one DEM grid, evaluates stations through a bounded pool, accumulates coverage counts, and writes aggregate outputs plus station summaries. The frontend renders aggregate GeoJSON and inexpensive station markers; detailed GLBs are only activated for selected stations.

**Tech Stack:** FastAPI, Pydantic, NumPy, Rasterio, Shapely, Vue 3, TypeScript, MapLibre GL, Three.js, pytest, Vitest.

## Global Constraints

- Accept 2 through 256 radars with unique \`radar_id\` values.
- Every station uses the batch \`dem_id\`; station coverage parameters are independent.
- A location is detected when at least one successful station detects it.
- Preserve all existing \`/api/radar/coverage\` behavior and output URLs.
- Limit detailed 3D map selections to five stations.

---

### Task 1: Batch Schemas and JSON Task Store

**Files:**
- Modify: \`backend/app/schemas/radar.py\`
- Create: \`backend/app/services/multi_radar_task_store.py\`
- Test: \`backend/tests/test_multi_radar_task_store.py\`

**Interfaces:** \`MultiRadarRequest\`, \`MultiRadarTaskStatus\`, \`create_multi_task(payload)\`, \`get_multi_task(task_id)\`, and \`list_multi_tasks()\`.

- [ ] Write a failing schema test for duplicate IDs and a store round-trip test:
\`\`\`python
def test_multi_radar_request_requires_unique_station_ids() -> None:
    with pytest.raises(ValidationError, match="radar_id"):
        MultiRadarRequest.model_validate({"dem_id": "dem", "radars": [station("a"), station("a")]})
\`\`\`
- [ ] Run: \`python -m pytest tests/test_multi_radar_task_store.py -q\`; expected failure: missing multi-radar types.
- [ ] Add \`MultiRadarStation\` with the current per-station fields except \`dem_id\`; add \`MultiRadarRequest(dem_id, radars)\` with \`Field(min_length=2, max_length=256)\` and duplicate-ID validation.
- [ ] Implement a store isolated from \`task_store.py\`, using \`multi_task_\` IDs and persisted request payloads.
- [ ] Run the focused test; expected: pass.
- [ ] Commit: \`git commit -m "feat: add multi-radar task schemas"\`.

### Task 2: Aggregate Mask Engine

**Files:**
- Create: \`backend/app/services/multi_radar_coverage.py\`
- Test: \`backend/tests/test_multi_radar_coverage.py\`

**Interfaces:** \`StationMask(radar_id, visible_mask, range_mask)\` and \`accumulate_station_masks(results) -> MultiRadarAggregate\`.

- [ ] Write the failing aggregation test:
\`\`\`python
aggregate = accumulate_station_masks([
    StationMask("north", numpy.array([[True, False], [True, False]]), numpy.ones((2, 2), bool)),
    StationMask("south", numpy.array([[True, True], [False, False]]), numpy.ones((2, 2), bool)),
])
assert aggregate.coverage_count.tolist() == [[2, 1], [1, 0]]
assert aggregate.visible_union.tolist() == [[True, True], [True, False]]
assert aggregate.overlap.tolist() == [[True, False], [False, False]]
\`\`\`
- [ ] Run: \`python -m pytest tests/test_multi_radar_coverage.py -q\`; expected failure: missing module.
- [ ] Implement a \`uint16\` coverage count, union \`>= 1\`, overlap \`>= 2\`, and blind mask as theoretical union minus visible union.
- [ ] Run the focused test; expected: pass.
- [ ] Commit: \`git commit -m "feat: aggregate multi-radar coverage masks"\`.

### Task 3: Worker and Aggregate Outputs

**Files:**
- Create: \`backend/app/workers/multi_radar_coverage_task.py\`
- Modify: \`backend/app/services/multi_radar_task_store.py\`
- Test: \`backend/tests/test_multi_radar_coverage_task.py\`

**Interfaces:** \`run_multi_radar_coverage_task(task_id, payload)\`; station outputs include state, metrics, diagnostics, and detail metadata.

- [ ] Write a failing partial-completion test by injecting an evaluator that raises for \`radar_id == "bad"\`; assert a partial task and a valid union from the successful station.
- [ ] Run: \`python -m pytest tests/test_multi_radar_coverage_task.py -q\`; expected failure: missing worker.
- [ ] Prepare one projected DEM from the batch centroid, cap executor workers at \`min(os.cpu_count() or 1, 8)\`, accumulate successful station masks, and record failed station reasons without aborting siblings.
- [ ] Write union, overlap, blind, coverage-count, station-summary, and station-GeoJSON outputs; set task state to \`partial\` when both success and failure occur.
- [ ] Run the focused test; expected: pass.
- [ ] Commit: \`git commit -m "feat: run multi-radar coverage tasks"\`.

### Task 4: Lifecycle API and Union Target Evaluation

**Files:**
- Modify: \`backend/app/api/radar.py\`
- Create: \`backend/app/services/multi_radar_target_evaluation.py\`
- Test: \`backend/tests/test_multi_radar_api.py\`

**Interfaces:** \`POST /api/radar/multi-coverage\`, lifecycle reads, \`GET /{task_id}/radars\`, \`GET /{task_id}/radars/{radar_id}\`, and \`POST /{task_id}/evaluate-target\`.

- [ ] Write failing API tests asserting a 202 batch response and an evaluation response with \`detected is True\` when one contributor detects the target.
- [ ] Run: \`python -m pytest tests/test_multi_radar_api.py -q\`; expected failure: route not found.
- [ ] Add routes that validate every station footprint before task creation; union evaluation must return every contributor and \`detected = any(contributor.detected)\`.
- [ ] Run the focused test; expected: pass.
- [ ] Commit: \`git commit -m "feat: expose multi-radar coverage API"\`.

### Task 5: Frontend API Contract

**Files:**
- Create: \`frontend/src/models/multiRadar/types.ts\`
- Create: \`frontend/src/api/multiRadar.ts\`
- Test: \`frontend/src/api/multiRadar.test.ts\`

**Interfaces:** \`MultiRadarRequest\`, \`MultiRadarTask\`, \`MultiRadarStationSummary\`, \`createMultiRadarTask\`, and \`getMultiRadarStations\`.

- [ ] Write a failing request test:
\`\`\`ts
await createMultiRadarTask(payload);
expect(requestJson).toHaveBeenCalledWith(
  "/api/radar/multi-coverage",
  expect.objectContaining({ method: "POST" })
);
\`\`\`
- [ ] Run: \`npm test -- src/api/multiRadar.test.ts\`; expected failure: module not found.
- [ ] Add typed request and response normalization; model task states include \`partial\`.
- [ ] Run the focused test; expected: pass.
- [ ] Commit: \`git commit -m "feat: add multi-radar frontend client"\`.

### Task 6: Map Adapter and Detail Budget

**Files:**
- Create: \`frontend/src/map/multiRadarLayerAdapter.ts\`
- Create: \`frontend/src/map/multiRadarLayerAdapter.test.ts\`
- Modify: \`frontend/src/composables/useMapWorkspace.ts\`
- Modify: \`frontend/src/App.vue\`

**Interfaces:** \`createMultiRadarLayerAdapter({ maxDetailedSelections: 5 })\`, \`showAggregate\`, \`selectStationDetail\`, \`removeStationDetail\`, and \`clear\`.

- [ ] Write the failing eviction test:
\`\`\`ts
["a", "b", "c", "d", "e", "f"].forEach((id) => adapter.selectStationDetail(id));
expect(deps.removeDetail).toHaveBeenCalledWith("a");
\`\`\`
- [ ] Run: \`npm test -- src/map/multiRadarLayerAdapter.test.ts\`; expected failure: module not found.
- [ ] Render union, overlap, blind, and count layers from aggregate outputs. Render stations through one clustered GeoJSON source. Delegate selected detail GLBs to the existing scene-GLB adapter and evict the oldest selection after five.
- [ ] Run the focused test; expected: pass.
- [ ] Commit: \`git commit -m "feat: render multi-radar aggregate layers"\`.

### Task 7: Station Controls and Full Verification

**Files:**
- Create: \`frontend/src/components/tasks/MultiRadarStationList.vue\`
- Create: \`frontend/src/components/tasks/MultiRadarStationList.test.ts\`
- Modify: \`frontend/src/App.vue\`

- [ ] Write a failing filter test that enters \`ridge\` and expects North Ridge but not South Basin.
- [ ] Run: \`npm test -- src/components/tasks/MultiRadarStationList.test.ts\`; expected failure: component not found.
- [ ] Implement search, status filtering, map focus, and detail toggles; the component emits events and never owns GLB resources.
- [ ] Run backend verification: \`python -m pytest tests/test_multi_radar_task_store.py tests/test_multi_radar_coverage.py tests/test_multi_radar_coverage_task.py tests/test_multi_radar_api.py -q\`.
- [ ] Run frontend verification: \`npm test -- src/api/multiRadar.test.ts src/map/multiRadarLayerAdapter.test.ts src/components/tasks/MultiRadarStationList.test.ts\`.
- [ ] Run: \`npm run build\`; expected: successful production build.
- [ ] Commit: \`git commit -m "feat: add multi-radar station controls"\`.

