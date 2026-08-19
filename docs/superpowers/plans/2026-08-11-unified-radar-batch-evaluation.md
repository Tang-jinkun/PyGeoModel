# Unified Radar Batch Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a unified batch target-evaluation API that supports both single-radar and multi-radar tasks while retaining per-target failures.

**Architecture:** The existing unified task API remains the sole public route family. Batch rows use the same `RadarTaskTargetEvaluation` envelope as the single-target endpoint. The API decides task type and delegates evaluation to the existing single- or multi-radar evaluator; the single-radar service provides only the AGL-to-AMSL normalization shared by batch requests.

**Tech Stack:** FastAPI, Pydantic v2, Rasterio, PyProj, pytest.

## Global Constraints

- Public radar task routes remain under `/api/radar/tasks`; do not reintroduce `/coverage` or `/multi-coverage` routes.
- Batch input accepts one to 500 targets with unique `target_id` values.
- Single-radar AGL input is converted using the task DEM; multi-radar preserves its existing visibility-mask semantics and does not claim altitude-sensitive detection.
- A failing row is reported in the response and does not abort the remaining rows.

---

### Task 1: Define The Unified Batch Contract And Altitude Helper

**Files:**
- Modify: `backend/app/schemas/radar.py:461-516`
- Modify: `backend/app/services/target_evaluation.py:4-236`
- Test: `backend/tests/test_target_evaluation_api.py:71-108`

**Interfaces:**
- Consumes: `TargetEvaluationResult`, `RadarTaskTargetEvaluation`, `get_task`, and `_sample_source_dem`.
- Produces: `BatchTargetEvaluationRequest`, `BatchRadarTaskTargetEvaluation`, `BatchTargetEvaluationResult`, and `resolve_batch_target_altitude(task_id, target)`.

- [ ] **Step 1: Write the failing single-radar batch API assertion**

Update the existing batch test request to the unified path and assert the row wraps the unified envelope:

```python
response = TestClient(app).post(
    "/api/radar/tasks/task_target/evaluate-targets",
    json={"targets": [{
        "target_id": "amsl-1", "x": target_lon, "y": target_lat,
        "altitude_reference": "amsl", "altitude_m": 200,
    }]},
)

assert response.status_code == 200
payload = response.json()
assert payload["results"][0]["evaluation"]["task_type"] == "single"
assert payload["results"][0]["evaluation"]["detail"]["detectable"] is True
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest backend/tests/test_target_evaluation_api.py::test_evaluate_targets_returns_results_and_row_errors -q`

Expected: FAIL because the unified batch route and/or `evaluation` field do not exist.

- [ ] **Step 3: Define batch rows around the unified envelope**

In `backend/app/schemas/radar.py`, retain the input, request, and error schemas, and replace the old row definition with:

```python
class BatchRadarTaskTargetEvaluation(BaseModel):
    target_id: str
    altitude_reference: Literal["amsl", "agl"]
    source_altitude_m: float
    evaluation: RadarTaskTargetEvaluation


class BatchTargetEvaluationResult(BaseModel):
    task_id: str
    requested_count: int
    succeeded_count: int
    failed_count: int
    detected_count: int
    results: list[BatchRadarTaskTargetEvaluation] = Field(default_factory=list)
    errors: list[BatchTargetEvaluationError] = Field(default_factory=list)
```

In `backend/app/services/target_evaluation.py`, remove the single-only
`evaluate_coverage_targets` function and replace it with an altitude helper:

```python
def resolve_batch_target_altitude(
    task_id: str,
    target: BatchTargetEvaluationInput,
) -> float:
    altitude_m = float(target.altitude_m or 0)
    if target.altitude_reference == "amsl":
        return altitude_m

    task = get_task(task_id)
    if task.request is None:
        raise AppError(
            "TASK_WITHOUT_REQUEST",
            "Task request parameters are missing.",
            status_code=409,
        )
    terrain_m = _sample_source_dem(
        task.request.dem_id,
        target.x,
        target.y,
        input_is_wgs84=True,
    )
    if terrain_m is None:
        raise AppError(
            "TARGET_TERRAIN_UNAVAILABLE",
            "Target terrain elevation is unavailable.",
            status_code=409,
        )
    return altitude_m + terrain_m
```

- [ ] **Step 4: Run the focused test to verify the contract remains red until Task 2**

Run: `pytest backend/tests/test_target_evaluation_api.py::test_evaluate_targets_returns_results_and_row_errors -q`

Expected: FAIL because the API route has not been wired to the new contract.

### Task 2: Resolve The Router Conflict With Unified Task Dispatch

**Files:**
- Modify: `backend/app/api/radar.py:7-55,256-276,368-535`
- Test: `backend/tests/test_unified_radar_tasks_api.py:88-151`

**Interfaces:**
- Consumes: `BatchTargetEvaluationRequest`, `BatchRadarTaskTargetEvaluation`, `BatchTargetEvaluationError`, `BatchTargetEvaluationResult`, `resolve_batch_target_altitude`, `_task_kind`, `evaluate_coverage_target`, and `evaluate_multi_radar_target`.
- Produces: `_evaluate_radar_task_target(task_id, payload)` and `POST /tasks/{task_id}/evaluate-targets`.

- [ ] **Step 1: Write the failing multi-radar batch route test**

Add this test beside the unified single-target test. It uses the established
mocked multi-radar evaluator and verifies the common response envelope:

```python
def test_unified_batch_target_endpoint_wraps_multi_results(tmp_path, monkeypatch) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    monkeypatch.setattr(
        radar,
        "evaluate_multi_radar_target",
        lambda task_id, payload: {
            "task_id": task_id,
            "detected": True,
            "contributors": [{"radar_id": "north", "detected": True}],
        },
    )

    response = TestClient(create_app()).post(
        "/api/radar/tasks/multi_task_target/evaluate-targets",
        json={"targets": [{
            "target_id": "target-1", "x": 79, "y": 31.5,
            "altitude_reference": "agl", "altitude_m": 100,
        }]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["detected_count"] == 1
    assert payload["results"][0]["evaluation"] == {
        "task_id": "multi_task_target",
        "task_type": "multi",
        "detected": True,
        "detail": None,
        "contributors": [{"radar_id": "north", "detected": True}],
    }
```

- [ ] **Step 2: Run the multi-radar test to verify it fails**

Run: `pytest backend/tests/test_unified_radar_tasks_api.py::test_unified_batch_target_endpoint_wraps_multi_results -q`

Expected: FAIL with HTTP 404 before the batch route is added.

- [ ] **Step 3: Resolve imports and factor the unified evaluator**

Remove all conflict markers and legacy `/coverage` route content from
`backend/app/api/radar.py`. Import the batch schemas and altitude helper. Move
the current single-target dispatch body into this helper, then make the
existing endpoint delegate to it:

```python
def _evaluate_radar_task_target(
    task_id: str,
    payload: TargetEvaluationRequest,
) -> RadarTaskTargetEvaluation:
    task_kind = _task_kind(task_id)
    if task_kind == "single":
        detail = TargetEvaluationResult.model_validate(
            evaluate_coverage_target(task_id, payload)
        )
        return RadarTaskTargetEvaluation(
            task_id=task_id,
            task_type="single",
            detected=detail.detectable,
            detail=detail,
        )
    result = evaluate_multi_radar_target(task_id, payload)
    return RadarTaskTargetEvaluation.model_validate(
        {"task_type": "multi", **result}
    )


@router.post("/tasks/{task_id}/evaluate-target", response_model=RadarTaskTargetEvaluation)
def evaluate_radar_task_target(task_id: str, payload: TargetEvaluationRequest) -> RadarTaskTargetEvaluation:
    try:
        return _evaluate_radar_task_target(task_id, payload)
    except AppError as exc:
        raise _http_error(exc) from exc
```

- [ ] **Step 4: Add the unified batch endpoint**

Add the endpoint next to the single-target route. It samples terrain only for
single-radar AGL rows, calls the shared evaluator for both task kinds, and
captures `AppError` per row:

```python
@router.post("/tasks/{task_id}/evaluate-targets", response_model=BatchTargetEvaluationResult)
def evaluate_radar_task_targets(
    task_id: str,
    payload: BatchTargetEvaluationRequest,
) -> BatchTargetEvaluationResult:
    task_kind = _task_kind(task_id)
    results: list[BatchRadarTaskTargetEvaluation] = []
    errors: list[BatchTargetEvaluationError] = []
    for target in payload.targets:
        try:
            altitude_m = (
                resolve_batch_target_altitude(task_id, target)
                if task_kind == "single"
                else float(target.altitude_m or 0)
            )
            evaluation = _evaluate_radar_task_target(
                task_id,
                TargetEvaluationRequest(
                    x=target.x, y=target.y, z=altitude_m,
                    target_type=target.target_type,
                ),
            )
            results.append(BatchRadarTaskTargetEvaluation(
                target_id=target.target_id,
                altitude_reference=target.altitude_reference,
                source_altitude_m=float(target.altitude_m or 0),
                evaluation=evaluation,
            ))
        except AppError as exc:
            errors.append(BatchTargetEvaluationError(
                target_id=target.target_id, x=target.x, y=target.y,
                code=exc.code, message=exc.message,
            ))
    return BatchTargetEvaluationResult(
        task_id=task_id,
        requested_count=len(payload.targets),
        succeeded_count=len(results), failed_count=len(errors),
        detected_count=sum(item.evaluation.detected for item in results),
        results=results, errors=errors,
    )
```

- [ ] **Step 5: Run the focused unified API tests**

Run: `pytest backend/tests/test_unified_radar_tasks_api.py backend/tests/test_target_evaluation_api.py -q`

Expected: PASS with the unified single-target, single-radar batch (including
an AGL terrain-unavailable row error), and multi-radar batch cases all
succeeding.

### Task 3: Verify Migration Boundaries And Commit The Resolution

**Files:**
- Modify: `backend/tests/test_unified_radar_tasks_api.py:147-151`
- Modify: `docs/superpowers/specs/2026-08-11-unified-radar-batch-evaluation-design.md`
- Create: `docs/superpowers/plans/2026-08-11-unified-radar-batch-evaluation.md`

**Interfaces:**
- Consumes: the public FastAPI route table.
- Produces: regression coverage that legacy batch routes are absent and a clean merge-resolution commit.

- [ ] **Step 1: Extend the legacy-path regression test**

Add the batch route assertion to `test_legacy_task_paths_are_not_supported`:

```python
assert client.post(
    "/api/radar/coverage/task_target/evaluate-targets",
    json={"targets": []},
).status_code == 404
```

- [ ] **Step 2: Run the migration-boundary test**

Run: `pytest backend/tests/test_unified_radar_tasks_api.py::test_legacy_task_paths_are_not_supported -q`

Expected: PASS.

- [ ] **Step 3: Run required verification**

Run: `git diff --check && pytest backend/tests/test_target_evaluation_api.py backend/tests/test_unified_radar_tasks_api.py -q`

Expected: exit code 0, no whitespace errors, and all focused tests passing.

- [ ] **Step 4: Inspect and commit the merged resolution**

Run:

```bash
git status --short
git diff --cached --check
git add backend/app/api/radar.py backend/app/schemas/radar.py \
  backend/app/services/target_evaluation.py \
  backend/tests/test_target_evaluation_api.py \
  backend/tests/test_unified_radar_tasks_api.py \
  docs/superpowers/specs/2026-08-11-unified-radar-batch-evaluation-design.md \
  docs/superpowers/plans/2026-08-11-unified-radar-batch-evaluation.md
git commit -m "feat: unify radar batch target evaluation"
```

Expected: conflict markers are gone, the previous stash is dropped only after
tests pass, and the commit records the batch API adaptation separately from
the upstream merge commit.
