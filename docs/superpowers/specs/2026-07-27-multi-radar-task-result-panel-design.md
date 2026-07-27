# Multi-Radar Task Result Panel Design

## Goal

Make completed multi-radar tasks use the existing right-side task result panel for layer inspection and full artifact downloads. Tighten the task-center history-row layout so terminal tasks do not reserve an empty progress column.

## Scope

- Reuse the existing `TaskResultPanel`; do not add a second drawer, modal, or output panel.
- Extend the selected-task context so it can represent either a registered single-model task or a multi-radar task.
- Add multi-radar actions in the task center:
  - `View layers` selects the task and activates the existing Layers tab.
  - `Download` selects the task and activates the existing Files tab.
- Reuse the current multi-radar aggregate layer adapter for visible union, overlap, blind area, coverage count, stations, and existing cooperative GLB artifacts.
- Reuse `OutputFileList` so every existing output descriptor is available from the Files tab.
- Keep failed rows limited to their log action.

## Layout

Task rows reserve columns for task id, model, summary, optional running progress, status, and actions.

- Pending and running rows render the progress control.
- Finished, partial, and failed rows collapse the progress column.
- The status chip and action group remain adjacent at the right edge.
- Single-model and multi-radar terminal rows share the same status/action alignment.

## Data Flow

1. A multi-radar row action emits an intent (`layers` or `files`) and its task id.
2. The application resolves the task from the already loaded multi-radar history, selects it as the active result context, and loads or reuses its output descriptors.
3. The existing result panel renders multi-radar metrics, aggregate-layer controls, and the shared file list using that context.
4. A layer action loads the aggregate artifacts through the established adapter; a file action keeps the result panel on the Files tab and uses existing download paths.

## Error Handling

- A task with unavailable artifacts still opens the result panel and surfaces its result state.
- Only output descriptors marked `exists` receive a download link.
- A missing optional fusion or cooperative GLB does not block GeoJSON layers or other downloads.

## Tests

- Multi-radar completed rows expose both actions and emit the corresponding intents.
- Selecting either action activates the existing result panel with the requested tab.
- The panel exposes all existing multi-radar output files and aggregate layer controls.
- Terminal task-row layout does not render the progress-column placeholder; running rows still do.
