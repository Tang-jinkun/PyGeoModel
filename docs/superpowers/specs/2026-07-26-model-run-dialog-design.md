# Model Run Dialog Design

## Goal

Replace the persistent right-hand parameter inspector with a reusable model run dialog. A task is configured only through this dialog, including its explicit input files, spatial inputs, and analysis parameters.

## Workspace Layout

- The left dock remains the model library, layers, and data catalog.
- The map expands into the space previously occupied by the right inspector.
- The map has no run button and never creates a task directly.
- Selecting a model in the model library opens that model's run dialog immediately.
- The task center remains the place for task progress, history, and results.

## Run Dialog

The shared dialog shell renders a model-specific schema in three sections:

1. Input data: required and optional file slots. The terrain DEM is the initial required slot.
2. Spatial inputs: coordinates, start/end locations, routes, and threat locations.
3. Analysis parameters: the model's numerical, boolean, and enumerated parameters.

The footer contains only Cancel and Run analysis. Closing or cancelling preserves the model draft. Submitting validates required inputs and creates a task, then closes the dialog.

## Explicit File Inputs

- The data catalog uploads, lists, and deletes assets; choosing an asset there does not implicitly configure a model task.
- Each model definition exposes input slot metadata: key, label, accepted asset types, required status, and cardinality.
- The dialog renders the slots from that metadata. A slot lets the user select an existing asset or upload a new one.
- The request stores selected asset references. During the transition, the selected terrain slot also supplies the existing `dem_id` field for current backend endpoints.
- Tasks persist the resolved input references and display them in task detail so a completed analysis is reproducible.

## Map Picking

1. A spatial field in the dialog has a map-pick control.
2. The user must select the terrain DEM before map picking is available, so coordinates can be checked against its bounds.
3. Activating map pick collapses the dialog into a small map-picking bar that names the active target and provides Cancel.
4. The map changes to a crosshair cursor and shows only neutral draft markers or route previews. It never shows radar volumes, scan planes, GLBs, or analysis results for a draft.
5. One-click fields immediately write the coordinates, exit map-pick mode, and restore the dialog.
6. Route fields keep the map-picking bar open. It provides Undo, Finish, and Cancel; a double click also finishes the route.
7. Start/end and threat fields identify the exact target before entering map-pick mode. The app does not infer which field should change.
8. Out-of-bounds clicks show validation feedback without updating the draft. Escape, Cancel, and model changes exit map-pick mode without discarding existing dialog values.

## Reusable Components

- `ModelRunDialog`: common dialog shell, draft lifecycle, validation, and submit action.
- `ModelInputSlots`: schema-driven asset selectors and upload controls.
- `ModelParameterFields`: schema-driven parameter fields currently represented by the right inspector.
- `MapPickBar`: transient map overlay for point, route, and collection editing.
- `ModelDefinition.inputSlots`: model-level input contract used by both UI validation and task request construction.

## Validation and Testing

- Unit tests cover schema rendering, required asset validation, multiple-file selection, draft persistence, and request construction.
- Map-picking tests cover point commit, route editing, cancellation, and DEM-bound rejection.
- Integration tests verify that selecting a model opens the dialog, no map run control is present, and task submission requires explicit inputs.

## Scope

This change introduces the frontend input-slot contract and preserves the current `dem_id` API bridge. A generic backend asset registry and non-DEM worker inputs are a following phase; their API can adopt the same slot keys without changing the dialog interaction.
