# Tactical Scene3D Symbols Design

## Status

Approved section by section during brainstorming and approved as a written
specification on 2026-07-15. Implementation follows the separately reviewed
plan.

## Goal

Make generated GLB model results immediately readable as portable tactical
scenes. The first integration upgrades the air-corridor result so each air
defense threat is represented by one coherent unit assembly: a simplified 3D
unit model, a multi-direction tactical symbol, a short identifier, and its
warning and kill zones.

The GLB remains the delivered result. A user must be able to download it and
understand its semantic colors in a general-purpose offline GLB viewer. The
PyGeoModel workbench remains a convenient DEM overlay and does not become the
only correct renderer.

## Current Problem

The existing air-corridor GLB already contains the route, risk samples, threat
volumes, terminals, and valid material colors. Its materials are standard
light-dependent PBR materials, but the MapLibre custom Three.js scene has no
lights. As a result, meaningful green, amber, orange, and red geometry appears
black in the workbench.

The threat volumes also lack a visible unit identity. Adding a detached
frontend icon would improve the workbench but would not improve the downloaded
artifact and could drift away from the unit geometry. The unit identity must
therefore be authored into the GLB scene graph.

## Decisions

- Extend the reusable backend `scene3d` kernel instead of post-processing GLB
  bytes in a model adapter or creating frontend-only symbols.
- Use a project-specific simplified tactical vocabulary for the first version.
  MIL-STD-2525 and APP-6 rendering are deferred.
- Add tactical assemblies directly to the GLB and keep all textures, if any,
  embedded in the binary artifact.
- Bind the unit body, symbol, label, warning zone, and kill zone below one
  semantic unit root.
- Make the tactical symbol readable from multiple horizontal viewing
  directions and show a short identifier rather than a long unit name.
- Use semantic unlit materials for routes, symbols, labels, and risk
  information. Keep moderate PBR shading on simplified unit bodies.
- Add only baseline lighting to the frontend for old PBR-only GLBs. The
  frontend must not reinterpret model colors or rebuild tactical symbols.
- Integrate air-corridor threats first. Other model adapters consume the same
  contracts in later, separately reviewed increments.

## Visual Direction

The accepted direction is a simplified 3D unit with a tactical symbol mounted
above it. This is the C2 visual variant from brainstorming, corrected so no
legacy black geometry remains behind the new symbol.

Each air-defense unit uses this visual order:

1. A compact, moderately shaded unit body establishes a physical anchor.
2. A high-contrast tactical glyph sits directly above the body.
3. A short identifier is integrated with the glyph assembly.
4. Translucent warning and kill zones remain centered on the same unit root.

At a distant map scale, the symbol and identifier carry recognition. At a near
scale, the unit body and influence volumes provide detail. Route and risk
geometry remain readable but do not visually overpower unit identity. The DEM
is context and therefore has the lowest visual priority.

The fixed hierarchy is:

```text
unit and tactical symbol
route and corridor
risk and influence zones
DEM terrain
```

## Scene Contract

### UnitSpec

The backend kernel introduces an internal, model-independent `UnitSpec`. It is
not a new public API request schema.

```text
unit_id: stable non-empty string
unit_type: supported tactical unit type or omitted for unknown
position: finite projected east/north coordinates
altitude_amsl_m: finite absolute altitude
heading_deg: optional finite clockwise heading, normalized to [0, 360)
status: supported semantic status or omitted for unknown
short_label: 1-8 uppercase ASCII letters, digits, hyphen, or underscore
display_scale_m: positive finite tactical display scale
warning_zone: optional finite inner/outer radius and altitude interval
kill_zone: optional finite inner/outer radius and altitude interval
source: model-specific semantic metadata copied into node extras
```

The initial unit types are `unknown` and `air_defense`; the initial statuses are
`unknown` and `active`. Omitted type or status maps to `unknown`, and omitted
heading maps to north (`0`). The explicit vocabulary lets later adapters add
types without changing the assembly interface. An unknown unit uses a neutral
generic body and marker, not an invented equipment subtype.

For air-corridor threats:

- `unit_id` comes from `AirDefenseThreatInput.id`;
- `short_label` uses a sanitized `name` only when the complete result fits in
  eight characters; otherwise air-corridor threats use deterministic
  one-based labels `AD-01`, `AD-02`, and so on in request order;
- the projected threat coordinate supplies `position`;
- the unit anchor altitude is the finite DEM surface elevation sampled at the
  threat coordinate;
- heading defaults to north because the current request contains no orientation;
- status is `active`;
- `display_scale_m` is the corridor width clamped to 400 through 1,200 metres;
- existing warning, kill, range, altitude, and threat-level values are retained
  in `source` and influence-zone specs.

No synthetic operational state or precise equipment subtype is inferred from
`threat_level`.

The threat minimum and maximum altitudes describe the influence volume, not the
physical ground unit position. The air-corridor worker therefore samples the
already prepared projected DEM at every threat coordinate and passes those
surface elevations to the adapter. It must not place the unit body at
`min_altitude_m`, which could bury it below high-elevation terrain.

### Unit Node Hierarchy

Every unit is exported as one parent node with stable semantic children:

```text
unit_<id>
|- model
|- symbol_cross
|- label_cross
|- warning_zone       optional
`- kill_zone          optional
```

Child node names are unique in the complete scene by including the sanitized
unit ID in their exported names. The short names above describe their semantic
roles. Node `extras` include `kind`, `unit_id`, `unit_type`, `status`, and the
child `role`. The root extras also preserve the model-specific `source`
metadata.

The parent transform owns projected position, altitude, and heading. Children
use local coordinates only. This guarantees that moving or rotating a unit
moves its body, symbol, label, and zones together. Influence zones ignore
heading geometrically but remain children for identity and lifecycle.

### Tactical Geometry

The air-defense body is a low-detail, recognizable assembly built from reusable
metre-scale primitives. It is intentionally generic and does not claim to be a
specific real-world weapon system.

The symbol uses two intersecting vertical glyph planes at right angles. Both
sides are visible, so at least one face remains readable from any horizontal
camera direction. Each air-defense face is a project-specific rectangular
light backplate with a red threat border and a simplified air-defense glyph;
it is not presented as a standards-compliant military symbol. The label uses
the same crossed arrangement immediately below the symbol. It has light glyphs
with a dark outline so terrain color does not erase it.

Short labels are generated as mesh geometry from a bundled restricted stroke
glyph set for `A-Z`, `0-9`, hyphen, and underscore. Version 1 uses no runtime
font, label texture, or external image URI. Unsupported characters are removed
during sanitization. A sanitized requested label or unit ID longer than eight
characters is not silently truncated because that can create duplicates; the
generic fallback is a deterministic `U01`, `U02` sequence derived from unit
order.

The body footprint, symbol backplate, mast height, stroke width, and label
spacing are fixed ratios of `display_scale_m`. The identity geometry formed by
the model, symbol, and label must stay within a footprint of
`1.25 * display_scale_m` and a height of `2.0 * display_scale_m`; warning and
kill zones retain their model-defined ranges and are excluded from this display
bound. These dimensions are intentionally tactical display scale rather than
claimed physical equipment dimensions, and the scale is recorded in root
extras. The assembly is part of the downloadable 3D artifact and does not
billboard toward a platform camera.

An internal `UnitDisplayOptions` controls emission of `model`, `symbol_cross`,
`label_cross`, `warning_zone`, and `kill_zone` independently. All available
children are enabled for the air-corridor integration. This is an exporter
contract rather than a new frontend or request control. A disabled child emits
no node, mesh, or otherwise unused material; at least one of model or symbol
must remain enabled so the unit retains an identity.

## Material Contract

`MaterialSpec` gains an explicit semantic shading mode instead of relying only
on RGBA:

```text
name
rgba
shading: pbr | unlit
emissive_rgb: optional fallback emissive color
double_sided
```

Semantic route, corridor, risk, tactical symbol, label, warning, kill, start,
and end materials use `unlit`. The exporter writes the standard
`KHR_materials_unlit` extension and records it in `extensionsUsed`, but not
`extensionsRequired`. It also writes matching base color and a conservative
emissive fallback so viewers without the extension do not reduce the material
to black.

Simplified unit bodies use non-metallic rough PBR materials so shape remains
legible under ordinary viewer lighting. Transparent influence zones retain
alpha blending, double-sided geometry, and conservative opacity. Their colors
remain subordinate to opaque symbols and routes.

The initial semantic palette remains stable:

| Semantic role | Color direction |
| --- | --- |
| accepted route and low risk | green |
| corridor ribbon | blue-green |
| medium risk | amber |
| warning zone | orange |
| high risk and kill zone | red |
| tactical symbol and label | high-contrast light neutral with dark outline |
| unit body | restrained neutral gray |

Color is never the only identifier: node names, extras, geometry role, and
label carry the same semantic distinction.

## Backend Architecture

### Unit Specification And Assembly

A focused `scene3d` unit module owns `UnitSpec` validation and assembly. It
depends on the existing coordinate frame and reusable primitive layer, and it
returns a hierarchy of named meshes plus node metadata. It does not know about
air-corridor request schemas.

The module handles units independently. A model adapter receives either a
complete assembly or a structured omission containing the unit ID and reason.
The scene records omissions in metadata and task warnings, allowing valid
units and the rest of the model result to remain deliverable.

The air-corridor adapter maps every input threat to a `UnitSpec` and asks the
kernel to build the assembly. Existing route, ribbon, risk, terminal, and
influence-zone calculations remain model-owned. The old standalone threat zone
nodes are replaced by the corresponding children of each unit; geometry and
numeric meaning are not duplicated.

### Hierarchical Export

The current exporter accepts a flat name-to-mesh dictionary. It is extended
with a small scene-node representation that supports:

- one optional mesh per node;
- child nodes;
- local transforms;
- material assignment;
- structured extras.

The exporter remains responsible for finite geometry validation, unique node
names, material serialization, GLB metadata injection, and reload validation.
Flat route and risk nodes continue to use the same API through root-level
nodes, preventing an air-corridor-specific exporter fork.

Structured JSON chunk manipulation is used for extras and material extensions.
No byte-string search or unstructured GLB replacement is introduced.

### Frontend Rendering

The MapLibre custom scene adds neutral hemisphere and directional light before
rendering. This provides a baseline for old PBR-only artifacts and for the new
unit bodies. Light intensity is restrained because semantic materials already
carry their own visibility.

The existing GLTFLoader remains authoritative for materials and hierarchy. The
frontend does not assign colors by node name and does not create tactical
objects. Its projection-flattening path must preserve effective visibility,
materials, textures, node names, and extras. Flattening may remove the authored
parent transforms after baking them into geometry, but it must not separate the
children spatially or semantically.

## Data Flow

1. Air-corridor calculation produces the existing route, samples, projected
   threat coordinates, request values, and finite DEM surface elevation for
   each threat coordinate.
2. The adapter maps each threat and its sampled surface elevation to a
   validated `UnitSpec`.
3. The shared unit assembler creates one tactical unit hierarchy per threat.
4. Existing route and risk result nodes and the unit hierarchies are combined
   in one `scene3d` scene.
5. The exporter validates geometry, writes PBR and unlit materials, embeds node
   extras and textures, and serializes one self-contained GLB.
6. The existing output manifest and authenticated download flow publish the
   file unchanged.
7. A general GLB viewer reads the embedded scene directly.
8. When manually enabled in PyGeoModel, the existing workbench loader projects
   the same artifact over the selected DEM and supplies baseline light only.

## Error Handling

- Duplicate, empty, or normalization-colliding unit IDs fail scene construction
  because stable node identity cannot be guaranteed.
- Missing unit type, status, or heading uses the documented `unknown`,
  `unknown`, and north-facing defaults. Missing optional names use the
  deterministic ID-derived short label.
- A unit with non-finite coordinates, altitude, heading, range, zone bounds, or
  geometry is omitted as one complete assembly. Its unit ID and reason are
  recorded in `scene3d.omitted_units` and surfaced in task warnings; no partial
  body, symbol, or influence zone is emitted.
- A threat outside the prepared DEM or over a nodata cell cannot receive a
  truthful ground anchor. It is omitted with its unit ID instead of falling
  back to an influence-zone altitude.
- An explicitly unsupported unit type or status is treated as a unit-level
  omission rather than silently mapped to a different semantic value.
- Invalid label characters are removed; an empty label uses the deterministic
  unit-index fallback.
- Missing optional warning or kill ranges omit only that zone child. Inverted
  intervals or outer radii not greater than inner radii omit the complete unit
  assembly through the structured unit-level error path.
- A material marked unlit must receive the extension, base color, and fallback
  emissive fields. Export validation rejects partial unlit serialization.
- GLB reload validation confirms all expected semantic roots and children. An
  incomplete hierarchy for an assembly that was accepted by the builder fails
  the task rather than publishing a misleading result.
- GLB structure, material serialization, metadata injection, and reload
  failures remain artifact-level errors and roll back the staged task output.
- Frontend light creation or rendering failure uses the existing overlay error
  lifecycle and never changes the downloadable server artifact.

## Compatibility

- The `scene3d` asset metadata stays at schema version 1 because geographic
  interpretation does not change.
- Existing GLBs and finished tasks remain downloadable and previewable.
- Existing flat semantic node names remain accepted by the frontend.
- New hierarchical nodes are additive to the generic GLB contract.
- Existing GeoJSON, JSON, output manifest, task status, and download contracts
  do not change.
- No public air-corridor request field is added. Heading remains an internal
  documented default until a future model requirement justifies an API field.
- `KHR_materials_unlit` is a Khronos glTF extension and does not require a
  PyGeoModel-specific viewer.
- Desktop workbench behavior is in scope. No new mobile-specific design or
  acceptance work is included.

## Testing

### Backend Unit Tests

- Validate supported unit type, status, finite position, altitude, normalized
  heading, unique ID, short-label sanitization, and deterministic fallback.
- Verify missing type, status, and heading use explicit defaults, while an
  invalid unit records one structured omission without partial children.
- Prove a parent translation and heading affect model, symbol, label, and zone
  children as one assembly.
- Verify crossed tactical geometry is double-sided and occupies both expected
  vertical planes.
- Verify warning and kill children preserve configured radii and altitude
  intervals.
- Verify PBR versus unlit material serialization, `extensionsUsed`, emissive
  fallback, alpha mode, and embedded texture references.
- Reload the GLB and assert each unit root contains all required semantic child
  roles and extras.
- Reject duplicate or normalization-colliding IDs and incomplete unlit
  materials at scene level; record invalid geometry, unsupported vocabulary,
  and malformed zones as unit-level omissions.

### Air-Corridor Integration Tests

- Map every threat in a route-found and route-not-found request to one unit
  hierarchy.
- Sample each unit anchor from the prepared projected DEM and prove it is not
  derived from the threat minimum influence altitude.
- Preserve existing threat-zone geometry and source values while moving those
  nodes below the corresponding unit root.
- Keep existing route, ribbon, samples, terminals, metadata, output manifest,
  and staging rollback behavior.
- Verify a newly generated artifact contains no duplicate standalone threat
  zones and remains below the existing 50 MB ceiling.

### Frontend Regression Tests

- Create and dispose baseline lights with each custom scene lifecycle.
- Confirm unlit material colors are not changed by frontend lighting.
- Preserve PBR materials, textures, node names, extras, and effective parent
  visibility during geographic flattening.
- Keep manual loading, DEM compatibility, true-scale terrain, focus, multiple
  overlays, deletion cleanup, and context-loss behavior unchanged.

### Real Artifact Acceptance

Generate a new air-corridor task from the enlarged deterministic scenario and
check the actual GLB in both the desktop workbench and one general offline GLB
viewer:

- no route, risk, symbol, label, warning, or kill geometry appears black;
- every threat visibly combines one unit body, tactical symbol, short label,
  warning zone, and kill zone at the same geographic anchor;
- symbols remain recognizable from at least four horizontal camera bearings;
- near and distant views preserve the agreed visual hierarchy;
- the GLB remains self-contained with no failed external resource request;
- DEM and GLB stay aligned at terrain exaggeration `1.0`;
- desktop screenshots, canvas pixel checks, browser console, and failed request
  logs provide acceptance evidence.

## Rollout

This increment ends after the real air-corridor artifact is accepted. Later
model adapters may add new unit types and result primitives through the same
kernel, but each model receives its own semantic mapping and real-artifact
review. The generic contract must not be weakened to force unrelated model
results into an air-defense vocabulary.

## Non-Goals

- Implementing formal MIL-STD-2525 or APP-6 symbol generation.
- Adding guided cameras, playback, narration, recording, or director controls.
- Embedding DEM terrain in the GLB.
- Making symbols billboard toward the PyGeoModel camera.
- Adding frontend-only tactical overlays or frontend semantic recoloring.
- Inferring a precise real-world weapon system, force affiliation, or
  operational state from current threat inputs.
- Implementing the remaining model adapters in this increment.
- Adding mobile-specific layout or visual acceptance work.
