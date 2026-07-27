# Vue GIS Workbench Redesign Design

## Goal

Replace the current PyGeoModel front-end workspace composition with Vue
components that visually and behaviorally match
`PyGeoModel-前端重设计/gis-workbench.html`. The static HTML is the source of
truth for layout, visual tokens, responsive behavior, and interaction
affordances. The replacement must preserve the production model, map, DEM,
task, result, and 3D rendering behavior already present in the application.

The redesign covers every registered analysis model, including radar, UAV,
watchpost, artillery, mobility, and air-corridor workflows. It is not a
radar-only skin.

## Visual Contract

The Vue workbench reproduces the static design's six persistent regions:

1. top bar;
2. left dock with Model Library, Layers, and Data tabs;
3. central map stage;
4. right inspector;
5. bottom task center;
6. status bar.

It uses the same light visual language, spacing scale, panel borders, 12px
panel radius, typography, compact controls, collapse behavior, and responsive
grid. The desktop frame follows the source's three-column grid. At reduced
widths, the dock, inspector, and task center follow the source's responsive
stacking/collapsing rules rather than introducing a separate application
layout.

The map stage is deliberately not replaced by the static page's canvas demo.
It hosts the current interactive map, terrain, result overlays, GLB assets,
radar platforms, and scan animations inside the redesigned visual chrome.

## Component Structure

`App.vue` becomes a thin coordinator for a new workbench shell. The shell is
split by screen region rather than duplicating the domain components:

- `GisWorkbenchShell`: owns responsive grid state and the active inspector
  mode.
- `WorkbenchTopbar`: project identity, DEM summary, service state, and global
  search trigger.
- `WorkbenchDock`: Model Library, Layers, and Data tabs.
- `WorkbenchMapStage`: the existing map workspace plus the source-design
  toolbar, basemap switch, legend, and scale presentation.
- `WorkbenchInspector`: swaps between model parameters and a selected task's
  result detail while keeping one right-side panel frame.
- `WorkbenchTaskCenter`: running, history, and log tabs with collapse state.
- `WorkbenchStatusbar`: cursor coordinate, elevation, CRS, active DEM, and
  task polling state.

Existing business components, composables, API clients, model schemas, map
layer adapters, and GLB loaders remain the source of domain behavior. Small
adapter components may translate their current props/events into the new
screen-region contracts, but calculations and task semantics are not copied
into the new shell.

## Interaction Model

### Model and Parameter Flow

Selecting a model from Model Library activates the parameter mode in the right
inspector. Each model retains its own real schema and controls; the shared
inspector supplies only the visual grouping, title, close action, draft action,
and run action. Map-pick and route-pick interactions continue to operate
against the real map.

### Task and Result Flow

The task center is a compact queue, not an expanded results table. Each row
shows task ID, model, concise execution context, status, completion time, and
at most one model-appropriate primary metric. Examples include visible area,
route distance, or mobility time saving.

Selecting a completed task has three coordinated effects:

1. it makes that task the active map result and focuses its bounds when
   available;
2. it selects or reveals that task's result group in the Layers tab;
3. it switches the right inspector to result-detail mode.

The result detail uses the same inspector frame and section styling as model
parameters. It contains complete metrics, warnings, artifact/download links,
and task-specific actions. A back action returns to the selected model's
parameters. The task center itself never expands into a dense metrics table.

Running tasks show real progress and cancellation where supported. Failed
tasks show a concise error and offer log viewing/retry when those actions are
available. The Logs tab displays the current task and worker messages without
inventing client-side fake progress.

### Layer Flow

The Layers tab is the single control surface for all map-visible objects:

- 2D coverage, terrain obstruction, boundary, raster, and vector outputs;
- radar platform GLBs, radar scene GLBs, scan planes, station markers, and
  target markers;
- cooperative radar intersection GLB and supporting per-station layers;
- base terrain, contours, imagery, and other basemap layers.

Layer entries are grouped by task and support visibility, opacity where the
render type permits it, focus, and removal through existing layer adapters.
GLB assets are therefore treated as regular task-result layers, not special
controls embedded in result details.

### Cooperative Radar

For two-to-five-station cooperative tasks, each station's platform, full
single-radar terrain-aware shell, scan plane, and marker is an independently
controllable child layer. The shared gold `coverage_count >= 2` intersection
is a separate sibling layer. Selecting the cooperative task focuses the full
scene and presents cooperative metrics in the result inspector, while the
Layers tab remains responsible for all visual toggles.

## State Boundaries

- Existing model workspace state remains authoritative for selected model and
  parameter drafts.
- Existing DEM manager remains authoritative for datasets and active DEM.
- Existing map workspace remains authoritative for map readiness, map tools,
  result layer registration, scene assets, and camera focus.
- Existing task manager remains authoritative for task lifecycle, polling,
  history, logs, artifacts, and failures.
- The new shell owns only presentation state: active left tab, task-center
  tab/collapse, selected result task, and inspector mode.

The selected result task is a view-level reference to a task-manager task. It
does not duplicate artifacts, map layers, or calculation results.

## Responsive and Accessibility Behavior

The implementation validates the source viewport matrix: 360x800, 390x844,
430x932, 600x960, 820x1180, 1024x768, 1366x768, 1440x900, and 1920x1080.
Panels preserve stable hit targets and avoid clipped labels. Icon-only controls
retain accessible labels and tooltips. Dock tabs, task tabs, layer toggles,
collapse controls, and inspector transitions remain keyboard-operable.

## Verification

Automated coverage includes:

- shell state transitions between model parameters and task result detail;
- model-library selection for every registered model;
- compact task-row metrics and task selection behavior;
- layer grouping and visibility handling for 2D outputs and GLB assets;
- cooperative radar station/intersection layer registration;
- task failure, log, retry, and download affordances where supported.

Manual verification includes:

- visual comparison against the static source at every required viewport;
- a completed single-radar task with coverage, platform GLB, scene GLB, and
  scan plane controls;
- a completed two-to-five-radar cooperative task with all station scenes
  and the gold intersection layer;
- one workflow for each remaining registered model;
- DEM selection/upload, task progress, completed task inspection, task
  failure, layer focus, and map tools.

## Non-Goals

- Rewriting backend analysis APIs or task workers.
- Replacing the current interactive/3D map with the static canvas mock.
- Adding a separate result dashboard or a second persistent right-side panel.
- Moving map layer controls into parameter or result detail views.
