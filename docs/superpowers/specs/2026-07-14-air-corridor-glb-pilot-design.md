# Air Corridor GLB Pilot Design

## Context

PyGeoModel currently stores air-corridor results as GeoJSON and JSON files. Those files are suitable for the platform map, but they do not provide a portable three-dimensional result that a user can download and open in general 3D software.

The broader direction is to export semantically meaningful GLB results for all seven models. This pilot validates that direction with one enlarged air-corridor scenario before the shared exporter is applied to the other models.

## Goals

- Generate one standards-based, terrain-free GLB result for every newly completed air-corridor task.
- Preserve geographic positioning through a documented local coordinate frame and embedded metadata.
- Represent only geometry supported by existing model data or deterministic derivation from model inputs.
- Keep the existing server-side output, manifest, API download, and frontend file-list workflow.
- Enlarge the synthetic air-corridor scenario so the pilot visibly demonstrates horizontal avoidance, altitude changes, risk samples, and multiple threat volumes.
- Build the coordinate, material, primitive, and export code as a reusable `scene3d` kernel for later model adapters.

## Non-Goals

- Do not include the DEM terrain mesh in the GLB.
- Do not add a production GLB viewer to the PyGeoModel frontend.
- Do not add director cameras, guided playback, narration, or recording controls.
- Do not backfill already finished air-corridor tasks.
- Do not implement the remaining six model exporters in this pilot.
- Do not claim that a ground coverage polygon is a physically calculated three-dimensional volume.

## User Delivery Contract

The current delivery workflow remains unchanged:

1. The backend computes an air-corridor task and writes all artifacts under `data/outputs/<task-id>/`.
2. `output_manifest.json` lists the GLB with the existing GeoJSON and JSON files.
3. The task output API exposes the GLB through the normal authenticated path resolution and download endpoint.
4. The frontend's existing Files tab lists the new item and downloads it. No model viewer is required in the application.

The new output contract is:

| Field | Value |
| --- | --- |
| Output kind | `scene_glb` |
| Filename | `air_corridor_result.glb` |
| Label | `Air Corridor 3D Result GLB` |
| Media type | `model/gltf-binary` |

Existing tasks remain readable. Only tasks executed by a backend containing this contract are expected to have `scene_glb`.

## Coordinate And Metadata Contract

The source air-corridor calculation already runs in a local UTM CRS. The exporter reuses those projected coordinates and maps them into a local GLB frame.

- Logical local frame: east, north, up in metres.
- glTF frame: `X = east`, `Y = up`, `Z = -north`, preserving glTF's right-handed Y-up convention.
- Horizontal origin: the center of the generated scene's projected XY bounds.
- Vertical origin: the minimum finite altitude used by any emitted scene object, rounded down to the nearest 100 metres. Scene Y values are `altitude_amsl_m - origin_altitude_m`.
- Geographic origin: longitude, latitude, and altitude are recorded so consumers can reconstruct global positions.
- Source CRS: the UTM EPSG code and WGS84 geographic CRS are recorded.

The same `scene3d` metadata object is stored in both glTF `asset.extras` and `model_metadata.json`:

```json
{
  "schema_version": 1,
  "task_id": "air_corridor_task_...",
  "model_id": "air_corridor",
  "units": "metre",
  "source_crs": "EPSG:32644",
  "geographic_crs": "EPSG:4326",
  "origin": {
    "projected_x": 0,
    "projected_y": 0,
    "longitude": 0,
    "latitude": 0,
    "altitude_amsl_m": 0
  },
  "axes": {
    "x": "east",
    "y": "up",
    "z": "south"
  }
}
```

The values above are illustrative; generated files contain actual task values. Every mesh node also carries `extras` identifying its semantic kind, source data, and relevant count or range summary.

## Scene Graph

The GLB contains these semantic objects when a route is found:

| Node group | Geometry | Meaning |
| --- | --- | --- |
| `corridor_path` | Continuous low-sided tube with joint caps | Planned path at absolute altitude |
| `corridor_ribbon` | Two-sided mesh strip | Planned corridor width following the path altitude |
| `risk_low` | Merged low-detail markers | Low-risk path samples |
| `risk_medium` | Merged low-detail markers | Medium-risk path samples |
| `risk_high` | Merged low-detail markers | High-risk path samples |
| `threat_<id>_warning` | Annular or solid translucent prism | Warning radius and configured altitude interval |
| `threat_<id>_kill` | Annular or solid translucent prism | Kill radius and configured altitude interval |
| `start` | Compact marker | Requested start point |
| `end` | Compact marker | Requested end point |

Risk markers are grouped by material rather than emitted as hundreds of separate scene nodes. Route segments are merged into one geometry. Threat volumes remain individually named so downstream users can identify and hide each source.

Risk classes are deterministic within each task. Samples are normalized by the maximum finite sample risk: values from 0 through 0.33 are low, values above 0.33 through 0.66 are medium, and values above 0.66 are high. If the maximum risk is zero, all samples are low risk. Node extras preserve the original risk minimum and maximum.

If no route is found, the task still produces a structurally valid GLB containing the start, end, and threat volumes. Path, ribbon, and risk nodes are absent, and metadata records `route_found=false`.

## Geometry Accuracy Rules

- Corridor path and risk marker altitude use `altitude_amsl_m` from the existing computed path samples.
- Corridor ribbon width uses `planning.corridor_width_m` and follows the path in 3D.
- Threat horizontal radii and minimum/maximum altitude use the request values already consumed by the risk model.
- A non-zero `min_range_m` produces an annular prism instead of silently filling the inner exclusion area.
- No threat volume is clipped to the route altitude merely for visual framing.
- No terrain mesh, synthetic building, decorative aircraft, or invented physical volume is added.
- Non-finite coordinates, inverted altitude intervals, empty required geometry, and invalid indices fail export before output commit.

## Materials

The pilot uses restrained, fixed semantic materials:

- Corridor path: opaque green.
- Corridor ribbon: translucent blue-green.
- Low risk: green.
- Medium risk: amber.
- High risk: red.
- Warning volume: translucent amber-red.
- Kill volume: translucent red.
- Start/end markers: neutral light and dark materials with distinct node names.

Materials use standard glTF PBR fields, metre-scale geometry, double-sided ribbon surfaces, and alpha blending only where transparency is required. The exporter does not depend on a platform-specific shader.

## Backend Architecture

### Shared `scene3d` Kernel

Create a focused backend package that owns reusable concerns:

- Coordinate frame creation and projected-to-glTF conversion.
- Tube, ribbon, marker, and annular-prism primitives.
- Semantic PBR material definitions.
- Scene validation and GLB export.
- Structured injection and verification of glTF extras.

`trimesh` is added as a pinned backend dependency for scene construction and GLB serialization. Any metadata adjustment operates on the structured GLB JSON chunk, not string replacement.

### Air-Corridor Adapter

The air-corridor adapter consumes the in-memory computed path, risk samples, prepared projection, request, metrics, and task ID. It builds the semantic scene without re-reading public GeoJSON or repeating route planning.

### Worker Integration

GLB generation runs inside the existing staging transaction:

1. Prepare DEM and compute the corridor as today.
2. Write existing GeoJSON and JSON artifacts.
3. Build and validate `air_corridor_result.glb` in the staging directory.
4. Include `scene_glb` in `AirCorridorPlanningOutputs`, output filename/media/label maps, and `output_manifest.json`.
5. Verify all staged outputs.
6. Atomically commit the staging directory to the task output directory.
7. Mark the task finished.

If GLB generation or validation fails, the task fails and the incomplete staging directory is removed. A finished task under the new contract must not silently omit the GLB.

## Enlarged Synthetic Scenario

The air-corridor synthetic scenario is bumped to version 2 and enlarged within the existing Zanda County DEM.

Target characteristics:

- Start-to-end geodesic span: 80 to 120 km.
- Threat count: 8 to 12.
- Altitude layers: 6 to 8, covering low, medium, and high AGL choices within aircraft constraints.
- Risk samples on an accepted path: 300 to 600.
- At least four altitude transitions.
- A horizontal detour ratio of at least 1.05 instead of a nearly straight route.
- Different warning radii, kill radii, threat levels, and terrain-relative maximum threat altitudes.
- Deterministic seed, candidate order, and request hashing remain unchanged in principle.

The scenario may use a finer route sampling interval than the GLB mesh needs. The exporter preserves the computed path shape while using bounded primitive resolution so output size remains practical.

The air-corridor metrics add enough observability to validate the larger scenario:

- `direct_distance_m`
- `horizontal_detour_ratio`
- `risk_sample_count`

The demo acceptance rule requires the configured span, 300 to 600 risk samples, at least four altitude transitions, a horizontal detour ratio of at least 1.05, all four existing spatial output kinds, and `scene_glb`.

## Size And Performance Boundaries

- Target GLB size for the enlarged pilot: under 15 MB.
- Hard acceptance ceiling: 50 MB.
- Risk markers use low-detail merged meshes.
- Route and ribbon geometry scale linearly with path sample count.
- Threat radial tessellation is bounded and independent of world-space radius.
- The GLB does not duplicate the DEM or original GeoJSON payloads.
- The enlarged route calculation may take longer than the current 25 km scenario, but remains a single server task with normal progress and failure reporting.

## Compatibility And Failure Handling

- Existing task records and old manifests remain valid.
- The generic API download implementation continues to resolve paths through the typed output-kind map.
- Unsupported or malformed GLB metadata fails tests and export validation.
- A route-planning failure still yields a context GLB, but the synthetic demo runner rejects that task because the pilot requires a found route.
- GLB export does not alter existing radar or non-air-corridor workers.
- The frontend requires no model-specific rendering changes; its generic file list displays the new label and download action.

## Verification

### Automated Tests

- Coordinate-frame tests prove ENU-to-glTF axis mapping and geographic origin round trips.
- Primitive tests cover route tubes, ribbons, solid and annular threat prisms, marker grouping, and finite vertex/index buffers.
- GLB tests verify magic/version, reload the artifact as a scene, inspect semantic node names, inspect metadata extras, and assert material transparency modes.
- Air-corridor adapter tests cover route-found and route-not-found scenes.
- Worker tests verify staging rollback on export failure and `scene_glb` inclusion on success.
- API tests verify list and download behavior with `model/gltf-binary`.
- Demo builder and acceptance tests verify the enlarged deterministic scenario boundaries.
- Full backend and frontend regression suites remain green.

### Real Runtime Verification

- Rebuild the Docker backend containing the exporter.
- Submit a new enlarged air-corridor task through the existing API.
- Confirm the task is finished, accepted, and exposes all existing outputs plus `scene_glb`.
- Confirm the GLB is under the hard size ceiling and reloads with expected nodes and metadata.
- Load the generated GLB in a temporary Three.js validation page, not the product UI.
- Capture desktop and mobile screenshots, perform non-blank canvas pixel checks, inspect framing and transparency, and provide the local preview URL to the user.
- Keep the pilot isolated until the user accepts the actual artifact appearance.

## Follow-On Rollout

After the user accepts the air-corridor artifact, the shared kernel can be extended with model adapters in this order:

1. UAV reconnaissance and recon vehicle coverage.
2. Mobility accessibility.
3. Watchpost detection and artillery coverage.
4. Radar coverage using its existing voxel and clipped-volume artifacts.

Each adapter receives its own geometry contract and real-artifact review. This pilot does not pre-commit those implementations.
