import * as THREE from "three";

import { customLayerProjectionMatrix } from "./customLayerProjection";
import { DEM_TERRAIN_SOURCE_ID } from "./mapLayers";
import type { CustomLayerInterface, Map as MapInstance } from "./mapEngineTypes";
import { disposePreparedScene, type PreparedSceneGlb, type SceneGlbBounds } from "./sceneGlbAsset";

const DEFAULT_TERRAIN_EXAGGERATION = 1.35;
const TRUE_SCALE_TERRAIN_EXAGGERATION = 1;

interface ManagedCustomLayer extends CustomLayerInterface {
  cleanup(): void;
}

interface RegisteredSceneGlb {
  taskId: string;
  layerId: string;
  layer: ManagedCustomLayer;
  asset: PreparedSceneGlb;
}

const registry = new WeakMap<MapInstance, Map<string, RegisteredSceneGlb>>();
const terrainTasks = new WeakMap<MapInstance, Set<string>>();

export interface SceneGlbLayerOptions {
  onLost?: () => void;
}

export function sceneGlbLayerId(taskId: string) {
  return `scene-glb-${taskId.replace(/[^A-Za-z0-9_-]+/g, "_")}`;
}

export function addSceneGlbLayer(
  map: MapInstance,
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

export function removeSceneGlbLayer(map: MapInstance, taskId: string) {
  const registered = registry.get(map)?.get(taskId);
  if (!registered) return;
  if (map.getLayer(registered.layerId)) {
    map.removeLayer(registered.layerId);
  } else {
    registered.layer.cleanup();
  }
}

export function removeAllSceneGlbLayers(map: MapInstance) {
  const taskIds = [...(registry.get(map)?.keys() ?? [])];
  for (const taskId of taskIds) removeSceneGlbLayer(map, taskId);
}

export function focusSceneGlbLayer(map: MapInstance, taskId: string) {
  const registered = registry.get(map)?.get(taskId);
  if (!registered) return false;
  return focusSceneGlbBounds(map, [registered.asset.bounds]);
}

export function focusSceneGlbLayers(map: MapInstance, taskIds: string[]) {
  const bounds = taskIds.flatMap((taskId) => {
    const registered = registry.get(map)?.get(taskId);
    return registered ? [registered.asset.bounds] : [];
  });
  return focusSceneGlbBounds(map, bounds);
}

function focusSceneGlbBounds(map: MapInstance, bounds: SceneGlbBounds[]) {
  if (!bounds.length) return false;
  const west = Math.min(...bounds.map((item) => item.west));
  const south = Math.min(...bounds.map((item) => item.south));
  const east = Math.max(...bounds.map((item) => item.east));
  const north = Math.max(...bounds.map((item) => item.north));
  map.fitBounds(
    [[west, south], [east, north]],
    { padding: 60, pitch: 55, bearing: -25, duration: 800 }
  );
  return true;
}

export function hasSceneGlbLayer(map: MapInstance, taskId: string) {
  return registry.get(map)?.has(taskId) ?? false;
}

export function getSceneGlbTerrainTaskCount(map: MapInstance) {
  return terrainTasks.get(map)?.size ?? 0;
}

function createCustomLayer(
  map: MapInstance,
  asset: PreparedSceneGlb,
  taskId: string,
  options: SceneGlbLayerOptions
): ManagedCustomLayer {
  let camera: THREE.Camera | null = null;
  let scene: THREE.Scene | null = null;
  let renderer: THREE.WebGLRenderer | null = null;
  let mixer: THREE.AnimationMixer | null = null;
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
      scene.add(createSceneGlbLights());
      scene.add(asset.group);
      if (asset.animations.length) {
        mixer = new THREE.AnimationMixer(asset.group);
        for (const clip of asset.animations) mixer.clipAction(clip).play();
      }
      canvas = map.getCanvas();
      canvas.addEventListener("webglcontextlost", handleContextLost);
      renderer = new THREE.WebGLRenderer({ canvas, context: gl, antialias: true });
      renderer.autoClear = false;
    },
    render(_gl, renderInput) {
      if (!camera || !scene || !renderer || cleaned) return;
      const mapMatrix = new THREE.Matrix4().fromArray(customLayerProjectionMatrix(renderInput));
      const anchorMatrix = new THREE.Matrix4().makeTranslation(...asset.anchor);
      camera.projectionMatrix.copy(mapMatrix).multiply(anchorMatrix);
      mixer?.setTime(performance.now() / 1_000);
      renderer.resetState();
      renderer.render(scene, camera);
      if (mixer) map.triggerRepaint();
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
      mixer?.stopAllAction();
      if (mixer) mixer.uncacheRoot(asset.group);
      disposePreparedScene(asset);
      const registered = registry.get(map)?.get(taskId);
      if (registered?.layer === layer) registry.get(map)?.delete(taskId);
      releaseTerrainTask(map, taskId);
      camera = null;
      scene = null;
      renderer = null;
      mixer = null;
      canvas = null;
    }
  };
  return layer;
}

export function createSceneGlbLights() {
  const lights = new THREE.Group();
  lights.name = "scene-glb-baseline-lights";
  const hemisphere = new THREE.HemisphereLight(0xffffff, 0x52606b, 1.35);
  const directional = new THREE.DirectionalLight(0xffffff, 1.6);
  directional.position.set(0.6, 1, 0.4);
  lights.add(hemisphere, directional);
  return lights;
}

function sceneRegistry(map: MapInstance) {
  let entries = registry.get(map);
  if (!entries) {
    entries = new Map();
    registry.set(map, entries);
  }
  return entries;
}

function terrainTaskSet(map: MapInstance) {
  let tasks = terrainTasks.get(map);
  if (!tasks) {
    tasks = new Set();
    terrainTasks.set(map, tasks);
  }
  return tasks;
}

function releaseTerrainTask(map: MapInstance, taskId: string) {
  const tasks = terrainTasks.get(map);
  if (!tasks?.delete(taskId)) return;
  if (tasks.size === 0) {
    applyTerrainScale(map, DEFAULT_TERRAIN_EXAGGERATION, false);
  }
}

function firstSymbolLayerId(map: MapInstance) {
  return map.getStyle().layers?.find((layer) => layer.type === "symbol")?.id;
}

function applyTerrainScale(
  map: MapInstance,
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
