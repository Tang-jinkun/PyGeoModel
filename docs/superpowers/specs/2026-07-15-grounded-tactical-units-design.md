# Grounded Tactical Units Design

**Status:** Approved for implementation planning on 2026-07-15

## Context

The accepted air-corridor GLB proves that self-contained tactical results can
be rendered in a standalone viewer and over the workbench DEM. The current
unit presentation is nevertheless unsuitable for final delivery:

- one `display_scale_m` value controls the vehicle, tactical symbol, label,
  and their vertical offsets;
- the enlarged demo uses an `800 m` corridor width, producing an approximately
  `608 x 368 m` vehicle body;
- each vehicle is placed from one value in the reprojected `250 m` planning
  grid, rather than from the original terrain used by the workbench;
- a horizontal body spanning mountainous terrain floats on its downhill side
  and intersects the uphill side;
- the tactical symbol and label are displaced by fixed ratios of the same
  oversized scale and have no dashed leader connecting them to the vehicle;
- warning and kill volumes overlap heavily and extend below local terrain.

Measurements from the accepted task show that the displayed vehicle footprint
spans `91-431 m` of local terrain relief. Its horizontal base sits `32-207 m`
above downhill terrain and `56-253 m` below uphill terrain. This is a geometry
and anchoring defect, not a uniform MapLibre altitude offset.

## Goals

1. Preserve real coordinates, elevations, headings, route altitudes, and zone
   dimensions.
2. Keep vehicles recognizable in a whole-scene view through explicit,
   documented cartographic exaggeration.
3. Ground every vehicle on a fitted local terrain plane derived from the
   original COG DEM.
4. Connect the physical model, tactical symbol, and short label into one
   readable tactical unit.
5. Reduce threat-volume occlusion without changing model results.
6. Keep the downloaded GLB self-contained and useful outside PyGeoModel.

## Non-Goals

- Do not change air-corridor pathfinding, risk values, route altitude, threat
  radius, or threat altitude calculations.
- Do not introduce guided cameras, narration, recording controls, or a
  platform-specific post-processing layer.
- Do not add mobile layouts or mobile acceptance work.
- Do not identify the procedural vehicle as a specific real-world weapon
  system.
- Do not backfill existing finished tasks or overwrite accepted artifacts.

## Design Principle: Truthful Exaggeration

Spatial data remains physically meaningful. Only presentation geometry is
exaggerated for readability. Every exaggerated dimension is recorded in GLB
metadata so downstream users can distinguish model data from cartographic
display choices.

The following values are never display-scaled:

- unit longitude, latitude, and ground elevation;
- unit heading;
- route coordinates and AGL/AMSL altitudes;
- warning and kill radii;
- warning and kill altitude limits.

The vehicle mesh, tactical symbol, label, leader, and ground anchor may use
display scaling.

## Unit Display Profile

Air-defense units use a reusable `UnitDisplayProfile` rather than deriving all
geometry from corridor width.

### Physical Reference Dimensions

The generic low-poly air-defense vehicle uses these reference dimensions:

- length: `12 m`;
- width: `3.2 m`;
- chassis height: `2.8 m`;
- equipment top: `7.5 m` above the contact plane.

The procedural model includes a chassis, left and right track groups, cabin,
launcher assembly, radar mast, and radar panel. The proportions remain fixed
when display-scaled.

### Vehicle Display Exaggeration

Let `scene_extent_m` be the larger horizontal extent of the emitted scene in
projected coordinates. The vehicle exaggeration factor is:

```text
clamp(scene_extent_m / 6000, 10, 15)
```

This yields a displayed vehicle length of `120-180 m` for the enlarged demo.
The factor is independent of corridor width and is shared by all emitted units
in one scene.

Metadata records both the physical and displayed dimensions. Consumers must
not infer physical size from mesh bounds.

### Tactical Symbol Scale

The tactical symbol scale is:

```text
clamp(display_vehicle_length_m * 2.2, 260, 400)
```

The crossed symbol remains readable from four horizontal bearings. Its panel
retains the current unlit light backplate and red air-defense glyph, but its
size no longer affects the vehicle mesh.

The short label is positioned immediately above the symbol with a gap equal to
`0.06 * symbol_scale_m`. It remains crossed in two perpendicular planes and
uses the existing collision-safe short-ID rules.

## Terrain Anchoring

### Source

Grounding uses the original DEM COG associated with the task's `dem_id`, not
the cropped and resampled planning raster. Sampling uses the source dataset's
CRS and nodata contract.

### Samples

For each vehicle, rotate its displayed footprint by the requested heading and
sample a `3 x 3` grid consisting of the center, edge midpoints, and corners.
Each elevation is bilinearly sampled from the original COG.

All nine samples must be finite and valid. A missing or nodata sample makes the
unit ineligible for emission and records a structured omission.

### Local Plane

Fit a least-squares plane in projected metres through the nine samples. Record:

- center ground elevation AMSL;
- normalized terrain normal;
- slope in degrees;
- plane-fit RMSE in metres.

The unit root is translated to the fitted plane at the true unit coordinate
but remains aligned to global east/up/south axes. The `model` child preserves
heading and applies pitch and roll derived from the terrain normal. The
`ground_anchor` child aligns to the fitted plane. The `leader`, tactical
symbol, label, and threat volumes remain aligned to global up and must not tilt
with the vehicle.

A `0.75 m` display-space ground clearance is applied after fitting so contact
geometry does not z-fight. This clearance is not multiplied by vehicle display
exaggeration.

The generated demo accepts candidate unit locations only when:

- slope is at most `15 degrees`;
- plane-fit RMSE is at most `5 m`;
- maximum absolute sample-to-plane residual is at most `8 m`;
- all nine terrain samples are valid.

The regular task API remains valid for steeper user-supplied positions. A unit
that cannot satisfy the terrain contract is omitted atomically and reported in
`scene3d.omitted_units` and task warnings; no partial model, symbol, or zone is
emitted.

## Tactical Unit Hierarchy

Each emitted unit uses one `unit_<normalized-id>` root with these direct roles:

1. `ground_anchor`
2. `model`
3. `leader`
4. `symbol_cross`
5. `label_cross`
6. `warning_zone`
7. `kill_zone`

Every descendant retains inherited unit identity metadata. Names continue to
use `/` separators and remain globally collision-safe.

### Ground Anchor

The ground anchor is a thin, unlit ring centered on the true unit coordinate
and aligned to the fitted local plane. Its diameter is
`0.35 * display_vehicle_length_m`. It identifies the exact data location
independently of the exaggerated vehicle footprint.

### Dashed Leader

The leader follows global up from the displayed vehicle top to the tactical
symbol's lower edge. Its available height is divided into seven equal
intervals; intervals
`1`, `3`, `5`, and `7` contain geometry and the alternating intervals are
empty. Each dash is a low-section vertical cylinder using an unlit neutral
light material. The radius is:

```text
clamp(symbol_scale_m * 0.008, 2, 4) metres
```

The symbol lower edge is separated from the vehicle top by:

```text
clamp(symbol_scale_m * 0.35, 90, 140) metres
```

The leader is visible from every horizontal bearing and is exported as merged
geometry for one draw call per unit.

## Threat Volumes

Threat radius and top altitude remain unchanged. Display geometry clips the
bottom altitude to:

```text
max(requested_min_altitude_amsl_m, unit_ground_elevation_amsl_m)
```

The original requested minimum remains in metadata. If the clipped top does
not exceed the clipped bottom, the unit fails the atomic emission contract and
is reported as omitted.

Materials use unlit semantic colors with these fill alpha values:

- warning zone: `20 / 255` (approximately `8%`);
- kill zone: `31 / 255` (approximately `12%`).

Each volume adds unlit boundary geometry:

- top ring;
- bottom ring;
- four evenly spaced vertical edge strokes.

Boundary geometry may be more opaque than the fill but must preserve terrain,
vehicle, and route readability. Warning remains amber and kill remains red.

## GLB Metadata

Each unit root includes:

```text
actual_dimensions_m
display_dimensions_m
display_exaggeration
ground_elevation_amsl_m
terrain_normal
terrain_slope_deg
terrain_fit_rmse_m
ground_clearance_m
symbol_scale_m
```

Zone metadata includes both requested and display-clipped altitude bounds.
Scene metadata includes the shared display profile and scene extent used to
derive it.

These are additive fields under schema version `1`; existing GLBs and existing
frontend parsing remain backward compatible.

## Data Flow

1. Prepare the planning DEM and compute the route exactly as today.
2. Open the original source COG and build one terrain-anchor result per threat.
3. Derive one scene-wide display profile from emitted horizontal extent.
4. Build `UnitSpec` values containing true identity, position, heading, terrain
   anchor, physical dimensions, display dimensions, symbol scale, and zones.
5. Build every unit atomically under one translation-only root. Apply terrain
   orientation only to the model and ground anchor; keep tactical and threat
   semantics globally upright.
6. Export and validate the self-contained GLB inside the existing sibling
   staging transaction.
7. Publish outputs atomically and expose the unchanged download contract.
8. The frontend loads the GLB without adding platform-only vehicle, leader,
   symbol, label, or terrain correction geometry.

## Failure Handling

- Invalid terrain samples, excessive demo slope, non-finite transforms,
  invalid clipped zones, or geometry validation failures produce structured
  unit omissions.
- The enlarged accepted demo must produce ten units and no omissions.
- Export, validation, or size-limit failure fails the task and leaves no
  partially published output directory.
- Existing task and GLB loading behavior remains backward compatible.

## Performance

- Vehicle components may remain separate semantic nodes beneath `model`, but
  repeated track and launcher primitives should be concatenated where this
  reduces draw calls without losing metadata ownership.
- Leader dashes are merged per unit.
- Zone boundary pieces are merged by semantic material per unit.
- The hard GLB ceiling remains exactly `50,000,000` bytes.
- The enlarged accepted demo should remain below the existing `15 MB` target.

## Testing

### Backend Unit Tests

- display scale is independent of corridor width and obeys the exact clamp;
- physical proportions and metadata survive export/reload;
- bilinear terrain samples and fitted plane match synthetic flat and sloped
  DEM fixtures;
- heading is preserved while pitch and roll follow the terrain normal;
- vehicle slope transforms do not tilt leaders, symbols, labels, or zones;
- the `0.75 m` display clearance is not multiplied by exaggeration;
- invalid/nodata terrain omits one whole unit with a structured reason;
- demo candidate placement rejects excessive slope, roughness, and nodata;
- unit roots contain all seven direct roles;
- the seven-interval dashed leader contains four merged dashes;
- warning and kill bottoms are clipped to local terrain while requested bounds
  remain in metadata;
- semantic fills, outlines, labels, symbols, and leader retain unlit material
  contracts;
- output publication, rollback, stale-stage cleanup, self-containment, and the
  exact GLB size ceiling remain covered.

### Frontend Tests

- additive metadata remains accepted;
- the prepared scene preserves all new inherited unit roles;
- terrain exaggeration remains `1` while any GLB overlay is visible;
- existing loading, cancellation, disposal, antimeridian, and context-loss
  coverage remains green.

### Real Artifact Acceptance

Generate a new enlarged air-corridor task and do not reuse the prior GLB.

At `1440 x 900`, capture:

- one top-oblique workbench view;
- one low side view matching the reported floating-vehicle reproduction;
- four standalone horizontal bearings.

Acceptance requires:

- task status `finished`, `warnings=[]`, ten tactical roots, and no omissions;
- each vehicle's ground anchor lies within `1 m` of its fitted plane;
- each accepted demo footprint has plane-fit RMSE at most `5 m` and maximum
  absolute terrain residual at most `8 m`;
- no systematic floating or large terrain intersection is visible from the
  side view;
- vehicle structure is recognizable in the whole-scene view and proportionate
  when focused;
- anchor, model, dashed leader, symbol, and label read as one unit from all
  four horizontal bearings;
- terrain, route, vehicles, and non-black warning/kill semantics are visible
  simultaneously;
- threat fills no longer obscure the principal route or terrain;
- no console errors, HTTP errors, unexpected request failures, control
  overlap, or external asset requests occur;
- the GLB is self-contained and valid, targets a size below `15 MB`, and never
  exceeds the hard `50,000,000` byte ceiling.

Only desktop acceptance is required.

## Rollout

The change applies only to newly generated GLBs. Existing finished task
records and files remain readable and are not migrated. The feature containers
on `5174/8001` are rebuilt only after automated verification, then the new
artifact is accepted before branch integration resumes.
