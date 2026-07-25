# Radar Batch Target Profiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a radar-only batch target profile endpoint that accepts hundreds of target points and returns one line-of-sight judgment per point.

**Architecture:** Keep the existing single-target `/profile` endpoint compatible, but refactor its implementation so single and batch analysis share one per-target calculation function. Add compact batch request/response schemas, one FastAPI route, and a frontend API client with TypeScript types.

**Tech Stack:** FastAPI, Pydantic v2, rasterio, pyproj, pytest, Vue 3, TypeScript, Vitest.

## Global Constraints

- Scope is radar only; do not add batch target support to other models.
- Keep `GET /api/radar/coverage/{task_id}/profile` behavior compatible.
- Add `POST /api/radar/coverage/{task_id}/profiles`.
- `targets` accepts minimum 1 and maximum 500 points.
- Default `samples` is 180 and uses the same clamp behavior as the single endpoint.
- Default `include_samples` is false.
- Return target-level failures in `errors` without discarding valid target results.
- Do not store batch query results in the backend task store.
- Do not create an asynchronous batch task system.

---

## File Structure

- Modify `backend/app/schemas/radar.py`: add batch target request and response models beside the existing profile models.
- Modify `backend/app/services/profile_analysis.py`: split task/DEM setup from per-target calculation and add `analyze_coverage_profiles`.
- Modify `backend/app/api/radar.py`: add the new POST route and imports.
- Modify `backend/tests/test_profile_analysis_api.py`: extend existing profile API coverage with schema, batch endpoint, partial failure, and single/batch consistency tests.
- Modify `frontend/src/api/radar.ts`: add batch profile interfaces and `getCoverageProfiles`.
- Modify `frontend/src/api/radar.test.ts`: test request serialization and keep existing normalization tests intact.

---

### Task 1: Batch Profile Schemas

**Files:**
- Modify: `backend/app/schemas/radar.py`
- Test: `backend/tests/test_profile_analysis_api.py`

**Interfaces:**
- Consumes: existing `CoverageProfileSample`.
- Produces:
  - `CoverageProfileTargetInput(id: str | None, lon: float, lat: float)`
  - `CoverageProfileBatchRequest(targets: list[CoverageProfileTargetInput], samples: int, include_samples: bool)`
  - `CoverageProfileError(id: str, index: int, lon: float, lat: float, code: str, message: str)`
  - `CoverageProfileBatchResult(task_id: str, requested_count: int, succeeded_count: int, failed_count: int, results: list[CoverageProfileResult], errors: list[CoverageProfileError])`

- [ ] **Step 1: Write failing schema tests**

Add these imports to `backend/tests/test_profile_analysis_api.py`:

```python
import pytest
from pydantic import ValidationError

from app.schemas.radar import CoverageProfileBatchRequest
```

Add these tests near the top of `backend/tests/test_profile_analysis_api.py`:

```python
def test_profile_batch_request_accepts_valid_targets() -> None:
    payload = CoverageProfileBatchRequest.model_validate(
        {
            "targets": [
                {"id": "T001", "lon": 105.010, "lat": 35.000},
                {"lon": 105.011, "lat": 35.001},
            ],
            "samples": 12,
            "include_samples": True,
        }
    )

    assert len(payload.targets) == 2
    assert payload.targets[0].id == "T001"
    assert payload.targets[1].id is None
    assert payload.samples == 12
    assert payload.include_samples is True


def test_profile_batch_request_rejects_empty_targets() -> None:
    with pytest.raises(ValidationError):
        CoverageProfileBatchRequest.model_validate({"targets": []})


def test_profile_batch_request_rejects_more_than_500_targets() -> None:
    with pytest.raises(ValidationError):
        CoverageProfileBatchRequest.model_validate(
            {
                "targets": [
                    {"lon": 105.0 + index * 0.00001, "lat": 35.0}
                    for index in range(501)
                ]
            }
        )
```

- [ ] **Step 2: Run schema tests to verify they fail**

Run:

```powershell
cd backend
python -m pytest tests/test_profile_analysis_api.py::test_profile_batch_request_accepts_valid_targets tests/test_profile_analysis_api.py::test_profile_batch_request_rejects_empty_targets tests/test_profile_analysis_api.py::test_profile_batch_request_rejects_more_than_500_targets -q
```

Expected: FAIL with an import error for `CoverageProfileBatchRequest`.

- [ ] **Step 3: Add radar schema models**

In `backend/app/schemas/radar.py`, add these models after `CoverageProfileResult`:

```python
class CoverageProfileTargetInput(BaseModel):
    id: str | None = None
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)


class CoverageProfileBatchRequest(BaseModel):
    targets: list[CoverageProfileTargetInput] = Field(min_length=1, max_length=500)
    samples: int = 180
    include_samples: bool = False


class CoverageProfileError(BaseModel):
    id: str
    index: int
    lon: float
    lat: float
    code: str
    message: str


class CoverageProfileBatchResult(BaseModel):
    task_id: str
    requested_count: int
    succeeded_count: int
    failed_count: int
    results: list[CoverageProfileResult] = Field(default_factory=list)
    errors: list[CoverageProfileError] = Field(default_factory=list)
```

- [ ] **Step 4: Run schema tests to verify they pass**

Run:

```powershell
cd backend
python -m pytest tests/test_profile_analysis_api.py::test_profile_batch_request_accepts_valid_targets tests/test_profile_analysis_api.py::test_profile_batch_request_rejects_empty_targets tests/test_profile_analysis_api.py::test_profile_batch_request_rejects_more_than_500_targets -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/schemas/radar.py backend/tests/test_profile_analysis_api.py
git commit -m "feat: add radar batch profile schemas"
```

---

### Task 2: Shared Profile Service and Batch Analysis

**Files:**
- Modify: `backend/app/services/profile_analysis.py`
- Test: `backend/tests/test_profile_analysis_api.py`

**Interfaces:**
- Consumes: `CoverageProfileBatchRequest`, `CoverageProfileBatchResult`, `CoverageProfileError`, existing `CoverageProfileResult`.
- Produces:
  - `analyze_coverage_profiles(task_id: str, request: CoverageProfileBatchRequest) -> CoverageProfileBatchResult`
  - Existing `analyze_coverage_profile(task_id: str, lon: float, lat: float, samples: int = 160) -> CoverageProfileResult` remains public and compatible.

- [ ] **Step 1: Write failing service tests**

Update the schema import in `backend/tests/test_profile_analysis_api.py`:

```python
from app.schemas.radar import CoverageProfileBatchRequest
from app.services.profile_analysis import analyze_coverage_profile, analyze_coverage_profiles
```

Add these tests after `test_read_coverage_profile_reports_terrain_obstruction`:

```python
def test_analyze_coverage_profiles_returns_compact_results(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    dem_path = write_profile_dem(tmp_path, "dem_a")
    metadata = read_dem_metadata("dem_a", dem_path)
    (tmp_path / "dem" / "dem_a" / "metadata.json").write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
    write_finished_task(tmp_path, "task_a")

    result = analyze_coverage_profiles(
        "task_a",
        CoverageProfileBatchRequest.model_validate(
            {
                "targets": [
                    {"id": "T001", "lon": 105.010, "lat": 35.000},
                    {"id": "T002", "lon": 105.004, "lat": 35.000},
                ],
                "samples": 80,
                "include_samples": False,
            }
        ),
    )

    assert result.task_id == "task_a"
    assert result.requested_count == 2
    assert result.succeeded_count == 2
    assert result.failed_count == 0
    assert [item.target_lon for item in result.results] == [105.010, 105.004]
    assert all(item.samples == [] for item in result.results)


def test_analyze_coverage_profiles_can_include_samples(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    dem_path = write_profile_dem(tmp_path, "dem_a")
    metadata = read_dem_metadata("dem_a", dem_path)
    (tmp_path / "dem" / "dem_a" / "metadata.json").write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
    write_finished_task(tmp_path, "task_a")

    result = analyze_coverage_profiles(
        "task_a",
        CoverageProfileBatchRequest.model_validate(
            {
                "targets": [{"id": "T001", "lon": 105.010, "lat": 35.000}],
                "samples": 40,
                "include_samples": True,
            }
        ),
    )

    assert result.succeeded_count == 1
    assert len(result.results[0].samples) == 40


def test_analyze_coverage_profiles_collects_target_errors(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    dem_path = write_profile_dem(tmp_path, "dem_a")
    metadata = read_dem_metadata("dem_a", dem_path)
    (tmp_path / "dem" / "dem_a" / "metadata.json").write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
    write_finished_task(tmp_path, "task_a")

    result = analyze_coverage_profiles(
        "task_a",
        CoverageProfileBatchRequest.model_validate(
            {
                "targets": [
                    {"id": "valid", "lon": 105.010, "lat": 35.000},
                    {"id": "outside", "lon": 106.500, "lat": 35.000},
                ],
                "samples": 40,
            }
        ),
    )

    assert result.requested_count == 2
    assert result.succeeded_count == 1
    assert result.failed_count == 1
    assert result.results[0].target_lon == 105.010
    assert result.errors[0].id == "outside"
    assert result.errors[0].index == 1
    assert result.errors[0].code == "PROFILE_OUTSIDE_DEM"


def test_single_and_batch_profiles_share_core_fields(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    dem_path = write_profile_dem(tmp_path, "dem_a")
    metadata = read_dem_metadata("dem_a", dem_path)
    (tmp_path / "dem" / "dem_a" / "metadata.json").write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
    write_finished_task(tmp_path, "task_a")

    single = analyze_coverage_profile("task_a", 105.010, 35.000, samples=80)
    batch = analyze_coverage_profiles(
        "task_a",
        CoverageProfileBatchRequest.model_validate(
            {
                "targets": [{"id": "same", "lon": 105.010, "lat": 35.000}],
                "samples": 80,
                "include_samples": True,
            }
        ),
    ).results[0]

    assert batch.blocked == single.blocked
    assert batch.reason == single.reason
    assert batch.distance_m == single.distance_m
    assert batch.required_height_delta_m == single.required_height_delta_m
    assert len(batch.samples) == len(single.samples)
```

- [ ] **Step 2: Run service tests to verify they fail**

Run:

```powershell
cd backend
python -m pytest tests/test_profile_analysis_api.py::test_analyze_coverage_profiles_returns_compact_results tests/test_profile_analysis_api.py::test_analyze_coverage_profiles_can_include_samples tests/test_profile_analysis_api.py::test_analyze_coverage_profiles_collects_target_errors tests/test_profile_analysis_api.py::test_single_and_batch_profiles_share_core_fields -q
```

Expected: FAIL with an import error for `analyze_coverage_profiles`.

- [ ] **Step 3: Refactor service setup into reusable helpers**

In `backend/app/services/profile_analysis.py`, add imports:

```python
from dataclasses import dataclass
from typing import Any

from app.schemas.radar import (
    CoverageProfileBatchRequest,
    CoverageProfileBatchResult,
    CoverageProfileError,
    CoverageProfileResult,
    CoverageProfileSample,
)
```

Replace the direct `CoverageProfileResult, CoverageProfileSample` schema import with the grouped import above.

Add this dataclass below `EARTH_RADIUS_M`:

```python
@dataclass
class _ProfileContext:
    task_id: str
    payload: Any
    dataset: Any
    to_projected: Transformer
    from_projected: Transformer
    to_dem: Transformer
    radar_x: float
    radar_y: float
    radar_ground_m: float
    radar_altitude_m: float
    effective_range_m: float
    radar_equation_range_m: float | None
```

Add this helper before `analyze_coverage_profile`:

```python
def _load_profile_task(task_id: str):
    task = get_task(task_id)
    if task.status != "finished":
        raise AppError("TASK_NOT_FINISHED", "Coverage profiles are available only after the task is finished.", status_code=409)
    if task.request is None:
        raise AppError("TASK_WITHOUT_REQUEST", "Task request parameters are missing.", status_code=409)
    return task


def _load_profile_context(task, dataset) -> _ProfileContext:
    if dataset.crs is None:
        raise AppError("DEM_WITHOUT_CRS", "DEM is missing coordinate reference system.")

    payload = task.request
    target_epsg = utm_epsg_from_lonlat(payload.radar.lon, payload.radar.lat)
    to_projected = Transformer.from_crs("EPSG:4326", f"EPSG:{target_epsg}", always_xy=True)
    from_projected = Transformer.from_crs(f"EPSG:{target_epsg}", "EPSG:4326", always_xy=True)
    to_dem = Transformer.from_crs("EPSG:4326", dataset.crs, always_xy=True)
    radar_x, radar_y = to_projected.transform(payload.radar.lon, payload.radar.lat)
    radar_ground_m = _sample_elevation(dataset, to_dem, payload.radar.lon, payload.radar.lat, "radar")
    effective_range_m, radar_equation_range_m = _effective_max_range(payload)

    return _ProfileContext(
        task_id=task.task_id,
        payload=payload,
        dataset=dataset,
        to_projected=to_projected,
        from_projected=from_projected,
        to_dem=to_dem,
        radar_x=radar_x,
        radar_y=radar_y,
        radar_ground_m=radar_ground_m,
        radar_altitude_m=radar_ground_m + payload.radar.height_m,
        effective_range_m=effective_range_m,
        radar_equation_range_m=radar_equation_range_m,
    )
```

- [ ] **Step 4: Extract per-target calculation**

Move the body of the current single-target calculation into this helper. The logic should be the same math currently inside `analyze_coverage_profile`; use context fields instead of recalculating task, transformers, radar elevation, and effective range:

```python
def _analyze_profile_target(
    context: _ProfileContext,
    lon: float,
    lat: float,
    *,
    samples: int,
    include_samples: bool,
) -> CoverageProfileResult:
    payload = context.payload
    sample_count = min(400, max(16, samples))
    target_x, target_y = context.to_projected.transform(lon, lat)
    dx = target_x - context.radar_x
    dy = target_y - context.radar_y
    distance_m = math.hypot(dx, dy)
    if not math.isfinite(distance_m) or distance_m <= 1:
        raise AppError("PROFILE_TARGET_TOO_CLOSE", "Profile target is too close to the radar.", status_code=400)

    target_ground_m = _sample_elevation(context.dataset, context.to_dem, lon, lat, "target")
    target_altitude_m = target_ground_m + payload.target.height_m
    azimuth_deg = (math.degrees(math.atan2(dx, dy)) + 360) % 360
    elevation_deg = math.degrees(math.atan2(target_altitude_m - context.radar_altitude_m, distance_m))

    profile_samples: list[CoverageProfileSample] = []
    obstruction: CoverageProfileSample | None = None
    required_target_altitude_m = target_altitude_m

    for index in range(sample_count):
        fraction = index / (sample_count - 1)
        sample_x = context.radar_x + dx * fraction
        sample_y = context.radar_y + dy * fraction
        sample_lon, sample_lat = context.from_projected.transform(sample_x, sample_y)
        sample_distance_m = distance_m * fraction
        terrain_m = _sample_elevation(context.dataset, context.to_dem, sample_lon, sample_lat, "profile sample")
        line_of_sight_m = context.radar_altitude_m + (target_altitude_m - context.radar_altitude_m) * fraction
        clearance_m = line_of_sight_m - (
            terrain_m
            + _curvature_bulge(
                distance_m,
                sample_distance_m,
                payload.advanced.use_curvature,
                payload.advanced.curvature_coeff,
            )
        )
        sample = CoverageProfileSample(
            distance_m=sample_distance_m,
            lon=sample_lon,
            lat=sample_lat,
            terrain_m=terrain_m,
            line_of_sight_m=line_of_sight_m,
            clearance_m=clearance_m,
        )
        profile_samples.append(sample)

        if index not in {0, sample_count - 1} and clearance_m < 0:
            if obstruction is None or clearance_m < obstruction.clearance_m:
                obstruction = sample
        if fraction > 0:
            required_altitude = context.radar_altitude_m + (
                terrain_m
                + _curvature_bulge(
                    distance_m,
                    sample_distance_m,
                    payload.advanced.use_curvature,
                    payload.advanced.curvature_coeff,
                )
                - context.radar_altitude_m
            ) / fraction
            required_target_altitude_m = max(required_target_altitude_m, required_altitude)

    min_required_target_height_m = max(0.0, required_target_altitude_m - target_ground_m)
    required_height_delta_m = max(0.0, min_required_target_height_m - payload.target.height_m)
    reason = _profile_reason(
        distance_m=distance_m,
        azimuth_deg=azimuth_deg,
        elevation_deg=elevation_deg,
        blocked=obstruction is not None,
        effective_range_m=context.effective_range_m,
        radar_equation_range_m=context.radar_equation_range_m,
        requested_range_m=payload.coverage.max_range_m,
        scan_mode=payload.coverage.scan_mode,
        sector_azimuth_deg=payload.coverage.azimuth_deg,
        beam_width_deg=payload.coverage.beam_width_deg,
        min_elevation_deg=payload.advanced.min_elevation_deg,
        max_elevation_deg=payload.advanced.max_elevation_deg,
    )

    return CoverageProfileResult(
        task_id=context.task_id,
        target_lon=lon,
        target_lat=lat,
        distance_m=distance_m,
        azimuth_deg=azimuth_deg,
        elevation_deg=elevation_deg,
        radar_ground_m=context.radar_ground_m,
        target_ground_m=target_ground_m,
        radar_altitude_m=context.radar_altitude_m,
        target_altitude_m=target_altitude_m,
        blocked=obstruction is not None,
        obstruction_distance_m=obstruction.distance_m if obstruction else None,
        obstruction_lon=obstruction.lon if obstruction else None,
        obstruction_lat=obstruction.lat if obstruction else None,
        obstruction_clearance_m=obstruction.clearance_m if obstruction else None,
        min_required_target_height_m=min_required_target_height_m,
        required_height_delta_m=required_height_delta_m,
        reason=reason,
        samples=profile_samples if include_samples else [],
    )
```

- [ ] **Step 5: Rebuild single and batch entry points**

Replace `analyze_coverage_profile` with:

```python
def analyze_coverage_profile(task_id: str, lon: float, lat: float, samples: int = 160) -> CoverageProfileResult:
    task = _load_profile_task(task_id)
    dem_path = find_dem_file(task.request.dem_id)

    try:
        import rasterio
    except ImportError as exc:
        raise AppError("RASTERIO_NOT_INSTALLED", "Rasterio is required to analyze terrain profiles.", status_code=500) from exc

    try:
        with rasterio.open(dem_path) as dataset:
            context = _load_profile_context(task, dataset)
            return _analyze_profile_target(context, lon, lat, samples=samples, include_samples=True)
    except AppError:
        raise
    except Exception as exc:
        raise AppError("PROFILE_ANALYSIS_FAILED", f"Unable to analyze terrain profile: {exc}", status_code=500) from exc
```

Add:

```python
def analyze_coverage_profiles(task_id: str, request: CoverageProfileBatchRequest) -> CoverageProfileBatchResult:
    task = _load_profile_task(task_id)
    dem_path = find_dem_file(task.request.dem_id)

    try:
        import rasterio
    except ImportError as exc:
        raise AppError("RASTERIO_NOT_INSTALLED", "Rasterio is required to analyze terrain profiles.", status_code=500) from exc

    results: list[CoverageProfileResult] = []
    errors: list[CoverageProfileError] = []

    try:
        with rasterio.open(dem_path) as dataset:
            context = _load_profile_context(task, dataset)
            for index, target in enumerate(request.targets):
                target_id = target.id if target.id is not None else str(index)
                try:
                    results.append(
                        _analyze_profile_target(
                            context,
                            target.lon,
                            target.lat,
                            samples=request.samples,
                            include_samples=request.include_samples,
                        )
                    )
                except AppError as exc:
                    errors.append(
                        CoverageProfileError(
                            id=target_id,
                            index=index,
                            lon=target.lon,
                            lat=target.lat,
                            code=exc.code,
                            message=exc.message,
                        )
                    )
    except AppError:
        raise
    except Exception as exc:
        raise AppError("PROFILE_ANALYSIS_FAILED", f"Unable to analyze terrain profiles: {exc}", status_code=500) from exc

    return CoverageProfileBatchResult(
        task_id=task_id,
        requested_count=len(request.targets),
        succeeded_count=len(results),
        failed_count=len(errors),
        results=results,
        errors=errors,
    )
```

- [ ] **Step 6: Run service tests**

Run:

```powershell
cd backend
python -m pytest tests/test_profile_analysis_api.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add backend/app/services/profile_analysis.py backend/tests/test_profile_analysis_api.py
git commit -m "feat: add radar batch profile analysis"
```

---

### Task 3: Batch Profile API Route

**Files:**
- Modify: `backend/app/api/radar.py`
- Test: `backend/tests/test_profile_analysis_api.py`

**Interfaces:**
- Consumes: `CoverageProfileBatchRequest` and `analyze_coverage_profiles`.
- Produces: `POST /api/radar/coverage/{task_id}/profiles`.

- [ ] **Step 1: Write failing API tests**

Add these tests to `backend/tests/test_profile_analysis_api.py`:

```python
def test_read_coverage_profiles_batch_returns_partial_results(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    dem_path = write_profile_dem(tmp_path, "dem_a")
    metadata = read_dem_metadata("dem_a", dem_path)
    (tmp_path / "dem" / "dem_a" / "metadata.json").write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
    write_finished_task(tmp_path, "task_a")

    response = TestClient(app).post(
        "/api/radar/coverage/task_a/profiles",
        json={
            "targets": [
                {"id": "valid", "lon": 105.010, "lat": 35.000},
                {"id": "outside", "lon": 106.500, "lat": 35.000},
            ],
            "samples": 40,
            "include_samples": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == "task_a"
    assert payload["requested_count"] == 2
    assert payload["succeeded_count"] == 1
    assert payload["failed_count"] == 1
    assert payload["results"][0]["samples"] == []
    assert payload["errors"][0]["id"] == "outside"
    assert payload["errors"][0]["code"] == "PROFILE_OUTSIDE_DEM"


def test_read_coverage_profiles_batch_rejects_empty_targets(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()

    response = TestClient(app).post("/api/radar/coverage/task_a/profiles", json={"targets": []})

    assert response.status_code == 422
```

- [ ] **Step 2: Run API tests to verify they fail**

Run:

```powershell
cd backend
python -m pytest tests/test_profile_analysis_api.py::test_read_coverage_profiles_batch_returns_partial_results tests/test_profile_analysis_api.py::test_read_coverage_profiles_batch_rejects_empty_targets -q
```

Expected: FAIL with HTTP 405 or 404 because the route does not exist.

- [ ] **Step 3: Add route imports**

In `backend/app/api/radar.py`, add `CoverageProfileBatchRequest` and `CoverageProfileBatchResult` to the `app.schemas.radar` import list. Add `analyze_coverage_profiles` to the `app.services.profile_analysis` import:

```python
from app.services.profile_analysis import analyze_coverage_profile, analyze_coverage_profiles
```

- [ ] **Step 4: Add the route**

Add this route below `read_coverage_profile`:

```python
@router.post("/coverage/{task_id}/profiles", response_model=CoverageProfileBatchResult)
def read_coverage_profiles(task_id: str, payload: CoverageProfileBatchRequest) -> CoverageProfileBatchResult:
    try:
        return analyze_coverage_profiles(task_id, payload)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc
```

- [ ] **Step 5: Run API and profile tests**

Run:

```powershell
cd backend
python -m pytest tests/test_profile_analysis_api.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/api/radar.py backend/tests/test_profile_analysis_api.py
git commit -m "feat: expose radar batch profile endpoint"
```

---

### Task 4: Frontend Batch Profile Client

**Files:**
- Modify: `frontend/src/api/radar.ts`
- Test: `frontend/src/api/radar.test.ts`

**Interfaces:**
- Produces:
  - `CoverageProfileTargetInput`
  - `CoverageProfileBatchRequest`
  - `CoverageProfileError`
  - `CoverageProfileBatchResult`
  - `getCoverageProfiles(taskId: string, targets: CoverageProfileTargetInput[], options?: { samples?: number; include_samples?: boolean })`

- [ ] **Step 1: Write failing frontend client test**

Update the import in `frontend/src/api/radar.test.ts`:

```ts
import { getCoverageProfiles, normalizeCoverageTaskStatus } from "./radar";
```

Add this test after the existing `describe("radar task normalization", ...)` block:

```ts
describe("radar batch profile client", () => {
  it("posts targets and options to the batch profile endpoint", async () => {
    const originalFetch = globalThis.fetch;
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    globalThis.fetch = (async (url: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(url), init });
      return new Response(
        JSON.stringify({
          task_id: "task_a",
          requested_count: 2,
          succeeded_count: 2,
          failed_count: 0,
          results: [],
          errors: []
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }) as typeof fetch;

    try {
      const result = await getCoverageProfiles(
        "task_a",
        [
          { id: "T001", lon: 105.01, lat: 35 },
          { lon: 105.02, lat: 35.01 }
        ],
        { samples: 80, include_samples: false }
      );

      expect(result.requested_count).toBe(2);
      expect(calls).toHaveLength(1);
      expect(calls[0].url).toBe("/api/radar/coverage/task_a/profiles");
      expect(calls[0].init?.method).toBe("POST");
      expect(JSON.parse(String(calls[0].init?.body))).toEqual({
        targets: [
          { id: "T001", lon: 105.01, lat: 35 },
          { lon: 105.02, lat: 35.01 }
        ],
        samples: 80,
        include_samples: false
      });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
```

- [ ] **Step 2: Run frontend test to verify it fails**

Run:

```powershell
cd frontend
npm test -- src/api/radar.test.ts
```

Expected: FAIL with an export error for `getCoverageProfiles`.

- [ ] **Step 3: Add frontend types**

In `frontend/src/api/radar.ts`, add these interfaces after `CoverageProfileResult`:

```ts
export interface CoverageProfileTargetInput {
  id?: string | null;
  lon: number;
  lat: number;
}

export interface CoverageProfileBatchRequest {
  targets: CoverageProfileTargetInput[];
  samples: number;
  include_samples: boolean;
}

export interface CoverageProfileBatchOptions {
  samples?: number;
  include_samples?: boolean;
}

export interface CoverageProfileError {
  id: string;
  index: number;
  lon: number;
  lat: number;
  code: string;
  message: string;
}

export interface CoverageProfileBatchResult {
  task_id: string;
  requested_count: number;
  succeeded_count: number;
  failed_count: number;
  results: CoverageProfileResult[];
  errors: CoverageProfileError[];
}
```

- [ ] **Step 4: Add frontend client function**

In `frontend/src/api/radar.ts`, add this function after `getCoverageProfile`:

```ts
export async function getCoverageProfiles(
  taskId: string,
  targets: CoverageProfileTargetInput[],
  options: CoverageProfileBatchOptions = {}
): Promise<CoverageProfileBatchResult> {
  const payload: CoverageProfileBatchRequest = {
    targets,
    samples: options.samples ?? 180,
    include_samples: options.include_samples ?? false
  };
  return requestJson<CoverageProfileBatchResult>(`/api/radar/coverage/${taskId}/profiles`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}
```

- [ ] **Step 5: Run frontend tests and type check**

Run:

```powershell
cd frontend
npm test -- src/api/radar.test.ts
npm run build
```

Expected: both commands PASS.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/api/radar.ts frontend/src/api/radar.test.ts
git commit -m "feat: add radar batch profile client"
```

---

### Task 5: Final Verification

**Files:**
- No expected source edits.

**Interfaces:**
- Consumes all previous tasks.
- Produces verified working batch radar profile behavior.

- [ ] **Step 1: Run focused backend tests**

Run:

```powershell
cd backend
python -m pytest tests/test_profile_analysis_api.py -q
```

Expected: PASS.

- [ ] **Step 2: Run relevant radar backend tests**

Run:

```powershell
cd backend
python -m pytest tests/test_profile_analysis_api.py tests/test_radar_outputs_api.py tests/test_fusion_analysis_api.py -q
```

Expected: PASS.

- [ ] **Step 3: Run frontend radar API tests**

Run:

```powershell
cd frontend
npm test -- src/api/radar.test.ts
```

Expected: PASS.

- [ ] **Step 4: Run frontend build**

Run:

```powershell
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 5: Inspect final git status**

Run:

```powershell
git status --short
```

Expected: only pre-existing unrelated local files remain, or an empty worktree if the workspace was clean before execution.

- [ ] **Step 6: Commit verification-only docs if needed**

If no files changed during verification, do not create a commit. If a small fix was required, commit only the files changed for that fix:

```powershell
git add <changed-files>
git commit -m "fix: stabilize radar batch profile verification"
```

---

## Self-Review Notes

- Spec coverage: schema limits, POST route, compact default response, optional samples, partial target errors, single endpoint compatibility, frontend client, and verification are covered by Tasks 1 through 5.
- Scope check: this plan touches only radar profile analysis and the radar frontend API client.
- Type consistency: backend batch request/result names match schema, service, and route tasks; frontend client names mirror backend JSON field names.
