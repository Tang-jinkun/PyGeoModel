# Task 5 Runtime Fix Report

Status: runtime blockers addressed and verified by frontend tests/build
Date: 2026-07-15
Worktree: `E:\Github\PyGeoModel\.worktrees\independent-model-demo-scenarios`

## Scope

This change fixes the two established frontend root causes that blocked Task 5 workbench acceptance:

1. `removeRadarVolume()` could throw before MapLibre style load because it dereferenced `map.getStyle().layers` when `getStyle()` was still undefined.
2. `MapWorkspace` defaulted to the external `https://demotiles.maplibre.org/style.json` style instead of a local empty style specification.

Per the brief, I did not change DEM sources, tactical rendering, layout, other map modules, or acceptance scripts. I also did not attempt to eliminate DEM `net::ERR_ABORTED` events caused by normal MapLibre tile cancellation during pan/zoom.

## Root-Cause Verification

The acceptance report's evidence matched the current code:

- `frontend/src/map/radarVolumeLayer.ts` used `map.getStyle().layers ?? []` inside `removeRadarVolume()`, which throws when `getStyle()` is undefined.
- `frontend/src/components/map/MapWorkspace.vue` defaulted `mapStyle` to the external `demotiles` URL.

## TDD Evidence

### Red

Focused regression command:

```powershell
npm test -- src/map/radarVolumeLayer.test.ts src/components/map/MapWorkspace.test.ts
```

Observed failures before the fix:

- `src/map/radarVolumeLayer.test.ts`
  - `TypeError: Cannot read properties of undefined (reading 'layers')`
- `src/components/map/MapWorkspace.test.ts`
  - received `"https://demotiles.maplibre.org/style.json"` instead of `{ version: 8, sources: {}, layers: [] }`

### Green

Same focused regression command after the fix:

```text
Test Files  2 passed (2)
Tests       8 passed (8)
```

## Code Changes

### 1. Radar cleanup fix

File:

- `frontend/src/map/radarVolumeLayer.ts`

Change:

- Made legacy layer cleanup style-safe with `map.getStyle()?.layers ?? []`.

### 2. Local empty default style

File:

- `frontend/src/components/map/MapWorkspace.vue`

Change:

- Replaced the external default style URL with a local empty `StyleSpecification` factory:
  - `version: 8`
  - `sources: {}`
  - `layers: []`

### 3. Regression coverage

Files:

- `frontend/src/map/radarVolumeLayer.test.ts`
- `frontend/src/components/map/MapWorkspace.test.ts`

Added tests to prove:

- `removeRadarVolume()` does not throw before style load and still clears active radar-layer state.
- `MapWorkspace` constructs MapLibre with a local empty default style and no external URL.

## Verification

### Focused frontend regressions

```powershell
npm test -- src/map/radarVolumeLayer.test.ts src/components/map/MapWorkspace.test.ts
```

Result:

```text
Test Files  2 passed (2)
Tests       8 passed (8)
```

### Full frontend tests

```powershell
npm test
```

Result:

```text
Test Files  30 passed (30)
Tests       213 passed (213)
```

### Frontend production build

```powershell
npm run build
```

Result:

```text
dist/index.html                 0.41 kB | gzip:   0.28 kB
dist/assets/index-DluTEpIb.css  442.72 kB | gzip:  61.97 kB
dist/assets/index-DsWbtzSs.js   2,624.26 kB | gzip: 766.06 kB
built in 29.65s
```

Known baseline warning remained:

- Vite chunk-size warning for assets larger than `500 kB` after minification.

## Self-Review

- Confirmed the radar fix is limited to optional-safe style access and does not alter rendering behavior.
- Confirmed the default style change is limited to the initial map constructor payload and does not alter DEM installation logic.
- Confirmed regression tests fail on the old behavior and pass on the new behavior.
- Confirmed no code was added for MapLibre `ERR_ABORTED` tile cancellations, because those are expected cancellation events rather than service failures.

## Concerns

1. Task 5 workbench acceptance itself was not rerun in this pass, so this report verifies the targeted root-cause fixes rather than a fresh end-to-end acceptance result.
2. The known Vite chunk-size warning remains unchanged.
