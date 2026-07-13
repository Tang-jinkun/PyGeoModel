# Radar Workbench Integration Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bound DEM-clipped radar computation and preserve the complete radar contract when the seven-model workspace replaces the radar-only application.

**Architecture:** The backend keeps the full requested extent while capping raster cells, derives a conservative compact azimuth profile from all invalid pixels, and versions the changed coverage semantics. The frontend uses one canonical radar request type and extends shared tasks with typed model/diagnostic data plus detail-backed request restoration.

**Tech Stack:** Python 3.12, NumPy, Rasterio, Pydantic, Pytest, Vue 3, TypeScript, Vitest.

## Global Constraints

- Do not fabricate GDAL or radar outputs; backend failures remain real task failures.
- Preserve the existing radar-only `App.vue` behavior until Task 10 activates the shared workspace.
- Preserve full requested geographic extent while limiting projected coverage rasters to `16,777,216` cells.
- DEM validity is the Rasterio dataset mask intersected with finite sample values.
- Version 2 meanings are requested area, analyzed area, and unknown area as defined in the design.
- Old radar tasks without a version remain readable as contract version 1.
- Use TDD for every production-code change.

---

### Task 1: Bound Coverage Canvas and Reject Non-Finite Terrain

**Files:**
- Modify: `backend/app/services/coverage_model.py`
- Test: `backend/tests/test_coverage_model.py`

**Interfaces:**
- Produces: `MAX_COVERAGE_CELLS = 16_777_216` and `bounded_canvas(bounds, x_resolution, y_resolution, max_cells=MAX_COVERAGE_CELLS)`.
- Produces: `PreparedCoverageDem.resolution_adjusted: bool` for task warnings.

- [ ] **Step 1: Write failing bounded-canvas and non-finite DEM tests**

Add tests that call `bounded_canvas((0, 0, 200_000, 200_000), 10, 10, max_cells=10_000)` and assert `width * height <= 10_000`, bounds still cover 200 km, and both resolutions increase uniformly. Add a source DEM containing `numpy.nan` without explicit NoData and assert its projected analysis cell is false.

- [ ] **Step 2: Run tests and verify RED**

Run: `E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pytest tests/test_coverage_model.py -q`

Expected: FAIL because `bounded_canvas` and finite-mask handling do not exist.

- [ ] **Step 3: Implement the bounded canvas and finite mask**

Use a uniform scale derived from `sqrt(native_cells / max_cells)`, then increase it until rounded dimensions satisfy the budget. Build the projected transform with `from_origin(bounds[0], bounds[3], x_resolution, y_resolution)`. Before reprojection use:

```python
source_values = numpy.asarray(source_data)
source_valid = (~numpy.ma.getmaskarray(source_data) & numpy.isfinite(source_values)).astype(numpy.uint8)
source_array = numpy.where(source_valid, source_values, PROJECTED_DEM_NODATA).astype(numpy.float32)
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pytest tests/test_coverage_model.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/services/coverage_model.py backend/tests/test_coverage_model.py
git commit -m "fix: bound radar coverage raster allocation"
```

---

### Task 2: Build a Conservative DEM Analysis Profile

**Files:**
- Modify: `backend/app/services/coverage_domain.py`
- Test: `backend/tests/test_coverage_model.py`

**Interfaces:**
- Preserves: `build_coverage_domain(...) -> CoverageDomain`.
- Changes: `CoverageDomain.radius_m` is the conservative profile derived from every invalid cell rather than sparse center rays.

- [ ] **Step 1: Write the failing off-ray NoData test**

Construct a projected raster with a one-cell invalid gap whose azimuth lies halfway between two 2-degree samples. Assert the invalid cell and a farther cell on the same discrete direction are both absent from `analysis_mask`; assert a direction outside the neighboring sample interval retains its range.

- [ ] **Step 2: Run the single test and verify RED**

Run: `E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pytest tests/test_coverage_model.py -k "off_ray" -q`

Expected: FAIL because the old center-ray sampling reopens the domain behind the gap.

- [ ] **Step 3: Implement invalid-cell profile contraction**

Scan rows in chunks of at most 256. For every invalid cell inside `max_range_m`, compute azimuth, distance, lower profile index, and upper profile index. Apply `numpy.minimum.at` to both indices using `max(0, distance - sample_step_m)` as the cutoff. Rasterize the resulting profile with `_profile_to_mask`, preserving its chunk bound.

- [ ] **Step 4: Run focused and backend tests**

Run: `E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pytest tests/test_coverage_model.py -q`

Expected: PASS.

Run: `E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pytest -q`

Expected: all backend tests PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/services/coverage_domain.py backend/tests/test_coverage_model.py
git commit -m "fix: conservatively clip radar domain at nodata gaps"
```

---

### Task 3: Version Radar Coverage Semantics

**Files:**
- Modify: `backend/app/schemas/radar.py`
- Modify: `backend/app/workers/coverage_task.py`
- Modify: `backend/app/services/fusion_analysis.py`
- Modify: `backend/tests/test_fusion_analysis_api.py`
- Modify: `backend/tests/test_radar_outputs_api.py`

**Interfaces:**
- Produces: `CoverageModelMetadata.coverage_contract_version: int`, defaulting to 1 for stored legacy payloads.
- New tasks explicitly write version 2.
- Mixed fusion contracts raise `AppError("FUSION_CONTRACT_MISMATCH", ..., status_code=409)`.

- [ ] **Step 1: Write failing metadata and mixed-fusion tests**

Assert new finished task metadata contains version 2. Store two finished fusion fixtures with versions 1 and 2 and assert the fusion endpoint returns HTTP 409 with code `FUSION_CONTRACT_MISMATCH`; matching version fixtures must remain accepted.

- [ ] **Step 2: Run tests and verify RED**

Run: `E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pytest tests/test_radar_outputs_api.py tests/test_fusion_analysis_api.py -q`

Expected: FAIL because metadata is unversioned and fusion does not check compatibility.

- [ ] **Step 3: Implement version propagation and fusion guard**

Add the schema field with legacy default 1, pass `coverage_contract_version=2` when new metadata is built, and read each task's stored model metadata before geometry fusion. Reject more than one distinct version; missing data resolves to 1.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pytest tests/test_radar_outputs_api.py tests/test_fusion_analysis_api.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/schemas/radar.py backend/app/workers/coverage_task.py backend/app/services/fusion_analysis.py backend/tests/test_radar_outputs_api.py backend/tests/test_fusion_analysis_api.py
git commit -m "feat: version radar coverage contracts"
```

---

### Task 4: Align Shared Radar Task Contracts

**Files:**
- Modify: `frontend/src/models/shared.ts`
- Modify: `frontend/src/models/radar/types.ts`
- Modify: `frontend/src/api/radar.ts`
- Modify: `frontend/src/api/radar.test.ts`
- Modify: `frontend/src/composables/useTaskManager.ts`
- Modify: `frontend/src/composables/useTaskManager.test.ts`

**Interfaces:**
- `TaskSummary<Request, Metrics, Model, Diagnostics>` exposes optional `model` and `diagnostics`.
- `RadarModelMetadata` includes `beam_clip_profile`, effective range, DEM coverage ratio, and `coverage_contract_version`.
- Produces: `restoreRequest(modelId, taskId): Promise<BaseModelRequest | null>` that fetches detail when required.

- [ ] **Step 1: Write failing API and task-manager tests**

Assert radar normalization treats missing contract version as 1 and preserves version 2 plus `beam_clip_profile`. Assert a listed task without `request` triggers one detail `get`, stores the result, and returns a clone; repeated restore uses cached detail. Assert disposal or removal during the detail request prevents stale state insertion.

- [ ] **Step 2: Run tests and verify RED**

Run: `npm test -- src/api/radar.test.ts src/composables/useTaskManager.test.ts`

Expected: FAIL because shared task extras and async restore do not exist.

- [ ] **Step 3: Implement canonical types and detail-backed restore**

Make nullable simplify tolerance consistent across radar request types. Extend task generics without weakening other model definitions. Track restore request versions by task key; after `get`, store only when the manager is active, the version is current, and the task still exists. Return `structuredClone(toRaw(request))`.

- [ ] **Step 4: Run focused tests, full frontend tests, and build**

Run: `npm test -- src/api/radar.test.ts src/composables/useTaskManager.test.ts`

Expected: PASS.

Run: `npm test`

Expected: all frontend tests PASS.

Run: `npm run build`

Expected: exit 0.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/models frontend/src/api/radar.ts frontend/src/api/radar.test.ts frontend/src/composables/useTaskManager.ts frontend/src/composables/useTaskManager.test.ts
git commit -m "refactor: preserve radar metadata in shared tasks"
```

