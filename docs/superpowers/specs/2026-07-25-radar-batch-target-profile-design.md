# Radar Batch Target Profile Design

## 1. Background

The radar workflow already supports a completed coverage task and a single-target profile query:

```text
GET /api/radar/coverage/{task_id}/profile?lon={lon}&lat={lat}&samples=180
```

That endpoint is useful for interactive map clicks, but it is not efficient for judging hundreds of target points. Each call reloads the task context, opens the DEM, creates coordinate transformers, and samples a terrain profile for one point. Repeating that flow from the frontend creates many HTTP requests and repeats expensive setup work.

This design adds radar-only batch target judgment while keeping the existing single-target endpoint unchanged.

## 2. Goals

1. Support submitting hundreds of radar target points in one request and returning one judgment result per target.
2. Reuse the existing single-target line-of-sight and reason logic so batch and single results stay consistent.
3. Avoid repeated DEM opens and transformer creation inside one batch request.
4. Keep responses compact by default, while still allowing full profile samples for debugging.
5. Return partial results when individual target points fail validation or DEM sampling.

## 3. Non-Goals

- Do not change radar coverage task creation or the coverage raster generation algorithm.
- Do not add batch target support to UAV, watchpost, artillery, recon vehicle, mobility, or air corridor models.
- Do not replace the existing single-point `/profile` endpoint.
- Do not create an asynchronous batch task system for the first version.
- Do not store batch query results in the backend task store.

## 4. API Contract

Add a new endpoint:

```text
POST /api/radar/coverage/{task_id}/profiles
```

Request body:

```json
{
  "targets": [
    { "id": "T001", "lon": 79.805, "lat": 31.482 },
    { "id": "T002", "lon": 79.812, "lat": 31.500 }
  ],
  "samples": 180,
  "include_samples": false
}
```

Request schema:

- `targets`: list of target points, minimum 1 and maximum 500.
- `targets[].id`: optional caller-provided identifier. If omitted, the backend returns a stable string index such as `"0"`.
- `targets[].lon`: longitude, `-180` to `180`.
- `targets[].lat`: latitude, `-90` to `90`.
- `samples`: optional profile sample count, same clamping behavior as the single endpoint, default `180`.
- `include_samples`: optional boolean, default `false`.

Response body:

```json
{
  "task_id": "task_20260725_...",
  "requested_count": 2,
  "succeeded_count": 1,
  "failed_count": 1,
  "results": [
    {
      "id": "T001",
      "target_lon": 79.805,
      "target_lat": 31.482,
      "distance_m": 1234.5,
      "azimuth_deg": 84.3,
      "elevation_deg": 1.2,
      "blocked": false,
      "reason": "detectable",
      "min_required_target_height_m": 0,
      "required_height_delta_m": 0,
      "samples": []
    }
  ],
  "errors": [
    {
      "id": "T002",
      "index": 1,
      "lon": 79.812,
      "lat": 31.5,
      "code": "PROFILE_OUTSIDE_DEM",
      "message": "The target is outside the DEM coverage."
    }
  ]
}
```

`results[].samples` is empty when `include_samples` is false. When true, it uses the same `CoverageProfileSample` objects as the single endpoint.

Task-level errors still fail the whole request:

- task not found
- task not finished
- task has no saved request
- DEM missing or unreadable
- rasterio unavailable

Target-level errors are collected in `errors` and do not prevent other targets from being processed.

## 5. Backend Design

Add schemas in `backend/app/schemas/radar.py`:

- `CoverageProfileTargetInput`
- `CoverageProfileBatchRequest`
- `CoverageProfileError`
- `CoverageProfileBatchResult`

Refactor `backend/app/services/profile_analysis.py` into shared context and per-target calculation:

```text
analyze_coverage_profile(task_id, lon, lat, samples)
  -> existing public single-target entry point

analyze_coverage_profiles(task_id, request)
  -> new public batch entry point

_build_profile_context(task_id)
  -> validates task, opens DEM, creates transformers, reads radar terrain once

_analyze_profile_target(context, lon, lat, samples, include_samples)
  -> calculates one target result using the existing math
```

The single endpoint should call the same internal target function as the batch endpoint. This prevents future drift between single and batch judgments.

The batch function should open the DEM once with a context manager and process targets sequentially. Sequential processing is deliberate for the first version because raster reads and shared dataset handles are simpler and safer. If later datasets or target counts grow much larger, the internal loop can be revisited without changing the API contract.

Add the FastAPI route in `backend/app/api/radar.py`:

```text
@router.post("/coverage/{task_id}/profiles", response_model=CoverageProfileBatchResult)
```

## 6. Frontend Design

Add TypeScript types and a client function in `frontend/src/api/radar.ts`:

```ts
getCoverageProfiles(taskId, targets, options)
```

The first implementation can expose only the API client and types. A richer UI for uploading, pasting, or drawing many targets can be a separate feature. Existing single-click profile behavior continues to call `getCoverageProfile()`.

When a UI is added, it should default to `include_samples: false`, show summary counts, and let users inspect failures per target.

## 7. Error Handling

The batch endpoint returns HTTP `200` when the task context is valid, even if some target points fail. Per-target failures are represented in the `errors` array with `id`, `index`, coordinates, backend error code, and message.

If every target fails for target-level reasons, the endpoint still returns `200` with `succeeded_count: 0` and `failed_count` equal to `requested_count`.

Whole-request validation failures still use FastAPI validation responses. Task-level `AppError` failures keep their existing HTTP status codes.

## 8. Performance Boundaries

The default maximum batch size is 500 targets. For 100 to 500 targets, the expected gain comes from:

- one HTTP request instead of hundreds
- one task lookup
- one DEM open
- one set of coordinate transformers
- one radar ground elevation sample
- one effective range calculation

The per-target terrain profile sampling work remains proportional to `target_count * samples`.

The response is intentionally compact by default. Returning samples for 500 targets with 180 samples each can produce a large payload, so `include_samples` must be explicitly requested.

## 9. Testing

Backend tests should cover:

- request schema accepts valid target lists and rejects empty or oversized lists
- batch endpoint uses a finished task and returns one result per valid target
- target-level DEM errors are collected without failing the whole batch
- `include_samples: false` returns empty sample lists
- `include_samples: true` returns sampled profile data
- single and batch endpoints produce consistent key fields for the same target

Frontend tests should cover:

- request body serialization for `getCoverageProfiles`
- response typing and basic result/error handling
- existing `getCoverageProfile` behavior remains unchanged

## 10. Acceptance Criteria

- A caller can submit at least 100 radar target points to one endpoint and receive corresponding results in order.
- Existing `/api/radar/coverage/{task_id}/profile` behavior remains compatible.
- Batch and single endpoints agree for the same task, target coordinate, and sample count.
- Invalid individual targets do not discard valid target results.
- Backend tests for batch profile behavior pass.
- Frontend type checks and existing frontend tests pass after the client addition.
