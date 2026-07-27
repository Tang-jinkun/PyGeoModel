# Deployment-Independent Artifact Delivery Design

## Goal

PyGeoModel must serve task artifacts and TianDiTu tiles correctly whether it is deployed behind Nginx at a subpath, at an origin root, or as separate frontend and backend containers on different origins. A task must never advertise stale output availability merely because an old task record says a file once existed.

The design must apply to current and future task models. It must remove deployment URL construction and artifact filesystem validation from model-specific frontend and backend code.

## Current Failure Modes

- Task records persist `output_files` entries with `exists: true`, while the referenced files can be removed independently.
- Frontend code can fall back from the live output listing to persisted `task.outputs` URLs, causing requests for known-missing files.
- Some frontend loaders fetch `/api/...` or `/outputs/...` directly instead of resolving them through one configured API base.
- `/PyGeoModel`, root-origin, and cross-origin deployments require different URL prefixes, but the current frontend configuration is embedded during the Vite build.
- TianDiTu proxying is implemented in host Nginx, so a deployment without that Nginx configuration loses its map source.
- Output publication moves files individually into the final directory, so a crash can expose a partially published result.
- Output filename, media type, validation, and download behavior are repeated across model-specific modules.

## Architecture

### Shared Artifact Store

Add a backend `ArtifactStore` as the only component that owns task artifact storage. It provides:

- safe task-directory and artifact-path resolution;
- staging directory creation;
- manifest generation and validation;
- atomic publication of a complete artifact directory;
- live artifact listing;
- artifact download resolution;
- task artifact deletion;
- reconciliation of persisted task state against durable files.

Each model registers an `OutputContract` containing its artifact kinds, filenames, media types, labels, and required/optional classification. Model workers produce files into a staging directory and ask `ArtifactStore` to publish them. Model code must not construct public `/outputs/...` URLs or move files into the final directory itself.

Existing model-specific API routes remain stable and call the shared store internally. This limits client breakage while removing duplicated storage behavior. A new model participates by registering an output contract and using the shared publisher.

### Manifest Contract

Every successfully published task directory contains a versioned `artifact-manifest.json` that is the commit record for the directory. It includes:

- manifest schema version;
- task identifier and model identifier;
- creation timestamp;
- one entry per artifact with kind, filename, media type, required flag, byte size, and SHA-256 checksum;
- the output contract version used by the worker.

Publication validates every required artifact before writing the manifest. The completed staging directory is renamed atomically to the final task directory. The task record is marked ready only after that rename succeeds.

Checksums are verified during explicit reconciliation and repair operations. Normal task-list reads verify the manifest, required file presence, and recorded file size to avoid hashing large files on every request.

## Task And Result State

Task computation state remains:

- `pending`
- `running`
- `finished`
- `failed`

Add a separate result availability state:

- `pending`: computation has not published a result;
- `ready`: a valid manifest and every required artifact are present;
- `unavailable`: computation previously finished, but its durable result is incomplete or invalid.

Task list and detail responses derive result availability from the artifact store. Persisted `exists` values are never trusted as current state. Responses include a live `output_files` list; missing files are reported with `exists: false`, `size_bytes: null`, and no loadable download path.

Metrics and diagnostic history remain readable when results are unavailable. The frontend displays the unavailable state and does not request any task artifact.

An explicit rerun operation creates a new task from the saved request and records `rerun_of` on the new task. It never overwrites the historical task or starts expensive computation merely because a user opened task history.

## Artifact API Contract

Artifact loading uses authenticated-capable API download endpoints as the canonical route. Raw static `/outputs/...` paths are not part of the new client contract.

An output descriptor includes metadata plus a deployment-independent `download_path`, for example:

```text
/api/radar/coverage/{task_id}/outputs/{kind}
```

The backend does not include a scheme, host, port, Nginx prefix, or other deployment detail. Existing `url` and `download_url` fields remain temporarily for API compatibility but are deprecated and ignored by the migrated frontend.

Download behavior is:

- `200`: artifact exists and is served with the registered media type;
- `409`: task computation has not finished;
- `410`: task exists and once completed, but the requested result is unavailable;
- `404`: task or artifact kind does not exist;
- `400`: identifier or resolved path is invalid.

## Runtime Deployment Configuration

The frontend image must be portable across deployments without rebuilding. Its container entrypoint generates a small `runtime-config.js` from environment variables. The generator uses JSON serialization rather than raw string substitution, and the response is served with `Cache-Control: no-store`. Frontend code reads this runtime object before creating API clients.

`PYGEOMODEL_API_BASE_URL` is the deployment prefix or backend origin, excluding the `/api` route itself. Supported examples are:

```text
/PyGeoModel
""
http://124.221.208.30:8000
```

One URL resolver joins this base with every route-relative API path. JSON requests, GeoJSON layers, GLB models, binary volume data, downloads, and map tiles all use that resolver. Components and model adapters must not call `fetch` with server-provided paths directly.

The existing build-time `VITE_API_BASE` may remain as a fallback during migration, but runtime configuration takes precedence. Map renderer selection remains a separate build-time setting.

For cross-origin direct deployments, the backend reads `PYGEOMODEL_CORS_ORIGINS`. Configuration parsing rejects malformed API bases and CORS origins at startup with an actionable error.

Nginx is an optional edge proxy. It may expose the frontend and backend under `/PyGeoModel`, but no domain logic or generated resource identifier depends on Nginx.

## TianDiTu Proxy

Move TianDiTu proxy ownership from host Nginx into the backend. The frontend requests a backend route such as:

```text
/api/map/tianditu/{node}/wmts
```

The backend appends `PYGEOMODEL_TIANDITU_TOKEN` server-side and forwards the request with the required upstream headers. It validates the node, layer, matrix set, tile coordinates, and supported WMTS operation so the endpoint cannot become an arbitrary open proxy.

The Token must never appear in frontend bundles, runtime configuration, response bodies, public URLs, or logs. Upstream authentication failures map to a controlled gateway error without returning the Token. Successful tile responses preserve the upstream content type and receive bounded cache headers.

Nginx deployments proxy the normal API prefix and require no TianDiTu-specific locations. Direct backend deployments use the same API route and behavior.

## Frontend Data Flow

When a user selects a task:

1. The frontend reads the task detail and its live result state.
2. If the result is not `ready`, it renders the state and does not start artifact requests.
3. If the result is `ready`, it retrieves the live output descriptor list.
4. It filters to `exists: true` descriptors with a `download_path`.
5. It resolves every download path through the runtime API base.
6. Model adapters load only the artifact kinds declared by the frontend model registry.

The fallback from a missing live descriptor to legacy `task.outputs` is removed. A failed output-list request is an explicit result-loading error, not permission to use stale persisted URLs.

## Failure Handling And Observability

- A worker failure before atomic publication leaves no visible final result and marks computation failed.
- A process crash can leave a hidden staging directory, which startup reconciliation may safely remove after an age threshold.
- A missing or corrupt final result yields `result_state=unavailable` and a structured reason code.
- Direct artifact requests for unavailable results return `410` with the same reason code.
- Rerun is explicit, idempotency-protected, and creates a new task identifier.
- Structured logs record task ID, model ID, manifest version, result-state transition, and artifact kind, but never credentials or full signed upstream URLs.
- Health checks distinguish API process health from optional upstream TianDiTu availability.

## Deletion And Retention

The supported deletion operation owns both the task record and its artifact directory. It reports partial deletion failures and is safe to retry. Automated retention, if added later, must invoke this operation rather than deleting output directories independently.

DEM deletion continues to reject DEMs referenced by task records. Artifact reconciliation does not automatically delete task history or rerun computation.

## Legacy Migration

Provide an administrative reconciliation command with dry-run as its default. It scans all registered task stores and reports:

- ready results;
- missing directories;
- incomplete files;
- corrupt or legacy manifests;
- task records without a reusable request or DEM.

An explicit repair mode can rebuild selected tasks when their saved request and DEM are available. The current seven radar task records with missing output directories are repaired once as deployment data migration. This repair is not called from normal list, detail, or download requests.

Legacy complete directories without an artifact manifest may be validated against their model contract and upgraded by writing a manifest. Legacy incomplete directories become unavailable.

## Testing And Verification

Backend tests cover:

- model output-contract registration;
- complete atomic publication;
- worker failure before publication;
- required and optional artifacts;
- manifest size and checksum validation;
- stale persisted `exists: true` values;
- result-state derivation on list and detail responses;
- `410` for unavailable results;
- safe rerun creation and `rerun_of` linkage;
- path traversal rejection;
- idempotent task and artifact deletion;
- reconciliation dry-run and explicit repair selection;
- TianDiTu parameter allowlisting, Token secrecy, upstream failures, and response media types.

Frontend tests cover:

- runtime API base at origin root;
- an Nginx subpath;
- an absolute cross-origin backend URL;
- runtime configuration precedence over build fallback;
- output loading only for `ready` tasks and live `exists: true` descriptors;
- no legacy URL fallback;
- GeoJSON, GLB, binary, and tile requests using the same URL resolver;
- unavailable result presentation and explicit rerun behavior.

Deployment verification runs two integration configurations:

1. Nginx exposes the application at `/PyGeoModel`.
2. The frontend and backend are accessed directly on separate ports with configured CORS.

Both configurations must create a new task, wait for atomic publication, switch between task-history entries without 404 requests, load every declared artifact, and retrieve TianDiTu tiles without exposing the Token.

## Rollout

1. Introduce shared artifact contracts and live result-state derivation behind existing model APIs.
2. Add runtime frontend configuration and migrate all API and artifact URL resolution.
3. Move TianDiTu proxying into the backend and switch frontend tile URLs.
4. Migrate each worker to atomic `ArtifactStore` publication.
5. Add explicit rerun and reconciliation commands.
6. Reconcile and repair legacy task data.
7. Remove frontend legacy URL fallback, then deprecate raw `/outputs` routes and old URL fields after compatibility monitoring.

## Non-Goals

- Introducing MinIO, COS, S3, or another object store in this change.
- Automatically recomputing results when users open task history.
- Changing map renderer selection or replacing TianDiTu as the map source.
- Adding authentication or authorization, while keeping artifact API routes compatible with future authentication.
- Implementing automatic retention policies.
