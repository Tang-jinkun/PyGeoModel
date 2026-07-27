# Configurable Map Rendering Engine Design

## Goal

PyGeoModel must use MapLibre GL by default while retaining an explicit, build-time switch to Mapbox GL. Both engines must render the existing TianDiTu raster sources through the same-origin Nginx proxy. Selecting an engine must not change the map source.

## Configuration Contract

- `VITE_MAP_ENGINE` accepts `maplibre` or `mapbox` and defaults to `maplibre`.
- `VITE_MAPBOX_ACCESS_TOKEN` is optional in MapLibre mode and required in Mapbox mode.
- Any unsupported `VITE_MAP_ENGINE` value is a configuration error.
- Explicit Mapbox mode without a non-empty access token is a configuration error. It must not silently fall back to MapLibre.
- Configuration is resolved during the Vite production build, matching the existing Docker build-argument model.

## Architecture

Add one frontend map-engine adapter as the only application-level import boundary for the renderer. The adapter selects `maplibre-gl` by default or `mapbox-gl` when configured, exports the selected engine, and exposes renderer-compatible TypeScript types needed by the application.

Application components, composables, map layers, and tests will import through this adapter rather than directly from `mapbox-gl`. The existing TianDiTu style factory remains renderer-neutral and continues to produce same-origin `vec_w` and `cva_w` raster tile URLs.

Both rendering packages remain build dependencies so one source tree can produce either deployment. Vite tree shaking may reduce unused code, but bundle-size optimization is outside this change.

## Runtime Behavior

In the default configuration, the adapter initializes MapLibre without a token and no Mapbox authentication request occurs. The TianDiTu Nginx proxy continues to append the server-side TianDiTu token and normalize the upstream user agent.

When `VITE_MAP_ENGINE=mapbox`, the adapter validates `VITE_MAPBOX_ACCESS_TOKEN`, assigns it to Mapbox GL, and exposes Mapbox GL as the selected engine. TianDiTu remains the active style and tile source; the Mapbox token only satisfies the Mapbox GL renderer's authentication requirement.

Invalid configuration fails before map construction with an actionable error naming the missing or invalid environment setting. It does not create a partially initialized map.

## Container Integration

The frontend Dockerfile accepts `VITE_MAP_ENGINE` with a default of `maplibre` and continues to accept the optional Mapbox token. Docker Compose forwards both build arguments, defaulting the engine to `maplibre`. The example environment file documents both modes without containing a real token.

Changing either setting requires rebuilding the frontend image because Vite embeds public environment values at build time.

## Compatibility Scope

Existing map interactions, TianDiTu raster layers, DEM terrain, GeoJSON layers, custom Three.js layers, and public component events must retain their current behavior. The migration changes the renderer selection boundary, not domain behavior or map styling.

The public entry point and Nginx routing remain unchanged:

- Application: `/PyGeoModel/`
- TianDiTu proxy: `/PyGeoModel/tianditu/...`

## Testing And Verification

Unit tests will cover:

- Missing `VITE_MAP_ENGINE` selects MapLibre.
- `maplibre` selects MapLibre without requiring a token.
- `mapbox` with a token selects Mapbox and applies the token.
- `mapbox` without a token fails with a clear configuration error.
- Unsupported engine values fail with a clear configuration error.
- TianDiTu style URLs remain same-origin, token-free in the browser, and versioned for cache invalidation.

The implementation gate requires the full frontend test suite and production build to pass in the default MapLibre mode. Container verification must confirm that the public bundle contains the new engine configuration, TianDiTu tiles return HTTP 200 through all configured upstream nodes, and the browser no longer emits a Mapbox access-token error in default mode.

Mapbox-mode build verification may validate configuration and compilation without publishing or exposing the real token in logs.

## Non-Goals

- Replacing TianDiTu with Mapbox-hosted styles or tiles.
- Storing a real Mapbox token in Git.
- Runtime switching without rebuilding the frontend.
- Refactoring unrelated map features or visual design.
