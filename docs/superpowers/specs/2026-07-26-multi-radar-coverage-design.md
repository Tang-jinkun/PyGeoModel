# Multi-Radar Coverage Design

## Goal

Support a single coverage task containing 2 to 256 independently configured
radars on one DEM. A location is covered when at least one radar can detect it.
The task must provide aggregate coverage products, per-radar summaries, and a
map experience that remains responsive with hundreds of radars.

Existing single-radar coverage tasks and their output URLs remain unchanged.
The current historical-task fusion endpoint also remains available for comparing
small sets of completed single-radar tasks.

## Scope

The first implementation includes:

- Batch submission through an object array.
- Independent station position, height, beam, range, advanced, and radar
  equation parameters.
- One shared DEM per batch.
- Union coverage, multi-radar overlap, blind area, and coverage-count outputs.
- Per-radar execution summaries, including partial failures.
- Aggregated map rendering plus on-demand detailed 3D rendering for selected
  radars.
- Target evaluation that reports the union result and contributing radars.

It does not implement cooperative beamforming, sensor-track fusion, probability
fusion, or cross-DEM batches.

## API Contract

Add a separate task family under `/api/radar/multi-coverage`.

`POST /api/radar/multi-coverage` accepts:

```json
{
  "dem_id": "dem_himalaya",
  "radars": [
    {
      "radar_id": "r-001",
      "name": "North Ridge",
      "radar": { "lon": 79.8, "lat": 31.4, "height_m": 18 },
      "target": { "height_m": 0 },
      "coverage": {
        "max_range_m": 50000,
        "scan_mode": "sector",
        "azimuth_deg": 120,
        "beam_width_deg": 90
      },
      "advanced": {},
      "reserved_radar_params": {}
    }
  ]
}
```

Each object has the current single-radar request fields except `dem_id`.
`radar_id` is unique within a request and is used in summaries, URLs, map
selection, and target-evaluation contributors. `name` is optional display text.
The schema accepts 2 to 256 radars and rejects duplicate IDs, invalid station
parameters, and station footprints that do not intersect the selected DEM.

The task API supplies list, read, delete, metrics, outputs, and progress
endpoints parallel to the existing coverage task API. It also provides:

- `GET /{task_id}/radars` for paged station summaries and filters.
- `GET /{task_id}/radars/{radar_id}` for one station's configuration, status,
  metrics, and detail output URLs.
- `POST /{task_id}/evaluate-target` for a union target decision and the list of
  radar contributors.

The response reports `finished`, `partial`, or `failed` at the task level. A
task is `partial` when at least one station succeeds and at least one fails. It
is `failed` only when no station produces usable coverage.

## Computation Model

The worker validates all input before submitting work. It selects one projected
analysis CRS from the batch centroid, prepares the DEM once in that CRS, and
uses a common raster grid for every station. This makes a cell-wise coverage
count meaningful and avoids repeated DEM projection.

Station calculations reuse the existing coverage algorithm. A bounded worker
pool processes stations with a configurable concurrency cap. Each worker opens
the prepared DEM once and returns only compact station products: visible mask,
range mask, metrics, diagnostics, and the data needed for a later detail GLB.
The coordinator incrementally combines masks instead of retaining every full
station result in memory.

For each valid station result, the coordinator updates:

- `coverage_count`: unsigned integer count of detecting radars per cell.
- `visible_union`: `coverage_count >= 1`.
- `overlap`: `coverage_count >= 2`.
- `theoretical_union` and `blind`: the union of theoretical ranges minus
  `visible_union`.

The task records failures by `radar_id` with an actionable reason and continues
other stations. A batch with zero usable stations has no aggregate geometry.

## Outputs

Aggregate outputs are first-class and use the existing output manifest pattern:

- Union, overlap, and blind GeoJSON.
- Coverage-count raster and a small manifest describing its grid and histogram.
- Radar-stations GeoJSON with station ID, name, status, and summary metrics.
- Per-radar summary JSON and task-level metrics JSON.
- Optional aggregate 3D coverage metadata.

Detailed scan GLBs and heavy volume products are not generated or downloaded for
all stations by default. The backend stores enough prepared data to generate or
retrieve detail products for a selected `radar_id`; detail generation is cached
per task and station. Small platform metadata may be returned in the station
summary without loading a GLB.

## Frontend Rendering

The multi-radar task view has a searchable, virtualized station list with status
and selection controls. The map shows all stations as a single batched marker
layer and clusters them at low zoom. Aggregate union, overlap, blind, and
coverage-count layers are rendered independently with visibility and opacity
controls.

Selecting a station requests its cached detail products and loads its platform
GLB, scan animation, and detailed coverage layer. The UI limits simultaneous
detailed 3D selections to five; selecting another station replaces the oldest
detail selection. All unselected stations remain inexpensive markers. This
avoids hundreds of animation mixers, GLB downloads, and custom WebGL layers.

The map supports filtering stations by ID/name, status, and contribution to a
selected target. Focusing a station zooms to its location; focusing the task
fits the aggregate union bounds.

## Target Evaluation

The multi-radar evaluator runs the existing per-station target decision for
eligible completed stations and returns:

- `detected`: true when one or more stations detect the target.
- `contributors`: station IDs with their individual decision, range, and
  blocking reason.
- `evaluated_count` and `failed_radar_ids`.

The result is deterministic and does not require a pre-generated detail GLB.

## Error Handling and Limits

- Reject more than 256 stations, duplicate IDs, non-finite values, and batches
  without a common valid DEM footprint.
- Cap station worker concurrency to a server configuration value; default to the
  lower of available CPU capacity and eight workers.
- Return per-station validation/execution errors without discarding successful
  stations.
- Reject detail requests for stations that failed or are not part of the task.
- Keep historical single-radar task behavior unchanged.

## Testing

Backend tests cover schema bounds and uniqueness, common-grid preparation,
union/count/overlap aggregation, partial failure behavior, target contributors,
and cached station detail retrieval. API tests cover lifecycle and paged station
results.

Frontend tests cover task parsing, station-list virtualization data, aggregate
layer controls, detail-selection eviction, GLB cleanup, and marker filtering.
An integration fixture with more than 100 lightweight stations verifies bounded
concurrency and proves that aggregate rendering does not instantiate one 3D
renderer per station.
