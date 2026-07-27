# Multi-Radar Output Path Design

## Problem

Multi-radar aggregate rendering reads canonical `download_path` values from the
live outputs endpoint. `App.vue` currently resolves those paths with
`resolveApiUrl`, then passes the resolved deployment URL to `requestGeoJson`.
`requestGeoJson` resolves API paths itself and correctly rejects anything that
does not begin with `/api/`, so subpath deployments fail with `API paths must
begin with /api/`.

## Design

Keep the global API path validation unchanged. Add a small multi-radar output
descriptor selector that returns the canonical backend `download_path` without
deployment resolution. Aggregate GeoJSON loading passes that path directly to
`requestGeoJson`, which remains the single owner of runtime API base resolution.

GLB loading is unchanged: scene descriptors continue through
`useMapWorkspace`, whose loader resolves their canonical paths at its own fetch
boundary.

## Tests

A focused unit test supplies a live descriptor with a canonical `/api/...`
download path and asserts that the selector returns that exact path. Existing
multi-radar API, App, HTTP resolution, frontend build, and deployment endpoint
tests must remain green.
