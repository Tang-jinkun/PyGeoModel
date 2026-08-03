# Radar Grid LOD Design

## Goal

Keep radar analysis precision unchanged while making both generated radar GLBs and the live preview visually legible across map zoom levels.

## Problem

The existing adaptive grid density applies only to the custom Three.js preview. Finished radar tasks remove that preview and display a static GLB whose `radar_result/shell_grid` mesh is baked by the backend. That mesh has fixed angular spacing, opaque emissive material, and no map-zoom behavior.

The generated grid currently samples the existing 1.5 degree ray grid with strides `(4, 3)`, which produces visual lines every 6 degrees in azimuth and 4.5 degrees in elevation. An omni result can therefore contain roughly 60 meridian paths and more than 20 elevation paths regardless of its projected screen size.

## Scope

- Preserve the 1.5 degree radar ray sampling and all detection-domain calculations.
- Export three visual grid LOD meshes from the already computed ray grid.
- Preserve `radar_result/shell_grid` as the standard LOD for compatibility.
- Switch generated GLB grid visibility by map zoom without reloading the GLB.
- Apply the existing `auto`, `sparse`, `standard`, and `detailed` density control to generated radar GLBs as well as the preview.
- Simplify the preview's sparse and standard structural lines, including supplementary lobes and ground connections.
- Reduce generated grid opacity and emissive strength without changing the detectable shell material.
- Cover backend export, frontend LOD selection, manual density override, and cleanup with automated tests.

## Generated GLB Contract

The radar scene exports these mesh nodes:

| LOD | Node name | Azimuth stride | Elevation stride | Effective spacing |
| --- | --- | ---: | ---: | --- |
| Sparse | `radar_result/shell_grid_sparse` | 12 | 8 | 18 degrees / 12 degrees |
| Standard | `radar_result/shell_grid` | 8 | 6 | 12 degrees / 9 degrees |
| Detailed | `radar_result/shell_grid_detailed` | 4 | 3 | 6 degrees / 4.5 degrees |

All three meshes are derived from the same `ray_grid`. LOD affects only which paths are exported, not ray tracing, terrain termination, the detectable shell, metrics, or metadata.

The standard node keeps the legacy node name. Existing consumers that do not understand LOD continue to render a valid, less dense grid. Sparse and detailed nodes are hidden by default in the exported scene so legacy viewers do not render all three simultaneously.

Grid materials remain unlit but use transparency and lower emissive values than the current opaque white material. Sparse and standard grids are visually quieter than detailed grids. The detectable shell and other diagnostic materials are unchanged.

## Frontend LOD Behavior

`sceneGlbAsset` already preserves each GLB mesh name when preparing the static scene. The scene layer will index the three known radar grid node names once and update their `visible` properties only when the effective LOD changes.

For `gridDensity: "auto"`, generated GLBs use:

| Map zoom | Visible generated grid |
| --- | --- |
| `< 7` | None |
| `>= 7` and `< 9` | Sparse |
| `>= 9` and `< 12` | Standard |
| `>= 12` | Detailed |

Explicit `sparse`, `standard`, or `detailed` density values pin that LOD at every zoom. If a historical GLB contains only the legacy `radar_result/shell_grid` node, it remains visible for standard and detailed selections, is used as the sparse fallback, and is hidden only in the automatic `< 7` range.

The custom layer checks the effective LOD during render and updates visibility only when the LOD key changes. This avoids mesh reconstruction, additional network requests, and map event listener lifecycle complexity.

The generic GLB loader exposes an optional grid-density setting. Scenes without radar grid node names ignore it. Updating the density control changes every currently loaded radar detection-domain GLB and becomes the initial density for subsequently loaded radar GLBs.

## Preview Behavior

The preview keeps the existing zoom thresholds of 9 and 12 but reduces non-grid structural clutter:

| Density | Rings | Meridians | Rays | Boundary segments | Ground connections | Supplementary lobe grids |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Sparse | 2 | 4 | 4 | 8 | 0 | Hidden |
| Standard | 3 | 6 | 8 | 16 | 4 | Visible, reduced |
| Detailed | 5 | 10 | 12 | 24 | 8 | Visible, reduced |

Manual density selection continues to override zoom. The full request outline follows the same boundary segment budget. Surface and scan-plane behavior are unchanged.

## Data Flow

1. The backend traces the existing full-resolution ray grid.
2. The exporter calls the grid mesh builder three times with LOD-specific strides and materials.
3. The frontend loads the GLB once and prepares named meshes as it does today.
4. `sceneGlbLayer` resolves `gridDensity` plus the current map zoom to an effective LOD.
5. The layer makes exactly one matching grid node visible, or none below zoom 7 in automatic mode.
6. Changing the workbench density control updates the preview and all loaded radar GLB layers without re-fetching assets.

## Compatibility And Failure Handling

- Historical single-grid GLBs remain renderable through the legacy node fallback.
- Non-radar GLBs and radar platform GLBs have no matching nodes and are unaffected.
- Missing sparse or detailed nodes fall back to the legacy standard node instead of hiding the result unexpectedly.
- A GLB load, metadata, or WebGL context error continues through the existing scene overlay error path.
- No new API endpoint, output filename, request field, or database migration is introduced.

## Tests

- Backend stride tests assert all three LOD definitions and their ordering.
- Backend GLB tests assert the three node names, default visibility, and quieter grid material properties.
- Frontend unit tests assert zoom-to-LOD resolution and manual override behavior.
- Scene layer tests assert that generated grid mesh visibility changes without reloading the asset and that historical single-grid GLBs use the fallback.
- Preview tests assert the reduced sparse and standard structural budgets.
- Existing radar scene, GLB loader, workspace, and frontend build checks remain green.

## Out Of Scope

- Changing radar analysis angular resolution or terrain tracing.
- Replacing tube meshes with WebGL line primitives.
- Continuous screen-space line-width scaling.
- Changing the detectable shell, scan animation, platform GLB, or result API contract.
