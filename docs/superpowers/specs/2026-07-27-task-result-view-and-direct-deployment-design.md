# Task Result View and Direct Deployment Design

## Goal

Restore a usable task result view in the current GIS workbench and make both the
Nginx `/PyGeoModel/` deployment and direct frontend/backend ports resolve API
requests correctly.

## Workbench Result View

The active workbench regains an inspector region beside the map. Selecting any
task switches the inspector to result mode. Selecting a model opens the existing
run dialog and returns the inspector to its empty/parameter state.

The result inspector will be restyled to match the current workbench: white
surface, subtle gray separators, compact 12-14px labels, restrained typography,
square 8px controls, and the existing blue/green/red status colors. It will not
reuse the legacy page heading or pill-heavy result treatment.

The inspector presents:

- model name, task status, and task message;
- the model's declared metrics in a compact definition list;
- available output files using canonical backend `download_path` values;
- a clear unavailable-result state when `result_state` is `unavailable`.

Selecting a finished task also opens the dock's Layers tab. Existing map result
loading remains responsible for GeoJSON and GLB rendering.

## Layout

`GisWorkbenchShell` adds an inspector column between the map and the existing
dock boundary on desktop. The map remains the flexible primary region and the
inspector has a stable, constrained width. On narrow screens the inspector is an
overlay/detail surface so it does not make the map unusably narrow.

`WorkbenchInspector` owns only result presentation. It receives the selected
task and live metrics/output descriptors already loaded by `useMapWorkspace`,
so the UI does not make a second independent result request.

## Deployment Modes

Compose no longer silently assumes the Nginx `/PyGeoModel` prefix. The default
direct-port configuration points the frontend at the backend's published direct
origin. Nginx subpath deployments explicitly set
`PYGEOMODEL_API_BASE_URL=/PyGeoModel` as documented.

The three supported modes remain:

- Nginx subpath: explicit `/PyGeoModel` API base;
- direct ports: explicit backend origin and matching CORS origin;
- same-origin root proxy: empty API base.

Deployment verification checks that the configured API endpoint returns JSON,
not the frontend SPA fallback HTML.

## Error Handling

Result API failures retain the selected task and show unavailable/loading errors
without clearing task history. Output links are rendered only when `exists` is
true and a canonical `download_path` is present.

## Tests

Component tests cover inspector styling structure, model metric labels, output
links, unavailable state, selection-driven inspector mode, and automatic Layers
tab selection. Shell tests cover desktop and narrow inspector layout contracts.
Deployment tests cover Compose defaults and both direct-port and Nginx runtime
API bases. Existing frontend and deployment verification suites must continue to
pass.
