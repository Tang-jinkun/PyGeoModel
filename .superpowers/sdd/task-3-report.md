# Task 3 Report: Concurrent Task Manager

## Status

Completed from base commit `a496627` in `E:\Github\PyGeoModel\.worktrees\multi-model-gis-workbench`.

## Initial RED

Command:

```powershell
npm test -- src/composables/useTaskManager.test.ts
```

Output:

```text
> pygeomodel-frontend@0.1.0 test
> vitest run src/composables/useTaskManager.test.ts

RUN  v4.1.10 E:/Github/PyGeoModel/.worktrees/multi-model-gis-workbench/frontend

src/composables/useTaskManager.test.ts (0 test)

Test Files  1 failed (1)
Tests  no tests
Start at  13:03:51
Duration  1.46s (transform 57ms, setup 81ms, import 0ms, tests 0ms, environment 900ms)

FAIL  src/composables/useTaskManager.test.ts [ src/composables/useTaskManager.test.ts ]
Error: Failed to resolve import "./useTaskManager" from "src/composables/useTaskManager.test.ts". Does the file exist?
Plugin: vite:import-analysis
File: E:/Github/PyGeoModel/.worktrees/multi-model-gis-workbench/frontend/src/composables/useTaskManager.test.ts:3:31
```

This was the expected missing-module failure before production code existed.

## Initial GREEN

Command:

```powershell
npm test -- src/composables/useTaskManager.test.ts
```

Output:

```text
> pygeomodel-frontend@0.1.0 test
> vitest run src/composables/useTaskManager.test.ts

RUN  v4.1.10 E:/Github/PyGeoModel/.worktrees/multi-model-gis-workbench/frontend

Test Files  1 passed (1)
Tests  1 passed (1)
Start at  13:04:32
Duration  1.77s (transform 219ms, setup 73ms, import 511ms, tests 13ms, environment 829ms)
```

The minimal implementation initialized model task state and proved that visibility changes do not stop or reset a running UAV poll.

## Expanded RED

Command:

```powershell
npm test -- src/composables/useTaskManager.test.ts
```

Output:

```text
> pygeomodel-frontend@0.1.0 test
> vitest run src/composables/useTaskManager.test.ts

RUN  v4.1.10 E:/Github/PyGeoModel/.worktrees/multi-model-gis-workbench/frontend

src/composables/useTaskManager.test.ts (10 tests | 7 failed) 39ms
  x tracks and selects a submitted terminal task without scheduling a poll 8ms
  x refreshes a model by replacing stale tasks and polling each nonterminal task once 2ms
  x backs off failed polls to the maximum delay and resets after success 3ms
  x retains all local state when backend deletion fails 2ms
  x clears polling, failure state, and only the matching selection after deletion 2ms
  x returns a deep clone of a stored request 1ms
  x disposes idempotently and permanently prevents polling 2ms

Test Files  1 failed (1)
Tests  7 failed | 3 passed (10)
Errors  3 errors
Start at  13:06:42
Duration  1.83s (transform 230ms, setup 69ms, import 468ms, tests 39ms, environment 848ms)

FAIL  ... tracks and selects a submitted terminal task without scheduling a poll
TypeError: manager.submit is not a function

FAIL  ... refreshes a model by replacing stale tasks and polling each nonterminal task once
TypeError: manager.select is not a function

FAIL  ... backs off failed polls to the maximum delay and resets after success
TypeError: Cannot read properties of undefined (reading 'value')

FAIL  ... retains all local state when backend deletion fails
TypeError: manager.select is not a function

FAIL  ... clears polling, failure state, and only the matching selection after deletion
TypeError: Cannot read properties of undefined (reading 'value')

FAIL  ... returns a deep clone of a stored request
TypeError: manager.restoreRequest is not a function

FAIL  ... disposes idempotently and permanently prevents polling
TypeError: Cannot read properties of undefined (reading 'value')

Unhandled Rejection: Error: offline-1
Unhandled Rejection: Error: offline
Unhandled Rejection: Error: offline
```

The missing public commands/state and unhandled poll errors were the expected failures before lifecycle and retry implementation.

The first GREEN attempt then exercised all methods and failed six assertions because new poll keys compared captured version `0` against an uninitialized version map. After initializing version `0` when scheduling a new key, the focused output was:

```text
> pygeomodel-frontend@0.1.0 test
> vitest run src/composables/useTaskManager.test.ts

RUN  v4.1.10 E:/Github/PyGeoModel/.worktrees/multi-model-gis-workbench/frontend

Test Files  1 passed (1)
Tests  10 passed (10)
Start at  13:08:48
Duration  1.73s (transform 228ms, setup 67ms, import 464ms, tests 38ms, environment 805ms)
```

## Terminal Failure RED/GREEN

The implementation had generalized terminal handling from the original `finished` test. To verify the `failed` branch independently, that branch was temporarily removed after adding its regression test.

RED output:

```text
> pygeomodel-frontend@0.1.0 test
> vitest run src/composables/useTaskManager.test.ts

RUN  v4.1.10 E:/Github/PyGeoModel/.worktrees/multi-model-gis-workbench/frontend

src/composables/useTaskManager.test.ts (13 tests | 1 failed) 52ms
  x stops polling when the backend reports a failed task 12ms

Test Files  1 failed (1)
Tests  1 failed | 12 passed (13)
Start at  13:10:07
Duration  1.82s (transform 243ms, setup 91ms, import 466ms, tests 52ms, environment 839ms)

FAIL  ... stops polling when the backend reports a failed task
AssertionError: expected 1 to be +0 // Object.is equality
Expected: 0
Received: 1
```

GREEN output after restoring `failed` as terminal:

```text
> pygeomodel-frontend@0.1.0 test
> vitest run src/composables/useTaskManager.test.ts

RUN  v4.1.10 E:/Github/PyGeoModel/.worktrees/multi-model-gis-workbench/frontend

Test Files  1 passed (1)
Tests  13 passed (13)
Start at  13:10:30
Duration  1.83s (transform 285ms, setup 67ms, import 548ms, tests 41ms, environment 817ms)
```

## Implementation

- Added readonly task arrays for every registered `ModelId`, readonly selection state, and readonly aggregate connection state.
- Added composite `modelId:taskId` identity, cached per-model clients, and one timeout/in-flight poll per active key.
- Polling begins after one interval, uses per-task exponential retry capped by `maxRetryDelayMs`, resets after success, and stops on `finished` or `failed`.
- `submit()` tracks and selects its result without polling terminal results.
- `refreshModel()` atomically replaces one model list, invalidates stale/in-flight polling, clears removed failure state, and starts one timer per returned nonterminal task.
- `remove()` mutates local state only after backend success; successful cleanup removes timer, failure state, task, and matching selection.
- `restoreRequest()` returns a deep clone via `structuredClone()` and `toRaw()`.
- `dispose()` is an idempotent production lifecycle command that clears all timers/failures and permanently blocks later polling, including completion of in-flight requests and later `track()` calls.

## Cleanup And Retry Evidence

- Fake-timer tests prove first polling at exactly `pollIntervalMs`, visibility and repeated tracking do not reset the deadline, and duplicate tracking retains one timer.
- Retry calls occur at 100 ms, then 200 ms, then capped 250 ms delays for later failures; a successful nonterminal result resets the next delay to 100 ms.
- Two concurrently failing model tasks keep `connectionInterrupted` true when only one recovers, then clear it when both recover.
- Terminal `finished` and `failed` responses leave zero timers.
- Refresh removes a failed stale task, clears interruption state, and leaves exactly two timers for two refreshed nonterminal tasks; both terminal responses leave zero timers.
- Failed deletion retains task, selection, interrupted state, and retry timer. Successful deletion clears each of them.
- Repeated disposal, tracking after disposal, and resolving an in-flight request after disposal produce no later polling.

## Verification

Focused command:

```powershell
npm test -- src/composables/useTaskManager.test.ts
```

Output:

```text
> pygeomodel-frontend@0.1.0 test
> vitest run src/composables/useTaskManager.test.ts

RUN  v4.1.10 E:/Github/PyGeoModel/.worktrees/multi-model-gis-workbench/frontend

Test Files  1 passed (1)
Tests  13 passed (13)
Start at  13:13:32
Duration  1.71s (transform 227ms, setup 66ms, import 458ms, tests 43ms, environment 809ms)
```

Full frontend command:

```powershell
npm test
```

Output:

```text
> pygeomodel-frontend@0.1.0 test
> vitest run

RUN  v4.1.10 E:/Github/PyGeoModel/.worktrees/multi-model-gis-workbench/frontend

Test Files  4 passed (4)
Tests  21 passed (21)
Start at  13:13:49
Duration  1.84s (transform 660ms, setup 275ms, import 928ms, tests 84ms, environment 3.66s)
```

Production build command:

```powershell
npm run build
```

Output:

```text
> pygeomodel-frontend@0.1.0 build
> vue-tsc -b && vite build

vite v6.0.7 building for production...
transforming...
1425 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                  0.41 kB | gzip:   0.28 kB
dist/assets/index-D1azeECq.css 410.18 kB | gzip:  57.12 kB
dist/assets/index-BPdATWs5.js 2,293.07 kB | gzip: 666.89 kB
built in 15.91s

(!) Some chunks are larger than 500 kB after minification.
```

The first build attempt correctly failed before Vite because `Object.fromEntries()` lost the exact seven-key shape under strict TypeScript checking:

```text
src/composables/useTaskManager.ts(23,33): error TS2352: Conversion of type '{ [k: string]: never[]; }' to type 'Record<"radar" | "uav" | "watchpost" | "artillery" | "reconVehicle" | "mobility" | "airCorridor", TaskSummary<BaseModelRequest, Record<string, unknown>>[]>' may be a mistake because neither type sufficiently overlaps with the other.
```

The initializer was replaced with a typed loop, then the focused suite, full suite, and production build above were rerun successfully.

## Files Changed

- `frontend/src/composables/useTaskManager.ts`
- `frontend/src/composables/useTaskManager.test.ts`
- `.superpowers/sdd/task-3-report.md`

## Self-Review

- Checked every confirmed interface and semantic choice against implementation and tests.
- Confirmed visibility is stored independently and never appears in timer ownership decisions.
- Confirmed poll generations prevent late in-flight responses from reviving deleted/refreshed/disposed work.
- Confirmed failed backend deletion performs no local task, timer, failure, or selection mutation.
- Confirmed test doubles provide complete task summaries and only replace the generic backend client boundary.
- Ran `git diff --check`; no whitespace errors were reported.

## Concerns

- No blocking concerns. The production build retains the pre-existing warning for a 2.29 MB minified JavaScript chunk; bundle splitting is outside Task 3 scope.
