# Workbench DEM And GLB Overlay Design

## Status

Approved for implementation on 2026-07-14.

## Goal

Allow a user to manually overlay a task's downloadable `scene_glb` result on the
selected DEM inside the existing MapLibre workbench. The overlay must use true
geographic position and true 1:1 elevation, share the map camera and terrain
depth buffer, and preserve the GLB as an independent downloadable artifact.

The first accepted artifact is the air-corridor GLB. The workbench integration
must depend on the generic `scene_glb` output contract so later model GLBs can use
the same loader without model-specific frontend rendering code.

## Decisions

- Rendering uses a MapLibre 3D custom layer backed by Three.js.
- Loading is manual. No GLB request is made until the user enables the overlay.
- Terrain exaggeration is `1.0` while one or more GLB overlays are visible.
- Turning an overlay off removes its custom layer and disposes GPU resources.
- The existing file list and download action remain unchanged.
- Geographic conversion is applied per vertex, not approximated with one local
  origin scale, because the accepted scene spans about 100 km.
- Version 1 supports static semantic GLBs in WGS84 UTM source CRSs only.
- Multiple task GLBs may be visible at the same time when they use the selected
  DEM.
- No production director camera, animation system, GLB editor, or re-export flow
  is added.

## Existing Context

The workbench already renders the selected DEM through a MapLibre `raster-dem`
source and `setTerrain`. Radar volumes already use Three.js MapLibre custom
layers with the map canvas, WebGL context, camera matrix, and depth buffer. The
new GLB layer follows this established pattern rather than adding a second
canvas or synchronizing a separate Three.js camera.

Task result files already have typed `kind`, `download_url`, `media_type`, size,
and existence fields. Air-corridor tasks now publish:

```text
kind: scene_glb
filename: air_corridor_result.glb
media_type: model/gltf-binary
```

The GLB embeds `asset.extras.scene3d` metadata with schema version, task and
model IDs, source and geographic CRSs, local origin, units, axes, and altitude
datum.

## User Experience

### Result Control

The task result panel adds one compact `3D result` layer row when an existing
output file has `kind="scene_glb"`. The row is separate from the file download
action and contains:

- a binary visibility toggle;
- a load or error status indicator;
- an icon button with a tooltip for focusing the scene bounds.

The default state is off. Enabling the toggle starts the request and shows a
loading state in that row without covering the map. A successful load changes
the state to visible. Disabling the toggle removes the map layer and releases
the parsed scene, geometries, materials, textures, and renderer references.

The browser HTTP cache may satisfy a later request, but the workbench does not
retain hidden GPU objects. The normal Files view continues to offer the GLB
download even when preview loading is unavailable or fails.

### Focus Behavior

The focus command uses the transformed GLB bounds. It adjusts map center, zoom,
pitch, and bearing to show the complete scene while respecting the current
viewport. It does not start playback or take control of later map interaction.

### Multiple Tasks

Every overlay uses a task-scoped layer ID and independent state. Multiple GLBs
can be visible together only when each task references the currently selected
DEM. The layer list shows the task and model identity so overlays remain
distinguishable.

Changing the selected DEM removes incompatible GLB overlays before the new DEM
terrain is installed. Removing a loaded task also removes its GLB layer.

## Architecture

### Scene GLB Loader

A new module, `frontend/src/map/sceneGlbLayer.ts`, owns:

- `scene_glb` fetching with `AbortSignal` support;
- GLTFLoader parsing;
- `asset.extras.scene3d` validation;
- scene graph flattening and geographic vertex conversion;
- MapLibre custom-layer creation, update, removal, and disposal;
- transformed geographic and Mercator bounds;
- per-task layer IDs and loaded-scene registry entries.

The loader exposes task-oriented functions matching existing map-layer APIs:

```ts
loadSceneGlbLayer(map, taskId, url, context, signal)
setSceneGlbVisibility(map, taskId, visible)
focusSceneGlbLayer(map, taskId)
removeSceneGlbLayer(map, taskId)
removeAllSceneGlbLayers(map)
```

`context` supplies the expected task ID, model ID, and DEM ID. The layer does
not import an air-corridor definition.

### Workbench State

`useMapWorkspace` adds task-scoped GLB state with these explicit phases:

```text
idle -> loading -> visible
idle <- removing <- visible
loading -> error
loading -> idle (aborted)
error -> loading (retry)
```

The composable coordinates UI state, request cancellation, DEM compatibility,
MapLibre layer calls, and task cleanup. Rendering and projection math remain in
the map module. The task panel only invokes composable commands and displays
state.

### Custom Layer

The custom layer uses:

```text
type: custom
renderingMode: 3d
```

It reuses `map.getCanvas()` and the supplied WebGL context, sets
`renderer.autoClear = false`, applies MapLibre's render matrix to a Three.js
camera, resets renderer state around rendering, and requests repaints only when
needed. Static GLB scenes do not run their own animation loop.

The layer is inserted after terrain-producing map content and before the first
symbol layer when possible. This gives terrain and GLB geometry a shared depth
relationship while preserving readable map labels.

## Geographic Conversion

### Accepted Metadata

Version 1 requires:

- `schema_version === 1`;
- `units === "metre"`;
- `geographic_crs === "EPSG:4326"`;
- axes equal to `x=east`, `y=up`, `z=south`;
- finite projected and geographic origin coordinates;
- a source CRS in `EPSG:32601` through `EPSG:32660`, or `EPSG:32701`
  through `EPSG:32760`.

Other CRSs fail preview validation with a clear unsupported-CRS message. The
artifact remains downloadable.

### Vertex Pipeline

The loader updates the complete GLB scene graph matrix, bakes each mesh's world
matrix into a cloned geometry, and then converts every position. For local glTF
position `(x, y, z)`:

```text
projected_east_m = origin.projected_x + x
projected_north_m = origin.projected_y - z
altitude_amsl_m = origin.altitude_amsl_m + y
```

`proj4` converts the projected east/north coordinates from the declared UTM CRS
to WGS84 longitude and latitude. `maplibregl.MercatorCoordinate.fromLngLat`
then converts longitude, latitude, and AMSL altitude into MapLibre coordinates.

The geographic origin is converted to a Mercator anchor at its altitude datum.
Each transformed vertex stores its delta from that anchor, while the custom
layer model matrix translates the local scene to the anchor. This avoids
float32 jitter without using an inaccurate single-scale tangent-plane
approximation.

Normals are recomputed after the small projection deformation. Materials,
node names, visibility hierarchy, and node `extras` are preserved. Version 1
rejects skinned meshes and animation-dependent geometry because flattening them
would change their meaning.

### Bounds

Bounds are calculated from transformed Mercator vertices and also retained as
WGS84 bounds for camera fitting. Non-finite vertices, empty scenes, inverted
bounds, or unreasonable coordinates fail before a layer is added.

## Terrain Scale Coordination

The existing DEM terrain exaggeration is `1.35`. A small terrain-scale manager
tracks visible GLB overlay task IDs for each map:

- first visible GLB: set terrain exaggeration to `1.0`;
- additional visible GLBs: keep `1.0`;
- remove one of several GLBs: keep `1.0`;
- remove the final GLB: restore the configured `1.35` value;
- change or remove DEM: clear the registry and follow normal DEM behavior.

This is reference-counted rather than handled by each component independently,
so asynchronous removals cannot restore exaggerated terrain while another GLB
is still visible.

## Data Flow

1. A finished task exposes an existing `scene_glb` output file.
2. The result panel shows the manual overlay row in the off state.
3. The user enables it.
4. `useMapWorkspace` verifies that the task DEM equals the selected DEM and
   creates an `AbortController`.
5. The loader fetches the existing authenticated download URL and parses the
   GLB.
6. Metadata and static-scene constraints are validated.
7. Vertices are converted from local glTF coordinates through UTM/WGS84 into
   local Mercator coordinates.
8. The first visible GLB changes terrain exaggeration to `1.0`.
9. The custom layer is added and the UI enters `visible`.
10. Focus is available but not automatic.
11. Turning the toggle off or removing the task aborts pending work, removes the
    custom layer, disposes resources, and updates terrain scale state.

## Error Handling

- DEM mismatch: do not fetch; explain that the task's DEM must be selected.
- Missing or nonexistent output: do not show an enabled overlay control.
- Fetch failure: enter `error`, allow retry, and retain file download.
- Toggle off, task change, or DEM change during loading: abort and return to
  `idle` without showing an error toast.
- Invalid GLB or metadata: report the validation reason and add no partial
  custom layer.
- Unsupported CRS or scene animation: reject preview with a specific message.
- WebGL context loss: remove the registry entry and allow a later manual retry.
- Disposal is idempotent so partially initialized scenes can be cleaned up.

No preview error changes task status or server artifacts.

## Performance Boundaries

- The accepted 1.98 MB, approximately 42,800-vertex air-corridor GLB is the
  baseline and should become visible within two seconds on the development
  workstation after the response is available.
- Loading remains lazy and user initiated.
- Files above 15 MB show byte progress when `Content-Length` is available.
- The frontend does not preview files above the server's 50 MB acceptance
  ceiling.
- The static scene renders only during normal map repaints. It does not create a
  permanent animation loop.
- Geometry conversion operates on cloned buffers, allowing all source GLTF
  parser objects to be disposed after layer construction.

If later model scenes approach the ceiling and conversion causes visible UI
blocking, vertex conversion can move to a worker without changing the layer or
UI contracts. A worker is not required for this pilot.

## Compatibility

- Existing GeoJSON result layers keep their current behavior.
- Radar volume, clipped-volume, and voxel custom layers remain independent.
- Existing tasks without `scene_glb` show no new control.
- Existing GLB downloads require no backend change.
- The generic Files view remains the authoritative artifact list.
- The new loader recognizes the output kind and metadata contract, not a model
  name, so later model GLBs are opt-in through their server output only.

## Testing

### Unit Tests

- Validate schema version, axes, units, finite origin, and supported UTM EPSGs.
- Convert known north- and south-hemisphere UTM points through glTF coordinates
  and compare WGS84/Mercator results within a defined tolerance.
- Prove AMSL reconstruction and the `Z=south` sign reversal.
- Preserve node names, material transparency, and extras while flattening.
- Reject empty, non-finite, animated, skinned, or unsupported-CRS scenes.
- Dispose geometries, materials, and textures exactly once.
- Prove terrain exaggeration reference counting for zero, one, and multiple
  overlays.

### Component And Composable Tests

- Show the overlay row only for an existing `scene_glb` file.
- Do not fetch before manual activation.
- Cover idle, loading, visible, error, retry, abort, and remove transitions.
- Disable loading for a mismatched DEM while preserving download.
- Keep multiple task states isolated.
- Remove loaded scenes when the task or DEM changes.

### Regression Tests

- Existing model GeoJSON loading, visibility, opacity, focus, and removal.
- Existing radar 3D layers and controls.
- Spatial editing and DEM switching.
- Frontend production build and full backend/frontend suites.

### Real Visual Acceptance

Using the real Zanda County DEM and the accepted air-corridor GLB, Playwright
checks desktop and mobile viewports:

- the GLB is not requested before the manual toggle;
- terrain exaggeration changes from `1.35` to `1.0` while visible;
- DEM terrain and GLB geometry are both nonblank and inside the viewport;
- camera pan, zoom, pitch, and bearing keep both layers synchronized;
- representative route and threat vertices project near their expected terrain
  locations and AMSL heights;
- terrain depth occludes geometry coherently;
- the focus command frames the complete transformed bounds;
- turning the overlay off removes its pixels and restores exaggeration;
- controls and labels do not overlap or overflow at `1440x900` and `390x844`;
- browser console and failed-request logs are empty.

Screenshots and pixel evidence remain in the visualization workspace, not in
the repository.

## Acceptance Criteria

- A user can manually show and remove the real air-corridor GLB over its source
  DEM in the existing workbench.
- Overlay geometry uses true 1:1 vertical scale and per-vertex geographic
  conversion.
- MapLibre terrain and GLB share camera movement and depth behavior.
- The GLB download workflow remains available and unchanged.
- DEM mismatch and invalid metadata cannot produce a misleading overlay.
- Multiple compatible task GLBs are independently controllable.
- Removing overlays releases resources and restores terrain exaggeration after
  the final overlay is gone.
- Existing model and radar workflows pass regression tests.

## Non-Goals

- Embedding terrain in the GLB.
- Modifying or re-exporting GLB artifacts in the browser.
- Guided cameras, playback, narration, recording, or director controls.
- Supporting arbitrary projected CRSs in the first version.
- Supporting animated, skinned, or externally referenced production assets.
- Automatically loading GLBs when a task finishes or is selected.
