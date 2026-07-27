# Workbench DEM And GLB Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users manually overlay a geographically referenced `scene_glb` task artifact on its source DEM in the existing MapLibre workbench at true 1:1 elevation.

**Architecture:** A projection kernel validates `asset.extras.scene3d` and converts every static GLB vertex from the local glTF frame through WGS84 UTM into local Mercator coordinates. A generic Three.js MapLibre custom layer owns rendering, bounds, terrain-exaggeration reference counting, and disposal, while `useMapWorkspace` owns lazy task-scoped UI state and cancellation. The existing Files tab remains the artifact download surface; the Layers tab gains one manual 3D overlay control.

**Tech Stack:** Vue 3.5, TypeScript 5.7, MapLibre GL JS 4.7, Three.js 0.171 `GLTFLoader`, proj4 2.20.9, Element Plus 2.9, Vitest 4.1, Playwright, Docker Desktop.

## Global Constraints

- Rendering MUST use one MapLibre `custom` layer with `renderingMode: "3d"`; do not add a second canvas or camera.
- Loading MUST be manual. No GLB request occurs before the user enables its toggle.
- Terrain exaggeration MUST be `1.0` while at least one compatible GLB is visible and MUST return to `1.35` after the final GLB is removed.
- Geographic conversion MUST operate per vertex; do not use one origin-scale approximation for the approximately 100 km pilot scene.
- Version 1 accepts only `schema_version=1`, metres, WGS84 geography, axes `X=east/Y=up/Z=south`, and WGS84 UTM EPSGs `32601-32660` or `32701-32760`.
- Version 1 accepts only static mesh scenes; reject animations and skinned meshes with a specific preview error.
- The frontend preview ceiling is 50,000,000 bytes. Files above 15,000,000 bytes show byte progress when `Content-Length` is available.
- Turning an overlay off MUST remove the MapLibre layer and dispose geometry, material, texture, and renderer resources.
- A task's DEM ID MUST equal the selected DEM ID before fetching its GLB.
- Existing GeoJSON layers, radar 3D layers, spatial editing, Files-tab downloads, and server artifacts MUST remain unchanged.
- No director camera, playback, narration, recording, editing, or browser re-export is added.
- Install npm dependencies through Clash at `http://127.0.0.1:7897`.
- Manual source edits use `apply_patch`; runtime screenshots and generated data remain outside Git.

---

### Task 1: Scene3d Metadata And Geographic Projection Kernel

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Create: `frontend/src/map/sceneGlbGeoReference.ts`
- Create: `frontend/src/map/sceneGlbGeoReference.test.ts`

**Interfaces:**
- Consumes: untrusted `asset.extras.scene3d` JSON and optional expected task/model IDs.
- Produces: `validateScene3dMetadata(value, expected)`, `createSceneGeoReference(metadata)`, `Scene3dMetadata`, `SceneGeoReference`, `SceneGeographicPosition`.

- [ ] **Step 1: Install the proven projection dependency through Clash**

Run from `frontend`:

```powershell
$env:HTTP_PROXY='http://127.0.0.1:7897'
$env:HTTPS_PROXY='http://127.0.0.1:7897'
npm install --save-exact proj4@2.20.9 --registry=https://registry.npmjs.org
```

Expected: `proj4` is pinned to `2.20.9` in both package files; no other dependency is upgraded.

- [ ] **Step 2: Write failing validation and north/south UTM conversion tests**

Create `frontend/src/map/sceneGlbGeoReference.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import {
  createSceneGeoReference,
  validateScene3dMetadata
} from "./sceneGlbGeoReference";

const north = {
  schema_version: 1,
  task_id: "air_corridor_task_a",
  model_id: "air_corridor",
  units: "metre",
  source_crs: "EPSG:32644",
  geographic_crs: "EPSG:4326",
  origin: {
    projected_x: 335974.7457902762,
    projected_y: 3486028.840193924,
    longitude: 79.27293573113577,
    latitude: 31.497477067232186,
    altitude_amsl_m: 5000
  },
  axes: { x: "east", y: "up", z: "south" }
};

describe("scene GLB georeference", () => {
  it("validates the exact version-one coordinate contract", () => {
    expect(validateScene3dMetadata(north, {
      taskId: "air_corridor_task_a",
      modelId: "air_corridor"
    })).toEqual(north);
    expect(() => validateScene3dMetadata({ ...north, units: "foot" }))
      .toThrow("metre");
    expect(() => validateScene3dMetadata({
      ...north,
      axes: { x: "east", y: "north", z: "up" }
    })).toThrow("axes");
    expect(() => validateScene3dMetadata({ ...north, source_crs: "EPSG:3857" }))
      .toThrow("UTM");
  });

  it("reconstructs projected and AMSL coordinates with Z pointing south", () => {
    const reference = createSceneGeoReference(validateScene3dMetadata(north));
    const result = reference.project([1000, 250, -2000]);

    expect(result.projected).toEqual([336974.7457902762, 3488028.840193924]);
    expect(result.altitudeAmslM).toBe(5250);
    expect(result.longitude).toBeCloseTo(79.283, 2);
    expect(result.latitude).toBeCloseTo(31.516, 2);
    expect(result.mercator.every(Number.isFinite)).toBe(true);
  });

  it("supports southern-hemisphere WGS84 UTM zones", () => {
    const south = {
      ...north,
      source_crs: "EPSG:32756",
      origin: {
        projected_x: 334368.6,
        projected_y: 6250941.0,
        longitude: 151.2,
        latitude: -33.86,
        altitude_amsl_m: 0
      }
    };
    const result = createSceneGeoReference(validateScene3dMetadata(south))
      .project([0, 100, 0]);

    expect(result.longitude).toBeCloseTo(151.2, 2);
    expect(result.latitude).toBeCloseTo(-33.86, 2);
    expect(result.altitudeAmslM).toBe(100);
  });
});
```

- [ ] **Step 3: Run the projection test and verify RED**

Run:

```powershell
npm test -- src/map/sceneGlbGeoReference.test.ts
```

Expected: FAIL because `sceneGlbGeoReference.ts` does not exist.

- [ ] **Step 4: Implement strict metadata validation and per-point projection**

Create `frontend/src/map/sceneGlbGeoReference.ts` with these public types and behavior:

```ts
import maplibregl from "maplibre-gl";
import proj4 from "proj4";

export interface Scene3dMetadata {
  schema_version: 1;
  task_id: string;
  model_id: string;
  units: "metre";
  source_crs: string;
  geographic_crs: "EPSG:4326";
  origin: {
    projected_x: number;
    projected_y: number;
    longitude: number;
    latitude: number;
    altitude_amsl_m: number;
  };
  axes: { x: "east"; y: "up"; z: "south" };
  [key: string]: unknown;
}

export interface SceneMetadataExpectation {
  taskId?: string;
  modelId?: string;
}

export interface SceneGeographicPosition {
  projected: [number, number];
  altitudeAmslM: number;
  longitude: number;
  latitude: number;
  mercator: [number, number, number];
}

export interface SceneGeoReference {
  metadata: Scene3dMetadata;
  anchor: maplibregl.MercatorCoordinate;
  project(point: readonly [number, number, number]): SceneGeographicPosition;
}

export function validateScene3dMetadata(
  value: unknown,
  expected: SceneMetadataExpectation = {}
): Scene3dMetadata {
  if (!isRecord(value) || value.schema_version !== 1) {
    throw new Error("GLB scene3d schema_version must be 1");
  }
  if (value.units !== "metre") throw new Error("GLB scene3d units must be metre");
  if (value.geographic_crs !== "EPSG:4326") {
    throw new Error("GLB scene3d geographic CRS must be EPSG:4326");
  }
  if (!isRecord(value.axes)
    || value.axes.x !== "east" || value.axes.y !== "up" || value.axes.z !== "south") {
    throw new Error("GLB scene3d axes must be X=east, Y=up, Z=south");
  }
  if (typeof value.source_crs !== "string" || utmDefinition(value.source_crs) === null) {
    throw new Error("GLB scene3d source CRS must be WGS84 UTM");
  }
  if (typeof value.task_id !== "string" || typeof value.model_id !== "string") {
    throw new Error("GLB scene3d task_id and model_id are required");
  }
  if (expected.taskId && value.task_id !== expected.taskId) {
    throw new Error("GLB scene3d task_id does not match the selected task");
  }
  if (expected.modelId && value.model_id !== expected.modelId) {
    throw new Error("GLB scene3d model_id does not match the selected model");
  }
  if (!isFiniteOrigin(value.origin)) throw new Error("GLB scene3d origin must be finite");
  return value as unknown as Scene3dMetadata;
}

export function createSceneGeoReference(metadata: Scene3dMetadata): SceneGeoReference {
  const definition = utmDefinition(metadata.source_crs);
  if (!definition) throw new Error("GLB scene3d source CRS must be WGS84 UTM");
  const inverse = proj4(definition, "EPSG:4326");
  const anchor = maplibregl.MercatorCoordinate.fromLngLat(
    { lng: metadata.origin.longitude, lat: metadata.origin.latitude },
    metadata.origin.altitude_amsl_m
  );
  return {
    metadata,
    anchor,
    project([x, y, z]) {
      const projected: [number, number] = [
        metadata.origin.projected_x + x,
        metadata.origin.projected_y - z
      ];
      const [longitude, latitude] = inverse.forward(projected);
      const altitudeAmslM = metadata.origin.altitude_amsl_m + y;
      const mercator = maplibregl.MercatorCoordinate.fromLngLat(
        { lng: longitude, lat: latitude }, altitudeAmslM
      );
      const values = [longitude, latitude, altitudeAmslM, mercator.x, mercator.y, mercator.z];
      if (!values.every(Number.isFinite)) throw new Error("GLB vertex produced non-finite coordinates");
      return {
        projected,
        altitudeAmslM,
        longitude,
        latitude,
        mercator: [mercator.x - anchor.x, mercator.y - anchor.y, mercator.z - anchor.z]
      };
    }
  };
}
```

Add these private helpers:

```ts
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isFiniteOrigin(value: unknown): value is Scene3dMetadata["origin"] {
  if (!isRecord(value)) return false;
  return [
    value.projected_x,
    value.projected_y,
    value.longitude,
    value.latitude,
    value.altitude_amsl_m
  ].every((item) => typeof item === "number" && Number.isFinite(item));
}

function utmDefinition(sourceCrs: string) {
  const match = /^EPSG:(326|327)(0[1-9]|[1-5][0-9]|60)$/.exec(sourceCrs);
  if (!match) return null;
  const south = match[1] === "327";
  const zone = Number(match[2]);
  return `+proj=utm +zone=${zone} ${south ? "+south " : ""}+datum=WGS84 +units=m +no_defs`;
}
```

- [ ] **Step 5: Run projection tests and the frontend type build**

Run:

```powershell
npm test -- src/map/sceneGlbGeoReference.test.ts
npm run build
```

Expected: 3 tests pass; TypeScript and Vite production build exit 0. The existing large-chunk warning may remain.

- [ ] **Step 6: Commit the projection kernel**

```powershell
git add frontend/package.json frontend/package-lock.json frontend/src/map/sceneGlbGeoReference.ts frontend/src/map/sceneGlbGeoReference.test.ts
git commit -m "feat: add scene glb georeference kernel"
```

---

### Task 2: Static GLB Parsing, Conversion, Bounds, And Disposal

**Files:**
- Create: `frontend/src/map/sceneGlbAsset.ts`
- Create: `frontend/src/map/sceneGlbAsset.test.ts`

**Interfaces:**
- Consumes: `ArrayBuffer`, `SceneMetadataExpectation`, and Task 1's georeference kernel.
- Produces: `parseSceneGlb(buffer, expectation)`, `prepareStaticScene(root, metadata, animations)`, `disposePreparedScene(asset)`, `PreparedSceneGlb`, `SceneGlbProgress`.

- [ ] **Step 1: Write failing static-scene conversion tests**

Create `frontend/src/map/sceneGlbAsset.test.ts`:

```ts
import * as THREE from "three";
import { describe, expect, it, vi } from "vitest";

import { prepareStaticScene, disposePreparedScene } from "./sceneGlbAsset";
import type { Scene3dMetadata } from "./sceneGlbGeoReference";

const metadata: Scene3dMetadata = {
  schema_version: 1,
  task_id: "task-a",
  model_id: "air_corridor",
  units: "metre",
  source_crs: "EPSG:32644",
  geographic_crs: "EPSG:4326",
  origin: {
    projected_x: 335974.7457902762,
    projected_y: 3486028.840193924,
    longitude: 79.27293573113577,
    latitude: 31.497477067232186,
    altitude_amsl_m: 5000
  },
  axes: { x: "east", y: "up", z: "south" }
};

describe("static scene GLB preparation", () => {
  it("bakes node transforms, preserves semantics, and returns finite bounds", () => {
    const root = new THREE.Group();
    const material = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.4 });
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(100, 40, 60), material);
    mesh.name = "corridor_path";
    mesh.userData = { kind: "corridor_path" };
    mesh.position.set(1000, 200, -500);
    root.add(mesh);

    const asset = prepareStaticScene(root, metadata, []);

    expect(asset.group.getObjectByName("corridor_path")?.userData.kind).toBe("corridor_path");
    expect(asset.bounds.west).toBeLessThan(asset.bounds.east);
    expect(asset.bounds.south).toBeLessThan(asset.bounds.north);
    expect(asset.bounds.minAltitudeM).toBeLessThan(asset.bounds.maxAltitudeM);
    expect(asset.group.position.toArray()).toEqual([0, 0, 0]);
  });

  it("rejects animations and skinned meshes", () => {
    expect(() => prepareStaticScene(new THREE.Group(), metadata, [new THREE.AnimationClip("move", 1, [])]))
      .toThrow("animated");
    const root = new THREE.Group();
    root.add(new THREE.SkinnedMesh(new THREE.BoxGeometry(), new THREE.MeshBasicMaterial()));
    expect(() => prepareStaticScene(root, metadata, [])).toThrow("skinned");
  });

  it("disposes shared resources exactly once", () => {
    const material = new THREE.MeshBasicMaterial();
    const root = new THREE.Group();
    root.add(new THREE.Mesh(new THREE.BoxGeometry(), material));
    const asset = prepareStaticScene(root, metadata, []);
    const prepared = asset.group.children[0] as THREE.Mesh;
    asset.group.add(new THREE.Mesh(prepared.geometry, prepared.material));
    const geometryDispose = vi.spyOn(prepared.geometry, "dispose");
    const materialDispose = vi.spyOn(material, "dispose");

    disposePreparedScene(asset);
    disposePreparedScene(asset);

    expect(geometryDispose).toHaveBeenCalledOnce();
    expect(materialDispose).toHaveBeenCalledOnce();
  });
});
```

- [ ] **Step 2: Run the asset test and verify RED**

Run:

```powershell
npm test -- src/map/sceneGlbAsset.test.ts
```

Expected: FAIL because `sceneGlbAsset.ts` does not exist.

- [ ] **Step 3: Implement static parsing and transformation**

Create `frontend/src/map/sceneGlbAsset.ts` with this public contract:

```ts
import * as THREE from "three";
import { GLTFLoader, type GLTF } from "three/examples/jsm/loaders/GLTFLoader.js";

import {
  createSceneGeoReference,
  validateScene3dMetadata,
  type Scene3dMetadata,
  type SceneMetadataExpectation
} from "./sceneGlbGeoReference";

export interface SceneGlbBounds {
  west: number;
  south: number;
  east: number;
  north: number;
  minAltitudeM: number;
  maxAltitudeM: number;
}

export interface PreparedSceneGlb {
  group: THREE.Group;
  anchor: [number, number, number];
  bounds: SceneGlbBounds;
  metadata: Scene3dMetadata;
  disposed: boolean;
}

export interface SceneGlbProgress { loaded: number; total: number | null }

export async function parseSceneGlb(
  buffer: ArrayBuffer,
  expected: SceneMetadataExpectation
): Promise<PreparedSceneGlb> {
  const gltf = await parseGltf(buffer);
  const raw = (gltf.parser.json as { asset?: { extras?: { scene3d?: unknown } } })
    .asset?.extras?.scene3d;
  const metadata = validateScene3dMetadata(raw, expected);
  return prepareStaticScene(gltf.scene, metadata, gltf.animations);
}
```

`parseGltf` wraps `new GLTFLoader().parse(buffer, "", resolve, reject)` in a Promise. `prepareStaticScene` MUST:

1. reject non-empty animations;
2. call `root.updateMatrixWorld(true)`;
3. reject any `THREE.SkinnedMesh`;
4. create one output `THREE.Group`;
5. for each `THREE.Mesh`, bake `matrixWorld` into a cloned geometry;
6. replace every position with `reference.project([x, y, z]).mercator`;
7. track WGS84 and altitude minima/maxima from the same projection result;
8. recompute bounding boxes, bounding spheres, and vertex normals;
9. create a new mesh with the transformed geometry and original material;
10. preserve `name`, `userData`, `renderOrder`, and visibility;
11. throw if no finite mesh vertices were emitted;
12. return the anchor as `[reference.anchor.x, reference.anchor.y, reference.anchor.z]`.

`disposePreparedScene` traverses the prepared group and uses Sets to dispose every unique geometry, material, and referenced texture once. It returns immediately when `asset.disposed` is already true.

- [ ] **Step 4: Add failing fetch-limit and progress tests**

Append tests for a separately exported `fetchSceneGlb(url, signal, onProgress?)`:

```ts
it("rejects files above 50 MB before parsing", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(new Uint8Array(1), {
    headers: { "Content-Length": "50000001" }
  })));
  await expect(fetchSceneGlb("/large.glb", new AbortController().signal))
    .rejects.toThrow("50 MB");
});

it("reports streamed byte progress", async () => {
  const progress = vi.fn();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(new Uint8Array([1, 2, 3]), {
    headers: { "Content-Length": "3" }
  })));
  const buffer = await fetchSceneGlb("/scene.glb", new AbortController().signal, progress);
  expect(buffer.byteLength).toBe(3);
  expect(progress).toHaveBeenLastCalledWith({ loaded: 3, total: 3 });
});
```

Run the file and verify these new tests fail because `fetchSceneGlb` is absent.

- [ ] **Step 5: Implement bounded streaming fetch**

Add:

```ts
export const SCENE_GLB_PREVIEW_MAX_BYTES = 50_000_000;
export const SCENE_GLB_PROGRESS_THRESHOLD_BYTES = 15_000_000;

export async function fetchSceneGlb(
  url: string,
  signal: AbortSignal,
  onProgress?: (progress: SceneGlbProgress) => void
): Promise<ArrayBuffer>;
```

The implementation checks `response.ok`, validates `Content-Length` before reading, reads `response.body.getReader()` when available, rejects as soon as accumulated bytes exceed `SCENE_GLB_PREVIEW_MAX_BYTES`, emits progress only when total is unknown or above the 15 MB threshold, and falls back to `response.arrayBuffer()` when streaming is unavailable.

- [ ] **Step 6: Run asset and projection tests**

```powershell
npm test -- src/map/sceneGlbAsset.test.ts src/map/sceneGlbGeoReference.test.ts
```

Expected: all tests pass with no uncaught console errors.

- [ ] **Step 7: Commit the static asset pipeline**

```powershell
git add frontend/src/map/sceneGlbAsset.ts frontend/src/map/sceneGlbAsset.test.ts
git commit -m "feat: prepare static scene glb assets"
```

---

### Task 3: MapLibre Custom Layer And Terrain Scale Registry

**Files:**
- Create: `frontend/src/map/sceneGlbLayer.ts`
- Create: `frontend/src/map/sceneGlbLayer.test.ts`

**Interfaces:**
- Consumes: Task 2's prepared static asset and MapLibre map.
- Produces: `addSceneGlbLayer`, `removeSceneGlbLayer`, `removeAllSceneGlbLayers`, `focusSceneGlbLayer`, `hasSceneGlbLayer`, `getSceneGlbTerrainTaskCount`, `SceneGlbLayerOptions`.

- [ ] **Step 1: Write failing layer lifecycle and terrain reference tests**

Create tests with a `FakeMap` that records layers and calls `onRemove` from `removeLayer`:

```ts
it("adds task-scoped custom layers and keeps terrain at 1.0 until the last removal", () => {
  const map = new FakeMap();
  const first = preparedAsset("task-a");
  const second = preparedAsset("task-b");

  addSceneGlbLayer(map as never, "task-a", first);
  addSceneGlbLayer(map as never, "task-b", second);

  expect(map.layers.get("scene-glb-task-a")?.renderingMode).toBe("3d");
  expect(map.setTerrain).toHaveBeenLastCalledWith({
    source: "dem-terrain-source",
    exaggeration: 1
  });
  expect(getSceneGlbTerrainTaskCount(map as never)).toBe(2);

  removeSceneGlbLayer(map as never, "task-a");
  expect(getSceneGlbTerrainTaskCount(map as never)).toBe(1);
  expect(map.setTerrain).toHaveBeenLastCalledWith({
    source: "dem-terrain-source",
    exaggeration: 1
  });

  removeSceneGlbLayer(map as never, "task-b");
  expect(map.setTerrain).toHaveBeenLastCalledWith({
    source: "dem-terrain-source",
    exaggeration: 1.35
  });
  expect(first.disposed).toBe(true);
  expect(second.disposed).toBe(true);
});

it("focuses the transformed WGS84 bounds with a stable 3D camera", () => {
  const map = new FakeMap();
  addSceneGlbLayer(map as never, "task-a", preparedAsset("task-a"));

  expect(focusSceneGlbLayer(map as never, "task-a")).toBe(true);
  expect(map.fitBounds).toHaveBeenCalledWith(
    [[79.0, 31.4], [80.0, 31.6]],
    expect.objectContaining({ pitch: 55, bearing: -25 })
  );
});
```

Also test idempotent removal, replacement of the same task, `removeAllSceneGlbLayers`, insertion before the first symbol layer, and a dispatched `webglcontextlost` event removing the affected registry entry so it can be manually loaded again.

- [ ] **Step 2: Run the layer tests and verify RED**

```powershell
npm test -- src/map/sceneGlbLayer.test.ts
```

Expected: FAIL because `sceneGlbLayer.ts` does not exist.

- [ ] **Step 3: Implement the task-scoped registry and custom layer**

Create `frontend/src/map/sceneGlbLayer.ts` around these constants and registry:

```ts
import maplibregl from "maplibre-gl";
import * as THREE from "three";

import { DEM_TERRAIN_SOURCE_ID } from "./mapLayers";
import { disposePreparedScene, type PreparedSceneGlb } from "./sceneGlbAsset";

const DEFAULT_TERRAIN_EXAGGERATION = 1.35;
const TRUE_SCALE_TERRAIN_EXAGGERATION = 1;

interface RegisteredSceneGlb {
  taskId: string;
  layerId: string;
  layer: maplibregl.CustomLayerInterface;
  asset: PreparedSceneGlb;
}

const registry = new WeakMap<maplibregl.Map, Map<string, RegisteredSceneGlb>>();
const terrainTasks = new WeakMap<maplibregl.Map, Set<string>>();

export interface SceneGlbLayerOptions {
  onLost?: () => void;
}

export function sceneGlbLayerId(taskId: string) {
  return `scene-glb-${taskId.replace(/[^A-Za-z0-9_-]+/g, "_")}`;
}
```

`addSceneGlbLayer(map, taskId, asset, options = {})` passes `options` into `createCustomLayer`. `createCustomLayer(asset, taskId, options)` MUST create Three camera, scene, and renderer in `onAdd` using the supplied map canvas/context. Add `asset.group` to the scene. In `render`, use:

```ts
const mapMatrix = new THREE.Matrix4().fromArray(matrix as number[]);
const anchorMatrix = new THREE.Matrix4().makeTranslation(...asset.anchor);
camera.projectionMatrix.copy(mapMatrix).multiply(anchorMatrix);
renderer.resetState();
renderer.render(scene, camera);
```

Set `renderer.autoClear = false`. Do not call `triggerRepaint` continuously. `onRemove` removes the group, calls `disposePreparedScene(asset)`, disposes the renderer, and releases the task from the terrain Set. Resource release MUST remain idempotent when removal is initiated before `onAdd`.

Register a named `webglcontextlost` listener on `map.getCanvas()` in `onAdd`. It calls `event.preventDefault()` and queues `removeSceneGlbLayer(map, taskId)` in a microtask. Remove that exact listener in `onRemove`. The workspace state returns to idle through a layer-loss callback supplied when the layer is created; this preserves manual retry rather than reconstructing automatically.

`addSceneGlbLayer` removes an existing same-task layer, adds the task to the terrain Set, applies `map.setTerrain({source: DEM_TERRAIN_SOURCE_ID, exaggeration: 1})`, registers the custom layer, and calls `map.addLayer(layer, firstSymbolLayerId(map))`.

Use these helpers so a missing DEM terrain source blocks the overlay instead of displaying geometry without its required terrain:

```ts
function firstSymbolLayerId(map: maplibregl.Map) {
  return map.getStyle().layers?.find((layer) => layer.type === "symbol")?.id;
}

function applyTerrainScale(
  map: maplibregl.Map,
  exaggeration: number,
  required: boolean
) {
  if (!map.getSource(DEM_TERRAIN_SOURCE_ID)) {
    if (required) {
      throw new Error("DEM terrain is not ready; retry the 3D overlay after terrain loads");
    }
    return;
  }
  map.setTerrain({ source: DEM_TERRAIN_SOURCE_ID, exaggeration });
}
```

Call it with `required=true` before adding the first GLB and `required=false` while restoring `1.35` during cleanup. Add a test proving `addSceneGlbLayer` throws this message, adds no registry entry, and disposes the prepared asset when `getSource(DEM_TERRAIN_SOURCE_ID)` is absent. Add another test proving removal remains harmless after the DEM terrain source has already been removed.

`removeSceneGlbLayer` removes through MapLibre when present, otherwise disposes the registry asset directly. The last terrain task restores exaggeration `1.35`. `focusSceneGlbLayer` uses WGS84 bounds with `padding: 60`, `pitch: 55`, `bearing: -25`, and `duration: 800`.

- [ ] **Step 4: Run custom-layer tests and focused existing 3D tests**

```powershell
npm test -- src/map/sceneGlbLayer.test.ts src/models/radar/layerAdapter.test.ts src/components/map/MapWorkspace.test.ts
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit the custom layer**

```powershell
git add frontend/src/map/sceneGlbLayer.ts frontend/src/map/sceneGlbLayer.test.ts
git commit -m "feat: render scene glb map layers"
```

---

### Task 4: Lazy Task-Scoped Overlay State And Cancellation

**Files:**
- Modify: `frontend/src/composables/useMapWorkspace.ts`
- Modify: `frontend/src/composables/useMapWorkspace.test.ts`

**Interfaces:**
- Consumes: current task, current `scene_glb` output file, selected DEM ID, map, Tasks 2-3 functions.
- Produces: `sceneGlbStates`, `sceneGlbStateFor`, `setSceneGlbVisibility`, `focusSceneGlb`, `removeIncompatibleSceneGlbs`, `removeAllSceneGlbs`, `resetSceneGlbStates`.

- [ ] **Step 1: Write failing lazy-load, mismatch, abort, and multi-task tests**

Extend `UseMapWorkspaceOptions` test setup with an injected adapter:

```ts
const sceneGlb = {
  load: vi.fn().mockResolvedValue(undefined),
  remove: vi.fn(),
  removeAll: vi.fn(),
  focus: vi.fn(() => true)
};
```

Add test imports:

```ts
import type { AirCorridorMetrics, AirCorridorRequest } from "../models/airCorridor/types";
```

Use complete fixtures:

```ts
const sceneFile: OutputFile = {
  kind: "scene_glb",
  label: "Air Corridor 3D Result GLB",
  url: "/outputs/air_corridor_task_demo/air_corridor_result.glb",
  download_url: "/api/air-corridor/planning/air_corridor_task_demo/outputs/scene_glb",
  filename: "air_corridor_result.glb",
  media_type: "model/gltf-binary",
  size_bytes: 1_980_764,
  exists: true
};

const finishedAirTask = {
  task_id: "air_corridor_task_demo",
  dem_id: "dem-a",
  status: "finished",
  progress: 100,
  message: "finished",
  request: { ...MODEL_REGISTRY.airCorridor.createDefaultRequest(), dem_id: "dem-a" },
  metrics: null,
  output_files: [sceneFile],
  warnings: []
} satisfies TaskSummary<AirCorridorRequest, AirCorridorMetrics>;
```

Add these behaviors:

```ts
it("does not fetch scene_glb until manually enabled", async () => {
  const workspace = useMapWorkspace("start-end-threats", undefined, {
    clientFactory: () => ({ metrics: vi.fn(), outputs: vi.fn().mockResolvedValue([sceneFile]) }),
    sceneGlb
  });
  await workspace.loadTaskOutputs("airCorridor", finishedAirTask);

  expect(sceneGlb.load).not.toHaveBeenCalled();
  expect(workspace.sceneGlbStateFor(finishedAirTask.task_id).status).toBe("idle");

  await workspace.setSceneGlbVisibility({} as never, "dem-a", "airCorridor", finishedAirTask, true);
  expect(sceneGlb.load).toHaveBeenCalledWith(expect.objectContaining({
    taskId: finishedAirTask.task_id,
    modelId: "air_corridor",
    url: "/api/air-corridor/planning/air_corridor_task_demo/outputs/scene_glb"
  }));
  expect(workspace.sceneGlbStateFor(finishedAirTask.task_id).status).toBe("visible");
});

it("rejects a DEM mismatch before fetch", async () => {
  await workspace.loadTaskOutputs("airCorridor", finishedAirTask);
  await workspace.setSceneGlbVisibility({} as never, "dem-b", "airCorridor", finishedAirTask, true);
  expect(sceneGlb.load).not.toHaveBeenCalled();
  expect(workspace.sceneGlbStateFor(finishedAirTask.task_id).error).toContain("DEM");
});

it("aborts loading and removes resources when toggled off", async () => {
  const pending = deferred<void>();
  sceneGlb.load.mockReturnValueOnce(pending.promise);
  const loading = workspace.setSceneGlbVisibility(map, "dem-a", "airCorridor", task, true);
  await Promise.resolve();
  await workspace.setSceneGlbVisibility(map, "dem-a", "airCorridor", task, false);
  expect(sceneGlb.remove).toHaveBeenCalledWith(map, task.task_id);
  expect(workspace.sceneGlbStateFor(task.task_id).status).toBe("idle");
  pending.resolve();
  await loading;
  expect(workspace.sceneGlbStateFor(task.task_id).status).toBe("idle");
});
```

Add a two-task test proving both states can be `visible` and removing one does not mutate the other.

- [ ] **Step 2: Run the composable tests and verify RED**

```powershell
npm test -- src/composables/useMapWorkspace.test.ts
```

Expected: new tests fail because overlay state and commands do not exist.

- [ ] **Step 3: Implement overlay state and adapter boundary**

Add:

```ts
export type SceneGlbOverlayStatus = "idle" | "loading" | "visible" | "error";

export interface SceneGlbOverlayState {
  taskId: string;
  modelId: ModelId;
  demId: string;
  status: SceneGlbOverlayStatus;
  visible: boolean;
  progress: { loaded: number; total: number | null } | null;
  error: string | null;
}

export interface SceneGlbLoadRequest {
  map: maplibregl.Map;
  taskId: string;
  modelId: string;
  url: string;
  signal: AbortSignal;
  onProgress(progress: SceneGlbProgress): void;
  onLayerLost(): void;
}

export interface SceneGlbAdapter {
  load(request: SceneGlbLoadRequest): Promise<void>;
  remove(map: maplibregl.Map, taskId: string): void;
  removeAll(map: maplibregl.Map): void;
  focus(map: maplibregl.Map, taskId: string): boolean;
}
```

The default adapter fetches through `fetchSceneGlb`, parses through `parseSceneGlb`, calls `addSceneGlbLayer`, and disposes a prepared asset if layer addition fails.

Define it once outside the composable:

```ts
const DEFAULT_SCENE_GLB_ADAPTER: SceneGlbAdapter = {
  async load(request) {
    const buffer = await fetchSceneGlb(request.url, request.signal, request.onProgress);
    const asset = await parseSceneGlb(buffer, {
      taskId: request.taskId,
      modelId: request.modelId
    });
    try {
      addSceneGlbLayer(request.map, request.taskId, asset, {
        onLost: request.onLayerLost
      });
    } catch (error) {
      disposePreparedScene(asset);
      throw error;
    }
  },
  remove: removeSceneGlbLayer,
  removeAll: removeAllSceneGlbLayers,
  focus: focusSceneGlbLayer
};
```

Map frontend IDs to the server metadata IDs with one explicit helper:

```ts
const SCENE_METADATA_MODEL_IDS: Record<ModelId, string> = {
  radar: "radar",
  uav: "uav",
  watchpost: "watchpost",
  artillery: "artillery",
  reconVehicle: "recon_vehicle",
  mobility: "mobility",
  airCorridor: "air_corridor"
};

function sceneMetadataModelId(modelId: ModelId) {
  return SCENE_METADATA_MODEL_IDS[modelId];
}
```

Pass this mapped value to `SceneGlbLoadRequest.modelId` and metadata validation; retain the frontend `ModelId` in UI state.

Use `ref<Record<string, SceneGlbOverlayState>>({})` and `Map<string, AbortController>`. `setSceneGlbVisibility` MUST:

1. resolve an existing current `scene_glb` file through `download_url`, then `url`;
2. resolve the URL with `resolveAssetUrl`;
3. derive task DEM from `task.request?.dem_id ?? task.dem_id`;
4. reject mismatch before creating a controller;
5. abort an older same-task controller;
6. update state to loading;
7. ignore stale completion by comparing the controller identity;
8. treat `AbortError` as idle without an error;
9. expose retry by allowing `error -> loading`;
10. set `visible` only after the custom layer is added.

Pass `onLayerLost` as a closure that changes only the matching visible task state back to idle and clears its progress/error. It must not issue a replacement network request.

`removeIncompatibleSceneGlbs(map, selectedDemId)` aborts and removes states whose `demId` differs. `removeAllSceneGlbs` aborts all, calls adapter `removeAll`, and clears states. `resetSceneGlbStates` clears controllers/states after an externally destroyed map without calling map APIs.

- [ ] **Step 4: Run composable and stale-request tests**

```powershell
npm test -- src/composables/useMapWorkspace.test.ts src/components/tasks/TaskResultPanel.test.ts
```

Expected: tests pass and existing GeoJSON loading remains unchanged.

- [ ] **Step 5: Commit lazy overlay state**

```powershell
git add frontend/src/composables/useMapWorkspace.ts frontend/src/composables/useMapWorkspace.test.ts
git commit -m "feat: manage lazy scene glb overlays"
```

---

### Task 5: Manual 3D Result Control In The Layers Tab

**Files:**
- Create: `frontend/src/components/tasks/SceneGlbControl.vue`
- Create: `frontend/src/components/tasks/SceneGlbControl.test.ts`
- Modify: `frontend/src/components/tasks/TaskResultPanel.vue`
- Modify: `frontend/src/components/tasks/TaskResultPanel.test.ts`

**Interfaces:**
- Consumes: existing `scene_glb` `OutputFile` and current `SceneGlbOverlayState`.
- Produces: `visibility(visible: boolean)` and `focus()` events from `SceneGlbControl`; forwards them as `scene-glb-visibility` and `scene-glb-focus` from `TaskResultPanel`.

- [ ] **Step 1: Write failing manual-control component tests**

Create tests that mount `SceneGlbControl` with an existing 1.98 MB file and assert:

```ts
expect(wrapper.get('[data-scene-glb-toggle]').attributes("aria-checked")).toBe("false");
expect(wrapper.text()).toContain("三维结果 · 空中走廊");
expect(wrapper.text()).toContain("任务 314ec4c4 · 未加载");
await wrapper.get('[data-scene-glb-toggle]').trigger("click");
expect(wrapper.emitted("visibility")?.[0]).toEqual([true]);
```

Add loading progress, visible/focus, error/retry, and over-50-MB disabled cases. In `TaskResultPanel.test.ts`, prove no control exists without `scene_glb`, while an existing scene file appears only in the Layers tab and the Files tab still renders `OutputFileList`.

- [ ] **Step 2: Run component tests and verify RED**

```powershell
npm test -- src/components/tasks/SceneGlbControl.test.ts src/components/tasks/TaskResultPanel.test.ts
```

Expected: FAIL because `SceneGlbControl.vue` and new panel props do not exist.

- [ ] **Step 3: Implement the compact manual control**

Create an unframed row matching `LayerList.vue` dimensions. Use Element Plus `ElSwitch`, `ElIcon`, `ElTooltip`, and `Location`. Public props:

```ts
defineProps<{
  file: OutputFile;
  state: SceneGlbOverlayState;
}>();

defineEmits<{
  visibility: [visible: boolean];
  focus: [];
}>();
```

The primary row label is `三维结果 · ${getModelDefinition(state.modelId).label}`. The secondary line prefixes every state with the final eight task-ID characters, for example `任务 314ec4c4 · 已叠加到地形`, while the full task ID is available through the row `title` attribute. State copy after that prefix is exactly:

- idle: `未加载`;
- loading without reportable total: `正在加载`;
- loading with total: `正在加载 ${percent}%`;
- visible: `已叠加到地形`;
- error: the state error string.

The switch is on during loading or visible. Clicking it off during loading emits `false` so the request can abort. The focus icon is enabled only when visible. A file whose `size_bytes` exceeds 50,000,000 disables the switch and shows `文件超过预览上限`. Do not put help text over the map.

- [ ] **Step 4: Integrate the control into `TaskResultPanel`**

Add props:

```ts
sceneGlbState?: SceneGlbOverlayState | null;
```

Compute:

```ts
const sceneGlbFile = computed(() => effectiveOutputFiles.value.find(
  (file) => file.kind === "scene_glb" && file.exists
) ?? null);
```

Wrap the Layers branch in one unframed container that renders existing `LayerList` and then `SceneGlbControl` when both file and state exist. Add emits:

```ts
"scene-glb-visibility": [visible: boolean];
"scene-glb-focus": [];
```

Do not add a fifth tab or duplicate the file download command.

- [ ] **Step 5: Run component tests and check responsive text layout**

```powershell
npm test -- src/components/tasks/SceneGlbControl.test.ts src/components/tasks/TaskResultPanel.test.ts
npm run build
```

Expected: component tests and production build pass; no button or row text overflows at 320 px component width in the test DOM.

- [ ] **Step 6: Commit the Layers-tab control**

```powershell
git add frontend/src/components/tasks/SceneGlbControl.vue frontend/src/components/tasks/SceneGlbControl.test.ts frontend/src/components/tasks/TaskResultPanel.vue frontend/src/components/tasks/TaskResultPanel.test.ts
git commit -m "feat: add manual scene glb control"
```

---

### Task 6: App Wiring, DEM Compatibility, And Map Lifecycle

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/App.test.ts`
- Modify: `frontend/src/components/map/MapWorkspace.vue`
- Modify: `frontend/src/components/map/MapWorkspace.test.ts`

**Interfaces:**
- Consumes: Tasks 4-5 workspace commands and control events.
- Produces: a complete manual task-to-map overlay workflow and deterministic cleanup on DEM/map teardown.

- [ ] **Step 1: Write failing App wiring tests**

Extend the `TaskResultPanel` stub so it can emit `scene-glb-visibility` and `scene-glb-focus`. Add tests proving:

```ts
it("loads a scene only after the result control requests visibility", async () => {
  // Select a finished task with scene_glb, emit map-ready, then emit true.
  expect(sceneGlbAdapter.load).not.toHaveBeenCalled();
  panel.vm.$emit("scene-glb-visibility", true);
  await flushPromises();
  expect(sceneGlbAdapter.load).toHaveBeenCalledOnce();
});

it("removes incompatible overlays before switching DEM", async () => {
  demSelector.vm.$emit("update:model-value", "dem-b");
  await flushPromises();
  expect(sceneGlbAdapter.remove).toHaveBeenCalledWith(map, "task-from-dem-a");
});
```

In `App.test.ts`, mock `fetchSceneGlb`, `parseSceneGlb`, and the exported `sceneGlbLayer` functions with `vi.hoisted` spies. The App uses the default workspace adapter, so assertions target those module spies rather than introducing a production injection prop on `App`.

Also prove focus forwarding, all-layer removal during app unmount, and state reset when `MapWorkspace` supplies a replacement map instance.

- [ ] **Step 2: Write failing map teardown test**

In `MapWorkspace.test.ts`, add a custom fake layer with `onRemove` and assert `map.remove()` invokes the layer lifecycle in the fake harness. This ensures App reset behavior corresponds to real MapLibre teardown.

- [ ] **Step 3: Run the App and map tests to verify RED**

```powershell
npm test -- src/App.test.ts src/components/map/MapWorkspace.test.ts
```

Expected: new event/lifecycle assertions fail.

- [ ] **Step 4: Wire scene state and events in App**

Add:

```vue
<TaskResultPanel
  :model-id="selectedTaskContext.modelId"
  :task="selectedTaskContext.task"
  :metrics="mapWorkspace.taskMetrics.value"
  :output-files="mapWorkspace.outputFiles.value"
  :layer-states="mapWorkspace.layerStates.value"
  :scene-glb-state="mapWorkspace.sceneGlbStateFor(selectedTaskContext.task.task_id)"
  @layer-visibility="setLayerVisibility"
  @layer-opacity="setLayerOpacity"
  @layer-focus="focusLayer"
  @scene-glb-visibility="setSceneGlbVisibility"
  @scene-glb-focus="focusSceneGlb"
/>
```

Handlers:

```ts
async function setSceneGlbVisibility(visible: boolean) {
  const instance = map.value;
  const context = selectedTaskContext.value;
  if (!instance || !context) return;
  await mapWorkspace.setSceneGlbVisibility(
    instance,
    demManager.selectedDem.value,
    context.modelId,
    context.task as never,
    visible
  );
}

function focusSceneGlb() {
  const instance = map.value;
  const context = selectedTaskContext.value;
  if (instance && context) mapWorkspace.focusSceneGlb(instance, context.task.task_id);
}
```

Watch `demManager.selectedDem.value`; when the ID changes and a map exists, call `removeIncompatibleSceneGlbs(map, nextId)` before the child DEM watcher renders the replacement terrain. On App unmount call `removeAllSceneGlbs(map)` before `map.remove()`.

In `setMap`, if an older map instance exists and differs from the new instance, call `resetSceneGlbStates()` because MapLibre has already removed the physical custom layers.

For Playwright observability without shipping a production global, expose the live map only in Vite development mode inside `setMap`:

```ts
if (import.meta.env.DEV) {
  (window as Window & { __PYGEOMODEL_MAP__?: maplibregl.Map })
    .__PYGEOMODEL_MAP__ = instance;
}
```

Delete the property during App unmount when it still references the removed map. The production build tree-shakes this branch because `import.meta.env.DEV` is false.

Do not remove compatible overlays merely because another task is selected. This preserves multiple task GLBs on the same live map; selecting a previous task exposes its existing on-state again.

- [ ] **Step 5: Make MapWorkspace terrain synchronization stable**

Keep `addOrUpdateDemTerrain`'s normal default at `1.35`. Ensure `syncDem` only reinstalls terrain when the DEM identity or terrain URL changes, not on unrelated component updates. Track the last synced DEM ID and clear it on DEM removal. This prevents a component update from overriding the custom-layer registry's `1.0` exaggeration.

Extend `MapWorkspace.test.ts` to prove rerendering an unchanged DEM does not call `setTerrain` again, while changing the DEM does.

- [ ] **Step 6: Run App, map, workspace, and full frontend tests**

```powershell
npm test -- src/App.test.ts src/components/map/MapWorkspace.test.ts src/composables/useMapWorkspace.test.ts
npm test -- --run
```

Expected: selected tests pass; full frontend suite passes with no new warnings.

- [ ] **Step 7: Commit end-to-end wiring**

```powershell
git add frontend/src/App.vue frontend/src/App.test.ts frontend/src/components/map/MapWorkspace.vue frontend/src/components/map/MapWorkspace.test.ts
git commit -m "feat: overlay scene glb results on dem"
```

---

### Task 7: Real Docker And Playwright Acceptance

**Files:**
- Modify: `README.md`
- Runtime only: `data/outputs/air_corridor_task_20260714_133725_314ec4c4/air_corridor_result.glb`
- Runtime only: visualization HTML, Playwright script, and screenshots outside Git.

**Interfaces:**
- Consumes: completed frontend, existing accepted air-corridor task, Zanda County DEM, Clash proxy.
- Produces: verified manual DEM/GLB overlay, screenshots, pixel evidence, and documented user workflow.

- [ ] **Step 1: Document the workbench workflow**

Add to README after Air Corridor GLB inspection:

```markdown
### Preview a GLB over its DEM

Open a finished task that includes `scene_glb`, choose **Layers**, and enable
**3D result**. The workbench loads the file only after this manual action and
temporarily displays DEM terrain at true 1:1 elevation. Disable the layer to
remove the preview and release browser GPU resources. The Files tab continues
to provide the original GLB download.

The preview requires the task's source DEM to be selected and currently accepts
static PyGeoModel GLBs whose embedded `scene3d` metadata declares WGS84 UTM and
the `X=east`, `Y=up`, `Z=south` frame.
```

- [ ] **Step 2: Run fresh source regression before Docker build**

```powershell
cd backend
E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pytest -q
cd ..\frontend
npm test -- --run
npm run build
```

Expected: backend and frontend tests pass; build exits 0. Existing NumPy/Rasterio deprecation and Vite chunk-size warnings may remain.

- [ ] **Step 3: Build isolated backend and frontend images through Clash**

From the feature worktree:

```powershell
$env:HTTP_PROXY='http://127.0.0.1:7897'
$env:HTTPS_PROXY='http://127.0.0.1:7897'
docker build -f backend/Dockerfile -t pygeomodel-glb-overlay-backend:latest .
docker build -f frontend/Dockerfile `
  --build-arg NPM_REGISTRY=https://registry.npmjs.org/ `
  --build-arg VITE_API_BASE=/PyGeoModel `
  --build-arg VITE_BASE_PATH=/PyGeoModel/ `
  --build-arg VITE_PROXY_TARGET=http://host.docker.internal:8001 `
  -t pygeomodel-glb-overlay-frontend:latest .
```

Expected: both builds exit 0 and include `proj4==2.20.9` in the frontend lockfile install.

- [ ] **Step 4: Start isolated validation services without disturbing 8000/5173**

```powershell
docker run -d --name pygeomodel-glb-overlay-backend `
  -p 127.0.0.1:8001:8000 `
  -e PYGEOMODEL_DATA_DIR=/workspace/data `
  -v E:\Github\PyGeoModel\data:/workspace/data `
  pygeomodel-glb-overlay-backend:latest

docker run -d --name pygeomodel-glb-overlay-frontend `
  --add-host host.docker.internal:host-gateway `
  -p 127.0.0.1:5174:5173 `
  -e VITE_API_BASE=/PyGeoModel `
  -e VITE_BASE_PATH=/PyGeoModel/ `
  -e VITE_PROXY_TARGET=http://host.docker.internal:8001 `
  pygeomodel-glb-overlay-frontend:latest `
  npm run dev -- --host 0.0.0.0 --port 5173

Invoke-RestMethod http://127.0.0.1:8001/api/health
```

Expected: backend health is `ok`; workbench opens at `http://127.0.0.1:5174/PyGeoModel/`; main containers remain on 8000/5173.

- [ ] **Step 5: Verify the accepted artifact before UI testing**

```powershell
docker exec pygeomodel-glb-overlay-backend python /app/scripts/inspect_glb.py `
  "/workspace/data/outputs/air_corridor_task_20260714_133725_314ec4c4/air_corridor_result.glb" `
  --max-bytes 50000000
curl.exe --fail --output NUL `
  "http://127.0.0.1:8001/api/air-corridor/planning/air_corridor_task_20260714_133725_314ec4c4/outputs/scene_glb"
```

Expected: valid GLB, 27 semantic nodes, approximately 1.98 MB, HTTP 200, and `model/gltf-binary`.

- [ ] **Step 6: Run Playwright manual-load and visual checks**

At `1440x900` and `390x844`, automate this exact sequence:

1. load the workbench and select `dem_20260713_080113_884937cf`;
2. restore `air_corridor_task_20260714_133725_314ec4c4` from history;
3. open Layers and assert no request ending in `/outputs/scene_glb` has occurred;
4. capture the DEM-only canvas pixel hash and verify terrain exaggeration is `1.35`;
5. enable `3D result` and wait for state `visible`;
6. assert exactly one GLB request, terrain exaggeration `1.0`, and 27 loaded semantic nodes;
7. sample WebGL canvas pixels and require at least 40 quantized colors plus more than 35 luma spread;
8. project representative corridor and threat bounds and require them inside the viewport;
9. pan, pitch, zoom, and rotate the map and prove canvas hashes change without GLB/DEM desynchronization;
10. use Focus and prove complete transformed bounds are framed;
11. disable the overlay, prove its layer is absent, canvas pixels change, and exaggeration returns to `1.35`;
12. save desktop and mobile screenshots under the visualization workspace.

Read the development-only `window.__PYGEOMODEL_MAP__.getTerrain()?.exaggeration` for the exact scale assertions and use `getLayer("scene-glb-air_corridor_task_20260714_133725_314ec4c4")` for layer lifecycle assertions.

Also switch to another DEM while loading and prove the request aborts with no console error and no stale layer.

- [ ] **Step 7: Clean up only temporary services**

```powershell
docker stop pygeomodel-glb-overlay-frontend pygeomodel-glb-overlay-backend
docker rm pygeomodel-glb-overlay-frontend pygeomodel-glb-overlay-backend
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
git status --short
git diff --check
```

Expected: temporary 5174/8001 containers are gone, main 5173/8000 containers remain, runtime files are ignored, and only the planned README change is uncommitted.

- [ ] **Step 8: Commit documentation**

```powershell
git add README.md
git commit -m "docs: explain dem glb overlays"
```

---

### Task 8: Final Review, Verification, Push, And PR Update

**Files:**
- Verify: all files changed from `origin/main...HEAD`.
- Modify only if review identifies a reproducible defect with a new failing test.

**Interfaces:**
- Consumes: Tasks 1-7 and the approved design.
- Produces: reviewed branch, fresh test evidence, pushed commits, and updated PR #1.

- [ ] **Step 1: Review implementation against the approved design**

Review every requirement in `docs/superpowers/specs/2026-07-14-workbench-dem-glb-overlay-design.md`, specifically:

- manual network behavior;
- exact metadata and UTM validation;
- per-vertex transformation and local Mercator anchoring;
- static-only scene rejection;
- unique task layer IDs and multi-task state isolation;
- true-scale terrain reference counting;
- DEM mismatch prevention and abort handling;
- idempotent resource disposal;
- Files-tab download compatibility;
- no camera/playback/editor scope expansion.

Order findings by severity. Fix Critical and Important findings through RED/GREEN tests before proceeding.

- [ ] **Step 2: Run final fresh verification**

```powershell
cd backend
E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe -m pytest -q
cd ..\frontend
npm test -- --run
npm run build
cd ..
git diff --check
git status --short --branch
```

Re-run the GLB inspector, download API check, and Playwright desktop/mobile overlay script from Task 7 after any review fix.

Expected: all commands exit 0, the worktree is clean, and visual checks report no browser errors.

- [ ] **Step 3: Push through Clash and update PR #1**

```powershell
git -c http.proxy=http://127.0.0.1:7897 `
  -c https.proxy=http://127.0.0.1:7897 `
  push origin codex/independent-model-demo-scenarios
```

Update PR #1 with:

- manual `scene_glb` workbench overlay;
- per-vertex UTM/WGS84/Mercator conversion;
- `1.0` terrain scale while visible and `1.35` restoration;
- real artifact load time and file size;
- backend/frontend test counts and production build;
- desktop/mobile Playwright evidence;
- confirmation that no GLB request occurs before the toggle;
- confirmation that main 8000/5173 services were not disturbed.

Preserve the feature worktree for PR review.
