# Full-Fidelity Cooperative Radar 3D Design

## Goal

Render a cooperative three-to-five-radar scene in which every station keeps
the complete, current single-radar visual treatment. The scene must make the
shared volume between nearby radar detection domains immediately legible.

This replaces the previous task-level fusion-shell design. It deliberately
optimizes the three-to-five-station presentation path; large multi-radar
calculations remain supported as a separate aggregate workflow.

## Visual Model

Each station is present from the start of a completed cooperative task with
the same artifacts used by a completed single-radar task:

- radar platform and antenna;
- terrain-aware detection shell and floor;
- shell grid and terrain, blocked, and unknown boundaries;
- animated scan plane.

The scene has one additional fusion artifact: a warm gold, translucent
intersection volume. It represents every point that at least two submitted
radars can detect. It is not a union shell and it has no three-or-more
coverage colour tier. For two nearby radar domains it reads as a terrain-aware
lens. For three to five stations it can have multiple connected lenses and a
shared central core.

The individual radar shells retain the existing green language. The
intersection volume uses a gold material with a restrained outline or grid so
that it remains visible inside the shells without obscuring their scan planes,
boundaries, or platforms. The former jade union shell is removed entirely.

All scan animations begin against one shared front-end clock. A stable station
phase offset prevents every plane from permanently occupying the same azimuth,
while preserving a readable cooperative rhythm.

## Scope and Limits

- A cooperative 3D task accepts three to five radar stations.
- All submitted stations receive full single-radar scene and platform GLBs;
  there is no detail-on-demand path or LRU eviction in this mode.
- Existing large-batch aggregate coverage remains available, but it does not
  automatically load full station scenes.
- Existing single-radar APIs, artifacts, materials, and scan behavior remain
  compatible and unchanged.

## Backend Data Flow

1. The multi-radar worker evaluates the common-grid coverage masks as it does
   today, including terrain and visibility-height constraints.
2. It writes the normal aggregate 2D outputs.
3. It samples each station visibility result onto one bounded common 3D grid.
   Cells with a station count of two or more form the cooperative intersection
   occupancy grid.
4. A dedicated GLB writer extracts one surface from that grid and writes
   `cooperative_intersection.glb`. It contains one named intersection mesh and
   metadata compatible with the existing scene loader.
5. For every submitted station, the worker also writes the existing complete
   single-radar `scene_glb` and `radar_platform_glb` artifacts using that
   station's request, DEM preparation, and terrain-derived height data.

The intersection is calculated by common-grid occupancy, not a mesh boolean
operation. It is therefore robust for terrain-carved, non-spherical radar
domains and does not depend on translucent-render ordering.

## API and Artifact Contract

`MultiRadarOutputs` exposes:

- `cooperative_intersection_glb`: one task-level GLB for the shared detection
  volume;
- per-station `scene_glb` and `radar_platform_glb` artifact URLs in the station
  summary or a station-artifact endpoint.

The existing `fusion_scene_glb` union artifact is not loaded for cooperative
tasks and will be retired from this presentation path. Completed tasks with
successful station calculations should expose the intersection GLB even when
the intersection is empty; the latter case is represented explicitly by a
metadata flag rather than a failed task.

## Front-End Behavior

When a cooperative task finishes, the map:

1. loads every station scene and platform GLB;
2. loads the intersection GLB when it has geometry;
3. focuses the bounds of the complete cooperative scene once;
4. keeps every station independently visible and focusable in the station
   list without recalculation.

The loading state identifies individual stations so that one failed artifact
does not hide successfully loaded stations or the aggregate outputs. A user
can toggle or focus one station, while the rest of the cooperative scene and
the intersection remain visible by default.

## Failure Behavior

- A failed station calculation is reported by station and does not invalidate
  the finished artifacts of other stations.
- A failed station scene/platform export leaves 2D aggregate output and other
  station scenes usable, with a visible station-level warning.
- Failure to write the intersection GLB records a task warning; it does not
  discard completed station scenes or 2D results.
- An empty common-detection intersection is valid and is shown as no gold
  volume, not as an error.

## Verification

Backend tests cover:

- common-grid extraction of a single `coverage_count >= 2` intersection;
- GLB metadata and intersection-node output;
- cooperative task station artifact URLs and the empty-intersection case.

Front-end tests cover:

- automatic loading of all station scene and platform artifacts;
- automatic loading of the intersection artifact when it exists;
- station visibility/focus without an on-demand coverage request;
- per-station loading failures that leave the remaining scene usable.

Manual verification uses two nearby stations to confirm two full single-radar
shells and a gold terrain-aware lens, then three to five stations to confirm
that every shell, platform, and scan remains visible and that the gold volume
does not obscure the individual radar cues.
