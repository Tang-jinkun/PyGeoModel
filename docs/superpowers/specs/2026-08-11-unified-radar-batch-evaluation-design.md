# Unified Radar Batch Evaluation

## Goal

Preserve the local batch target-evaluation work while aligning it with the
unified radar task API. A batch request must work for both single-radar and
multi-radar tasks without restoring the removed legacy coverage routes.

## API Contract

- Add `POST /api/radar/tasks/{task_id}/evaluate-targets`.
- Keep `POST /api/radar/tasks/{task_id}/evaluate-target` unchanged for one
  target.
- Accept one to 500 uniquely identified targets. Each target supplies WGS84
  coordinates, an AMSL or AGL altitude reference, optional altitude, and an
  optional target type.
- Return aggregate request, success, failure, and detected counts. Each
  successful row includes its target identity, supplied altitude metadata, and
  a `RadarTaskTargetEvaluation` payload. Failed rows retain their target
  identity, coordinates, application error code, and message.

## Evaluation Behavior

- Dispatch each batch item through the same task-kind decision as the unified
  single-target endpoint.
- For single-radar tasks, preserve the existing batch behavior: convert AGL
  input to AMSL using the task DEM, then use the detailed 3D target evaluator.
- For multi-radar tasks, preserve the existing single-target behavior: return
  the station contributor results from the visibility masks. That evaluator
  currently does not use target altitude, so batch requests must not imply a
  new altitude-sensitive multi-radar detection model.
- An evaluation failure for one target must not prevent evaluation of the
  remaining targets.

## Implementation Boundaries

- Resolve the stashed legacy `/coverage/{task_id}/evaluate-targets` route by
  moving it under `/tasks/{task_id}`; do not reintroduce `/coverage` or
  `/multi-coverage` endpoints.
- Reuse the existing single-radar DEM conversion and evaluation logic where
  possible. Keep task dispatch in the radar API so it remains consistent with
  the current unified single-target endpoint.
- Update API tests to cover a batch on each task kind, individual row errors,
  and the absence of legacy paths.

## Verification

- Run the focused target-evaluation and unified-radar-task backend tests.
- Run the backend test suite or the project-defined equivalent if feasible.
- Confirm no conflict markers remain, the stash is no longer needed, and the
  working tree contains only the intended merge-resolution changes.
