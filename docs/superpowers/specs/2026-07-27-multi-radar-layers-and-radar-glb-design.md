# Multi-Radar Layers And Radar GLB Recovery Design

## Goal

Show loaded multi-radar aggregate overlays in the existing workbench Layers tab, and make a historical radar task restore its own DEM before loading its GLB artifacts.

## Scope

- Reuse `WorkbenchDock`; do not create a parallel layer panel.
- Expose four aggregate multi-radar overlays: visible union, overlap, blind area, and coverage count.
- Keep the existing cooperative-radar-station group separate from aggregate result layers.
- Reuse the Dock's existing visibility, opacity, and focus controls for the four aggregate overlays.
- When a single-model history task is selected, select `task.dem_id` before task output or GLB interaction.
- Preserve GLB load state in the existing scene entry row and surface its failure state instead of silently returning when the task DEM is unavailable.

## Data Flow

1. `showMultiRadarAggregate` obtains the five GeoJSON artifacts as it does now.
2. `multiRadarLayerAdapter` retains the four aggregate artifact payloads and their Dock-compatible layer states; station points remain a separate map concern.
3. `App.vue` chooses either the normal `mapWorkspace` layer provider or the active multi-radar provider for the Dock and delegates visibility, opacity, and focus actions to that provider.
4. Selecting a normal history task selects its task DEM before putting it in the selected-task state.
5. A GLB toggle validates that the task's DEM is selected. If it is not ready, the associated scene state becomes an explicit error rather than a no-op.

## Error Handling

- Missing multi-radar output artifacts leave their corresponding aggregate layer absent; they do not block the other aggregate layers.
- A GLB request, metadata, parse, or terrain error remains attached to its existing scene-entry state and is visible in the Dock.
- The backend artifact contract is unchanged. Existing radar GLBs remain accepted when their output descriptor is present and their task DEM matches the selected DEM.

## Tests

- The multi-radar adapter exposes four Dock states after aggregate rendering and updates map visibility, opacity, and focus for each.
- The App supplies multi-radar aggregate definitions and states to `WorkbenchDock` after a layer selection.
- Selecting a normal historical radar task selects its DEM.
- A GLB request with no selected or mismatched DEM records an explicit scene-entry error.
