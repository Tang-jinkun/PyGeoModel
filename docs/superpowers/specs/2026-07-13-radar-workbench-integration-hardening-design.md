# Radar Workbench Integration Hardening Design

## Context

The DEM-clipped radar change introduces a correct domain distinction between requested, analyzed, and unknown coverage, but it also expands the projected canvas to the full requested footprint. The multi-model workbench must preserve the new radar metadata and rendering behavior when it replaces the radar-only `App.vue`.

## Goals

1. Bound radar coverage memory use without changing the requested geographic extent.
2. Treat non-finite DEM samples as unknown even when the source has no explicit NoData value.
3. Prevent a narrow invalid DEM gap between 2-degree sample rays from reopening farther from the radar.
4. Version the changed radar coverage semantics and prevent mixed-contract fusion from silently producing misleading blind areas.
5. Preserve radar-specific model metadata and diagnostics in the shared task flow.
6. Make historical task restoration fetch task detail when list summaries do not include the request.

## Backend Design

### Bounded projected canvas

The projected output keeps the full square around the effective radar range. A helper computes the native projected resolution and dimensions, then uniformly increases both resolutions when the canvas would exceed `16,777,216` cells (`4096 x 4096`). The helper rounds dimensions conservatively and guarantees the final product does not exceed the budget. `PreparedCoverageDem` records whether adjustment occurred, and task warnings report the effective resolution.

This policy preserves extent and prevents multi-gigabyte allocations. It deliberately trades raster detail for bounded execution on extreme range/resolution combinations.

### Finite valid mask

Source validity is `dataset mask AND isfinite(source values)`. NaN and infinity are replaced with projected NoData before reprojection. The nearest-neighbor validity raster remains the authority for the projected analysis domain.

### Conservative 2-degree profile

The API keeps the compact 2-degree `beam_clip_profile`. Instead of tracing only the center ray of each 2-degree sample, the backend scans every invalid projected cell inside the requested radius. Each invalid cell lowers both neighboring profile samples to its near-edge distance. Linear interpolation between those samples therefore cannot extend beyond that cell. The final analysis mask is rasterized from the conservative profile and intersected with valid pixels.

This can classify a narrow wedge around an invalid cell as unknown, but it never invents terrain knowledge behind an invalid gap. The conservative bias is preferable to false analyzed or blocked coverage.

### Contract version

New radar task metadata carries `coverage_contract_version = 2`. Missing metadata is interpreted as version 1. Fusion accepts tasks only when all selected tasks have the same contract version; mixed versions fail with a stable `FUSION_CONTRACT_MISMATCH` error. Version 2 retains the current meanings:

- `requested_theoretical_area_m2`: full requested beam
- `theoretical_area_m2`: DEM-analyzed beam
- `unknown_area_m2`: requested beam outside the analysis domain

## Frontend Design

`RadarRequest` in `models/radar/types.ts` is the canonical request shape. Compatibility exports in `api/radar.ts` continue to expose `CoverageRequest`, but it aliases the canonical type. Nullable simplify tolerance remains supported because the backend accepts it.

The shared `TaskSummary` gains generic `Model` and `Diagnostics` slots. Radar defines typed metadata including `beam_clip_profile`, effective range, DEM coverage, and contract version. The task manager adds an async detail-backed restore operation: when a list summary lacks `request`, it calls `get(taskId)`, stores the detail, and returns a cloned request.

The radar adapter work in Task 11A will consume this typed metadata before the shared `App.vue` is activated.

## Testing

- Canvas helper tests prove the maximum cell count and preserved extent.
- DEM preparation tests prove NaN without explicit NoData remains outside the analysis domain.
- Coverage-domain tests place a one-cell invalid gap between old 2-degree rays and assert farther cells are unknown.
- Fusion tests reject mixed contract versions and accept matching versions.
- Frontend type/API tests prove nullable tolerance and radar metadata normalization.
- Task-manager tests prove detail-backed restore, clone isolation, stale response safety, and disposal safety.

## Non-Goals

- No new radar form fields.
- No new DEM source or interpolation outside valid terrain.
- No redesign of Three.js geometry in this hardening task.
- No database migration; old tasks remain readable as contract version 1.
