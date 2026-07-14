import maplibregl from "maplibre-gl";
import * as THREE from "three";

import { DEM_TERRAIN_SOURCE_ID } from "./mapLayers";
import { disposePreparedScene, type PreparedSceneGlb } from "./sceneGlbAsset";

const DEFAULT_TERRAIN_EXAGGERATION = 1.35;
const TRUE_SCALE_TERRAIN_EXAGGERATION = 1;

interface ManagedCustomLayer extends maplibregl.CustomLayerInterface {
  cleanup(): void;
}

interface RegisteredSceneGlb {
  taskId: string;
  layerId: string;
  layer: ManagedCustomLayer;
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

export function addSceneGlbLayer(
  map: maplibregl.Map,
  taskId: string,
  asset: PreparedSceneGlb,
  options: SceneGlbLayerOptions = {}
) {
  removeSceneGlbLayer(map, taskId);
  try {
    applyTerrainScale(map, TRUE_SCALE_TERRAIN_EXAGGERATION, true);
  } catch (error) {
    disposePreparedScene(asset);
    throw error;
  }

  const tasks = terrainTaskSet(map);
  tasks.add(taskId);
  const layerId = sceneGlbLayerId(taskId);
  const layer = createCustomLayer(map, asset, taskId, options);
  const registered: RegisteredSceneGlb = { taskId, layerId, layer, asset };
  sceneRegistry(map).set(taskId, registered);

  try {
    map.addLayer(layer, firstSymbolLayerId(map));
  } catch (error) {
    layer.cleanup();
    throw error;
  }
}

export function removeSceneGlbLayer(map: maplibregl.Map, taskId: string) {
  const registered = registry.get(map)?.get(taskId);
  if (!registered) return;
  if (map.getLayer(registered.layerId)) {
    map.removeLayer(registered.layerId);
  } else {
    registered.layer.cleanup();
  }
}

export function removeAllSceneGlbLayers(map: maplibregl.Map) {
  const taskIds = [...(registry.get(map)?.keys() ?? [])];
  for (const taskId of taskIds) removeSceneGlbLayer(map, taskId);
}

export function focusSceneGlbLayer(map: maplibregl.Map, taskId: string) {
  const registered = registry.get(map)?.get(taskId);
  if (!registered) return false;
  const { west, south, east, north } = registered.asset.bounds;
  map.fitBounds(
    [[west, south], [east, north]],
    { padding: 60, pitch: 55, bearing: -25, duration: 800 }
  );
  return true;
}

export function hasSceneGlbLayer(map: maplibregl.Map, taskId: string) {
  return registry.get(map)?.has(taskId) ?? false;
}

export function getSceneGlbTerrainTaskCount(map: maplibregl.Map) {
  return terrainTasks.get(map)?.size ?? 0;
}

function createCustomLayer(
  map: maplibregl.Map,
  asset: PreparedSceneGlb,
  taskId: string,
  options: SceneGlbLayerOptions
): ManagedCustomLayer {
  let camera: THREE.Camera | null = null;
  let scene: THREE.Scene | null = null;
  let renderer: THREE.WebGLRenderer | null = null;
  let canvas: HTMLCanvasElement | null = null;
  let contextLostQueued = false;
  let cleaned = false;

  const handleContextLost = (event: Event) => {
    event.preventDefault();
    if (contextLostQueued) return;
    contextLostQueued = true;
    queueMicrotask(() => {
      removeSceneGlbLayer(map, taskId);
      options.onLost?.();
    });
  };

  const layer: ManagedCustomLayer = {
    id: sceneGlbLayerId(taskId),
    type: "custom",
    renderingMode: "3d",
    onAdd(_map, gl) {
      if (cleaned) return;
      camera = new THREE.Camera();
      scene = new THREE.Scene();
      scene.add(asset.group);
      canvas = map.getCanvas();
      canvas.addEventListener("webglcontextlost", handleContextLost);
      renderer = new THREE.WebGLRenderer({ canvas, context: gl, antialias: true });
      renderer.autoClear = false;
    },
    render(_gl, matrix) {
      if (!camera || !scene || !renderer || cleaned) return;
      const mapMatrix = new THREE.Matrix4().fromArray(matrix as unknown as number[]);
      const anchorMatrix = new THREE.Matrix4().makeTranslation(...asset.anchor);
      camera.projectionMatrix.copy(mapMatrix).multiply(anchorMatrix);
      renderer.resetState();
      renderer.render(scene, camera);
    },
    onRemove() {
      layer.cleanup();
    },
    cleanup() {
      if (cleaned) return;
      cleaned = true;
      canvas?.removeEventListener("webglcontextlost", handleContextLost);
      scene?.remove(asset.group);
      renderer?.dispose();
      disposePreparedScene(asset);
      const registered = registry.get(map)?.get(taskId);
      if (registered?.layer === layer) registry.get(map)?.delete(taskId);
      releaseTerrainTask(map, taskId);
      camera = null;
      scene = null;
      renderer = null;
      canvas = null;
    }
  };
  return layer;
}

function sceneRegistry(map: maplibregl.Map) {
  let entries = registry.get(map);
  if (!entries) {
    entries = new Map();
    registry.set(map, entries);
  }
  return entries;
}

function terrainTaskSet(map: maplibregl.Map) {
  let tasks = terrainTasks.get(map);
  if (!tasks) {
    tasks = new Set();
    terrainTasks.set(map, tasks);
  }
  return tasks;
}

function releaseTerrainTask(map: maplibregl.Map, taskId: string) {
  const tasks = terrainTasks.get(map);
  if (!tasks?.delete(taskId)) return;
  if (tasks.size === 0) {
    applyTerrainScale(map, DEFAULT_TERRAIN_EXAGGERATION, false);
  }
}

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
