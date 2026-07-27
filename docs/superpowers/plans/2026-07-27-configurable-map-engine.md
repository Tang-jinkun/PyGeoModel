# Configurable Map Rendering Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make MapLibre GL the default renderer while allowing an explicit build-time switch to Mapbox GL with a required access token, without changing the TianDiTu map source.

**Architecture:** A local `mapEngine` adapter owns renderer selection and is the only runtime import boundary for MapLibre GL and Mapbox GL. A companion type-export module keeps renderer-compatible types centralized, while all map data continues to flow through the existing TianDiTu style and same-origin Nginx proxy.

**Tech Stack:** Vue 3.5, TypeScript 5.7, Vite 6, Vitest 4, MapLibre GL 5.7.3, Mapbox GL 3.27.0, Docker Compose, Nginx.

## Global Constraints

- `VITE_MAP_ENGINE` accepts exactly `maplibre` or `mapbox` and defaults to `maplibre`.
- `VITE_MAPBOX_ACCESS_TOKEN` is optional in MapLibre mode and required in Mapbox mode.
- Unsupported engine values and explicit Mapbox mode without a non-empty token fail before map construction.
- Both renderer modes continue to use the TianDiTu `vec_w` and `cva_w` raster sources through `/PyGeoModel/tianditu/...`.
- The default deployment must produce no Mapbox access-token error in the browser.
- No real Mapbox or TianDiTu token may be committed or printed in command output.
- Engine selection is embedded at Vite build time; changing it requires rebuilding the frontend image.
- Existing map interactions, DEM terrain, GeoJSON layers, custom Three.js layers, events, public URL, and Nginx routes remain unchanged.
- The worktree already contains unrelated and prerequisite uncommitted changes. Every commit must stage only the explicit files listed in that task.

## File Structure

- Create `frontend/src/map/mapEngine.ts`: validate build configuration and expose the selected runtime renderer.
- Create `frontend/src/map/mapEngine.test.ts`: cover default, explicit MapLibre, valid Mapbox, missing-token, and unsupported-engine behavior.
- Create `frontend/src/map/mapEngineTypes.ts`: re-export the renderer-compatible Mapbox type surface used by application code.
- Delete `frontend/src/map/mapboxAccessToken.ts`: superseded by centralized engine selection.
- Delete `frontend/src/map/mapboxAccessToken.test.ts`: superseded by `mapEngine.test.ts`.
- Modify `frontend/package.json` and `frontend/package-lock.json`: add exact `maplibre-gl` dependency.
- Modify renderer consumers under `frontend/src`: route runtime constructors and static helpers through `mapEngine`, and types through `mapEngineTypes`.
- Modify `frontend/src/main.ts`: load CSS for both supported renderer class-name families.
- Modify `frontend/Dockerfile`, `docker-compose.yml`, and `frontend/.env.example`: expose the build-time engine contract.

---

### Task 0: Preserve The Verified TianDiTu Proxy Baseline

**Files:**
- Modify: `frontend/src/map/tiandituStyle.ts`
- Modify: `frontend/src/map/tiandituStyle.test.ts`
- Modify: `frontend/src/components/map/MapWorkspace.vue`
- Modify: `frontend/Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `frontend/.env.example`

**Interfaces:**
- Consumes: the already configured host Nginx routes under `/PyGeoModel/tianditu/...`.
- Produces: a committed browser-token-free TianDiTu proxy baseline on which the renderer migration can build without overlapping dirty hunks.

- [ ] **Step 1: Review the existing prerequisite diff**

Run:

```bash
cd /home/PyGeoModel
git diff -- frontend/src/map/tiandituStyle.ts \
  frontend/src/map/tiandituStyle.test.ts \
  frontend/src/components/map/MapWorkspace.vue \
  frontend/Dockerfile docker-compose.yml frontend/.env.example
```

Expected: TianDiTu URLs use the same-origin proxy and `PROXY_VERSION=2`; browser-side TianDiTu token plumbing is removed; no real token appears in the diff.

- [ ] **Step 2: Re-run the proxy regression test and production build**

Run:

```bash
cd /home/PyGeoModel/frontend
npm test -- --run src/map/tiandituStyle.test.ts src/components/map/MapWorkspace.test.ts
npm run build
```

Expected: focused tests pass and the production build exits 0.

- [ ] **Step 3: Commit only the verified prerequisite changes**

Run:

```bash
cd /home/PyGeoModel
git add frontend/src/map/tiandituStyle.ts \
  frontend/src/map/tiandituStyle.test.ts \
  frontend/src/components/map/MapWorkspace.vue \
  frontend/Dockerfile docker-compose.yml frontend/.env.example
git diff --cached --check
git commit -m "fix(frontend): proxy TianDiTu tiles through nginx"
```

Expected: the six prerequisite files are committed and the renderer tasks start without overlapping uncommitted changes.

---

### Task 1: Engine Selection Adapter

**Files:**
- Create: `frontend/src/map/mapEngine.test.ts`
- Create: `frontend/src/map/mapEngine.ts`
- Create: `frontend/src/map/mapEngineTypes.ts`
- Delete: `frontend/src/map/mapboxAccessToken.ts`
- Delete: `frontend/src/map/mapboxAccessToken.test.ts`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

**Interfaces:**
- Consumes: Vite values `import.meta.env.VITE_MAP_ENGINE` and `import.meta.env.VITE_MAPBOX_ACCESS_TOKEN`.
- Produces: `selectMapEngine(config, engines): MapEngineModule`, default export `mapEngine`, and named renderer-compatible types from `mapEngineTypes.ts`.

- [ ] **Step 1: Write the failing selector tests**

Create `frontend/src/map/mapEngine.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { selectMapEngine, type MapEngineModule } from "./mapEngine";

function fakeEngine() {
  return { accessToken: "" } as unknown as MapEngineModule;
}

describe("selectMapEngine", () => {
  it("selects MapLibre when the engine setting is missing", () => {
    const maplibre = fakeEngine();
    const mapbox = fakeEngine();

    expect(selectMapEngine({}, { maplibre, mapbox })).toBe(maplibre);
  });

  it("selects MapLibre explicitly without requiring a token", () => {
    const maplibre = fakeEngine();
    const mapbox = fakeEngine();

    expect(selectMapEngine({ name: "maplibre" }, { maplibre, mapbox })).toBe(maplibre);
  });

  it("selects Mapbox and applies its token", () => {
    const maplibre = fakeEngine();
    const mapbox = fakeEngine();

    expect(selectMapEngine(
      { name: "mapbox", mapboxAccessToken: "pk.test-mapbox-token" },
      { maplibre, mapbox }
    )).toBe(mapbox);
    expect(mapbox.accessToken).toBe("pk.test-mapbox-token");
  });

  it("rejects Mapbox mode without a token", () => {
    expect(() => selectMapEngine(
      { name: "mapbox", mapboxAccessToken: "  " },
      { maplibre: fakeEngine(), mapbox: fakeEngine() }
    )).toThrow("VITE_MAPBOX_ACCESS_TOKEN is required when VITE_MAP_ENGINE=mapbox");
  });

  it("rejects unsupported engine values", () => {
    expect(() => selectMapEngine(
      { name: "leaflet" },
      { maplibre: fakeEngine(), mapbox: fakeEngine() }
    )).toThrow('VITE_MAP_ENGINE must be "maplibre" or "mapbox"');
  });
});
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
cd /home/PyGeoModel/frontend
npm test -- --run src/map/mapEngine.test.ts
```

Expected: FAIL because `./mapEngine` does not exist.

- [ ] **Step 3: Install MapLibre and implement the selector**

Run:

```bash
cd /home/PyGeoModel/frontend
npm install --save-exact maplibre-gl@5.7.3
```

Create `frontend/src/map/mapEngine.ts`:

```ts
import mapboxEngine from "mapbox-gl";
import maplibreEngine from "maplibre-gl";

export type MapEngineModule = typeof mapboxEngine;

export interface MapEngineConfig {
  name?: string;
  mapboxAccessToken?: string;
}

interface MapEngines {
  maplibre: MapEngineModule;
  mapbox: MapEngineModule;
}

export function selectMapEngine(config: MapEngineConfig, engines: MapEngines): MapEngineModule {
  const name = config.name?.trim() || "maplibre";
  if (name === "maplibre") return engines.maplibre;
  if (name !== "mapbox") {
    throw new Error('VITE_MAP_ENGINE must be "maplibre" or "mapbox"');
  }

  const token = config.mapboxAccessToken?.trim();
  if (!token) {
    throw new Error("VITE_MAPBOX_ACCESS_TOKEN is required when VITE_MAP_ENGINE=mapbox");
  }
  engines.mapbox.accessToken = token;
  return engines.mapbox;
}

const mapEngine = selectMapEngine(
  {
    name: import.meta.env.VITE_MAP_ENGINE,
    mapboxAccessToken: import.meta.env.VITE_MAPBOX_ACCESS_TOKEN
  },
  {
    maplibre: maplibreEngine as unknown as MapEngineModule,
    mapbox: mapboxEngine
  }
);

export default mapEngine;
```

Create `frontend/src/map/mapEngineTypes.ts`:

```ts
export type {
  CustomLayerInterface,
  FillLayerSpecification,
  FitBoundsOptions,
  GeoJSONSource,
  LayerSpecification,
  LineLayerSpecification,
  LngLatBounds,
  Map,
  MapMouseEvent,
  MercatorCoordinate,
  StyleSpecification
} from "mapbox-gl";
```

Delete the superseded helper and test with `apply_patch`:

```diff
*** Delete File: frontend/src/map/mapboxAccessToken.ts
*** Delete File: frontend/src/map/mapboxAccessToken.test.ts
```

- [ ] **Step 4: Run the focused selector test and verify GREEN**

Run:

```bash
cd /home/PyGeoModel/frontend
npm test -- --run src/map/mapEngine.test.ts
```

Expected: 1 test file and 5 tests pass.

- [ ] **Step 5: Commit only the adapter deliverable**

Run:

```bash
cd /home/PyGeoModel
git add frontend/package.json frontend/package-lock.json \
  frontend/src/map/mapEngine.ts frontend/src/map/mapEngine.test.ts \
  frontend/src/map/mapEngineTypes.ts \
  frontend/src/map/mapboxAccessToken.ts frontend/src/map/mapboxAccessToken.test.ts
git diff --cached --check
git commit -m "feat(frontend): add configurable map engine"
```

Expected: commit contains the selector, type boundary, dependency update, and removal of only the superseded helper.

---

### Task 2: Route Map Runtime Through The Adapter

**Files:**
- Modify: `frontend/src/components/map/MapWorkspace.vue`
- Modify: `frontend/src/components/map/MapWorkspace.test.ts`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/App.test.ts`
- Modify: `frontend/src/composables/useMapWorkspace.ts`
- Modify: `frontend/src/map/clippedVolumeLayer.ts`
- Modify: `frontend/src/map/mapLayers.ts`
- Modify: `frontend/src/map/modelLayers.ts`
- Modify: `frontend/src/map/multiRadarLayerAdapter.ts`
- Modify: `frontend/src/map/radarVolumeLayer.ts`
- Modify: `frontend/src/map/sceneGlbGeoReference.ts`
- Modify: `frontend/src/map/sceneGlbLayer.ts`
- Modify: `frontend/src/map/voxelLayer.ts`
- Modify: `frontend/src/main.ts`

**Interfaces:**
- Consumes: default `mapEngine` and the named types exported by Task 1.
- Produces: all renderer constructors and value helpers come from the configured engine; business APIs and emitted Vue event types remain unchanged.

- [ ] **Step 1: Change the component test to mock the adapter and verify RED**

In `frontend/src/components/map/MapWorkspace.test.ts`, replace the Mapbox type import and module mock with:

```ts
import type { StyleSpecification } from "../../map/mapEngineTypes";

vi.mock("../../map/mapEngine", () => ({
  default: {
    Map: class {
      constructor(options: unknown) {
        const map = new FakeMap(options);
        mapHarness.instances.push(map);
        mapHarness.constructor(options);
        return map;
      }
    },
    NavigationControl: class {}
  }
}));
```

Change the local annotation from `mapboxgl.StyleSpecification` to `StyleSpecification`.

Run:

```bash
cd /home/PyGeoModel/frontend
npm test -- --run src/components/map/MapWorkspace.test.ts
```

Expected: FAIL because `MapWorkspace.vue` still constructs the directly imported Mapbox renderer instead of the mocked adapter.

- [ ] **Step 2: Migrate `MapWorkspace.vue` to the selected runtime**

Replace the renderer imports and type usage with this boundary:

```ts
import { onBeforeUnmount, onMounted, ref, shallowRef, toRaw, watch } from "vue";

import mapEngine from "../../map/mapEngine";
import type { Map, MapMouseEvent, StyleSpecification } from "../../map/mapEngineTypes";
```

Remove `applyMapboxAccessToken(...)` and its import. Apply these exact substitutions in the component:

```text
mapboxgl.StyleSpecification -> StyleSpecification
mapboxgl.MapMouseEvent      -> MapMouseEvent
mapboxgl.Map                -> Map
new mapboxgl.Map            -> new mapEngine.Map
new mapboxgl.NavigationControl -> new mapEngine.NavigationControl
```

The default style remains:

```ts
mapStyle: (): StyleSpecification => createTiandituStyle() as StyleSpecification,
```

Run:

```bash
cd /home/PyGeoModel/frontend
npm test -- --run src/components/map/MapWorkspace.test.ts
```

Expected: all `MapWorkspace` tests pass through the adapter mock.

- [ ] **Step 3: Migrate runtime map modules and centralized types**

For modules that call renderer values, import the configured runtime and the exact named types they use:

```ts
import mapEngine from "./mapEngine";
import type {
  CustomLayerInterface,
  FillLayerSpecification,
  FitBoundsOptions,
  GeoJSONSource,
  LayerSpecification,
  LineLayerSpecification,
  LngLatBounds,
  Map,
  MercatorCoordinate
} from "./mapEngineTypes";
```

Only include names actually used by each file. Apply these value substitutions:

```text
mapboxgl.MercatorCoordinate.fromLngLat -> mapEngine.MercatorCoordinate.fromLngLat
new mapboxgl.LngLatBounds              -> new mapEngine.LngLatBounds
```

Apply these type substitutions wherever present:

```text
mapboxgl.CustomLayerInterface   -> CustomLayerInterface
mapboxgl.FillLayerSpecification -> FillLayerSpecification
mapboxgl.FitBoundsOptions       -> FitBoundsOptions
mapboxgl.GeoJSONSource          -> GeoJSONSource
mapboxgl.LayerSpecification     -> LayerSpecification
mapboxgl.LineLayerSpecification -> LineLayerSpecification
mapboxgl.LngLatBounds           -> LngLatBounds
mapboxgl.Map                    -> Map
mapboxgl.MercatorCoordinate     -> MercatorCoordinate
```

Apply the migration to these runtime files:

```text
frontend/src/map/clippedVolumeLayer.ts
frontend/src/map/mapLayers.ts
frontend/src/map/radarVolumeLayer.ts
frontend/src/map/sceneGlbGeoReference.ts
frontend/src/map/sceneGlbLayer.ts
frontend/src/map/voxelLayer.ts
```

Apply type-only imports from `./mapEngineTypes` to:

```text
frontend/src/map/modelLayers.ts
frontend/src/map/multiRadarLayerAdapter.ts
```

Apply type-only imports from `../map/mapEngineTypes` to:

```text
frontend/src/composables/useMapWorkspace.ts
```

Apply type-only imports from `./map/mapEngineTypes` to `frontend/src/App.vue`, including `Map`, `MapMouseEvent`, and `GeoJSONSource` as required by that file.

Verify no application TypeScript or Vue file directly imports the package:

```bash
cd /home/PyGeoModel
rg -n 'from "mapbox-gl"' frontend/src --glob '!map/mapEngine.ts' --glob '!map/mapEngineTypes.ts'
```

Expected: no output.

- [ ] **Step 4: Route tests and CSS through the compatibility boundary**

In `frontend/src/App.test.ts`, replace the package mock with:

```ts
vi.mock("./map/mapEngine", () => ({
  default: { Map: class {}, NavigationControl: class {} }
}));
```

In `frontend/src/main.ts`, load both supported renderer CSS files before the application styles:

```ts
import "maplibre-gl/dist/maplibre-gl.css";
import "mapbox-gl/dist/mapbox-gl.css";
```

Run:

```bash
cd /home/PyGeoModel/frontend
npm test
npm run build
```

Expected: 55 test files with at least 266 tests pass, and the default MapLibre production build exits 0.

- [ ] **Step 5: Commit only the runtime migration**

Run:

```bash
cd /home/PyGeoModel
git add frontend/src/App.vue frontend/src/App.test.ts \
  frontend/src/components/map/MapWorkspace.vue frontend/src/components/map/MapWorkspace.test.ts \
  frontend/src/composables/useMapWorkspace.ts frontend/src/main.ts \
  frontend/src/map/clippedVolumeLayer.ts frontend/src/map/mapLayers.ts \
  frontend/src/map/modelLayers.ts frontend/src/map/multiRadarLayerAdapter.ts \
  frontend/src/map/radarVolumeLayer.ts frontend/src/map/sceneGlbGeoReference.ts \
  frontend/src/map/sceneGlbLayer.ts frontend/src/map/voxelLayer.ts
git diff --cached --check
git commit -m "refactor(frontend): use selected map renderer"
```

Expected: commit contains only renderer import/type migration and CSS compatibility changes.

---

### Task 3: Build-Time Container Configuration

**Files:**
- Modify: `frontend/Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `frontend/.env.example`

**Interfaces:**
- Consumes: host or CI variables `VITE_MAP_ENGINE` and optional `VITE_MAPBOX_ACCESS_TOKEN`.
- Produces: Vite build environment with a default renderer of `maplibre` and explicit Mapbox opt-in.

- [ ] **Step 1: Verify the current Compose contract is missing the engine switch**

Run:

```bash
cd /home/PyGeoModel
test -z "$(docker compose config 2>/dev/null | rg 'VITE_MAP_ENGINE')"
```

Expected: exit 0, proving the switch is not yet propagated.

- [ ] **Step 2: Add the Docker and environment contract**

Add to the frontend build arguments in `frontend/Dockerfile`:

```dockerfile
ARG VITE_MAP_ENGINE=maplibre
ARG VITE_MAPBOX_ACCESS_TOKEN

ENV VITE_MAP_ENGINE=${VITE_MAP_ENGINE}
ENV VITE_MAPBOX_ACCESS_TOKEN=${VITE_MAPBOX_ACCESS_TOKEN}
```

The existing API base, base path, and proxy target arguments remain unchanged. Replace the existing build command with a build-time configuration gate:

```dockerfile
RUN case "${VITE_MAP_ENGINE}" in \
      maplibre) ;; \
      mapbox) test -n "${VITE_MAPBOX_ACCESS_TOKEN}" || \
        { echo "VITE_MAPBOX_ACCESS_TOKEN is required when VITE_MAP_ENGINE=mapbox" >&2; exit 1; } ;; \
      *) echo 'VITE_MAP_ENGINE must be "maplibre" or "mapbox"' >&2; exit 1 ;; \
    esac \
    && npm run build
```

Set the frontend build arguments in `docker-compose.yml` to:

```yaml
args:
  NPM_REGISTRY: https://mirrors.cloud.tencent.com/npm/
  VITE_MAP_ENGINE: ${VITE_MAP_ENGINE:-maplibre}
  VITE_MAPBOX_ACCESS_TOKEN: ${VITE_MAPBOX_ACCESS_TOKEN:-}
```

Set `frontend/.env.example` to document the public build configuration without a real credential:

```dotenv
VITE_API_BASE=
VITE_MAP_ENGINE=maplibre
VITE_MAPBOX_ACCESS_TOKEN=
```

- [ ] **Step 3: Verify both configuration paths**

Run:

```bash
cd /home/PyGeoModel
docker compose config | rg -A3 'VITE_MAP_ENGINE|VITE_MAPBOX_ACCESS_TOKEN'
VITE_MAP_ENGINE=mapbox VITE_MAPBOX_ACCESS_TOKEN=pk.test-build-token \
  docker compose config | rg -A3 'VITE_MAP_ENGINE|VITE_MAPBOX_ACCESS_TOKEN'
```

Expected: the first configuration resolves `VITE_MAP_ENGINE: maplibre`; the second resolves `VITE_MAP_ENGINE: mapbox`. Do not use or print a real token in this check.

Run the explicit container configuration tests:

```bash
cd /home/PyGeoModel
VITE_MAP_ENGINE=mapbox VITE_MAPBOX_ACCESS_TOKEN= docker compose build frontend
```

Expected: image build exits non-zero at the Dockerfile configuration gate with `VITE_MAPBOX_ACCESS_TOKEN is required when VITE_MAP_ENGINE=mapbox`.

Then run:

```bash
cd /home/PyGeoModel
VITE_MAP_ENGINE=mapbox VITE_MAPBOX_ACCESS_TOKEN=pk.test-build-token docker compose build frontend
```

Expected: build exits 0, proving explicit Mapbox mode compiles when configured.

- [ ] **Step 4: Commit only container configuration**

Run:

```bash
cd /home/PyGeoModel
git add frontend/Dockerfile docker-compose.yml frontend/.env.example
git diff --cached --check
git commit -m "build: configure frontend map engine"
```

Expected: commit contains only the build-time engine contract.

---

### Task 4: Default MapLibre Deployment And Public Verification

**Files:**
- Verify only; no source files should change.

**Interfaces:**
- Consumes: the default Compose configuration, the host Nginx TianDiTu proxy, and public URL `http://124.221.208.30/PyGeoModel/`.
- Produces: a running default MapLibre deployment with TianDiTu tiles and no Mapbox token requirement.

- [ ] **Step 1: Run the complete frontend verification gate**

Run:

```bash
cd /home/PyGeoModel/frontend
VITE_MAP_ENGINE=maplibre npm test
VITE_MAP_ENGINE=maplibre npm run build
```

Expected: all tests pass and the production build exits 0.

- [ ] **Step 2: Rebuild and restart only the frontend service**

Run:

```bash
cd /home/PyGeoModel
VITE_MAP_ENGINE=maplibre docker compose build frontend
VITE_MAP_ENGINE=maplibre docker compose up -d --no-build frontend
docker compose ps
```

Expected: `pygeomodel-frontend-1` is recreated and `Up`; backend remains `Up`.

- [ ] **Step 3: Verify the public app and all TianDiTu upstream nodes**

Run:

```bash
curl -fsS http://124.221.208.30/PyGeoModel/ | rg 'assets/index-.*\.js'

for endpoint in t0 t1 t2 t3 t4 t5 t6 t7; do
  status=$(curl -sS -o /dev/null -w '%{http_code}' \
    -H 'User-Agent: Mozilla/5.0 Chrome/150.0.0.0' \
    -H 'Referer: http://124.221.208.30/PyGeoModel/' \
    "http://124.221.208.30/PyGeoModel/tianditu/${endpoint}/vec_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=vec&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX=9&TILEROW=209&TILECOL=373&PROXY_VERSION=2")
  printf '%s %s\n' "$endpoint" "$status"
  test "$status" = 200
done
```

Expected: public HTML returns an asset hash and `t0` through `t7` each return 200.

- [ ] **Step 4: Verify the deployed bundle selected MapLibre without leaking tokens**

Run:

```bash
docker exec pygeomodel-frontend-1 sh -lc \
  'grep -ao "VITE_MAPBOX_ACCESS_TOKEN is required" /app/dist/assets/index-*.js | head -n 1'

awk '$7 ~ /PyGeoModel\/tianditu/ && $9 == 403 {print}' \
  /var/log/nginx/access.log | tail -n 20
```

Expected: the configuration error text exists for explicit Mapbox builds, no token value is printed, and no new TianDiTu 403 entry appears after the deployment timestamp.

Manually load `http://124.221.208.30/PyGeoModel/` in a clean browser session. Expected: the map renders TianDiTu tiles, the console has no `A valid Mapbox access token is required` error, and existing 3D/map interactions remain available.

- [ ] **Step 5: Confirm repository state and report deployment**

Run:

```bash
cd /home/PyGeoModel
git status --short
git log -4 --oneline
```

Expected: only previously known TianDiTu-related uncommitted changes remain, and the map-engine commits are visible. Report the public URL, selected default engine, test counts, build result, eight tile status codes, and any residual browser-only verification gap.
