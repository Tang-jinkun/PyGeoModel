import * as THREE from "three";

import { customLayerProjectionMatrix } from "./customLayerProjection";
import { DEM_TERRAIN_SOURCE_ID } from "./mapLayers";
import type { CustomLayerInterface, Map as MapInstance } from "./mapEngineTypes";
import type { RadarGridDensity } from "./radarVolumeLayer";
import {
  applyPreparedSceneColor,
  disposePreparedScene,
  restorePreparedSceneColors,
  type PreparedSceneGlb,
  type SceneGlbBounds
} from "./sceneGlbAsset";

const DEFAULT_TERRAIN_EXAGGERATION = 1.35;
const TRUE_SCALE_TERRAIN_EXAGGERATION = 1;

interface ManagedCustomLayer extends CustomLayerInterface {
  cleanup(): void;
  setGridDensity(density: RadarGridDensity): void;
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
  foreground?: boolean;
  gridDensity?: RadarGridDensity;
  onLost?: () => void;
}

export type SceneGlbGridLod = Exclude<RadarGridDensity, "auto"> | "hidden";

const RADAR_GRID_NAMES = {
  sparse: "radar_result/shell_grid_sparse",
  standard: "radar_result/shell_grid",
  detailed: "radar_result/shell_grid_detailed"
} as const;

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

export function resolveSceneGlbGridLod(
  density: RadarGridDensity,
  zoom: number
): SceneGlbGridLod {
  if (density !== "auto") return density;
  if (zoom < 7) return "hidden";
  if (zoom < 9) return "sparse";
  if (zoom < 12) return "standard";
  return "detailed";
}

export function setSceneGlbLayerGridDensity(
  map: MapInstance,
  taskId: string,
  density: RadarGridDensity
) {
  const layer = registry.get(map)?.get(taskId)?.layer;
  if (!layer) return false;
  layer.setGridDensity(density);
  return true;
}

export function setAllSceneGlbLayerGridDensity(
  map: MapInstance,
  density: RadarGridDensity
) {
  for (const registered of registry.get(map)?.values() ?? []) {
    registered.layer.setGridDensity(density);
  }
}

export function setSceneGlbLayerColor(
  map: MapInstance,
  taskId: string,
  color: string,
  referenceColor?: string
) {
  const asset = registry.get(map)?.get(taskId)?.asset;
  if (!asset) return false;
  applyPreparedSceneColor(asset, color, referenceColor);
  map.triggerRepaint();
  return true;
}

export function restoreSceneGlbLayerColors(map: MapInstance, taskId: string) {
  const asset = registry.get(map)?.get(taskId)?.asset;
  if (!asset) return false;
  restorePreparedSceneColors(asset);
  map.triggerRepaint();
  return true;
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
  let gridDensity = options.gridDensity ?? "auto";
  let currentGridLod: SceneGlbGridLod | null = null;
  const gridMeshes = findRadarGridMeshes(asset.group);

  const updateGridLod = () => {
    const nextLod = resolveSceneGlbGridLod(gridDensity, map.getZoom());
    if (nextLod === currentGridLod) return;
    applyRadarGridLod(gridMeshes, nextLod);
    currentGridLod = nextLod;
  };

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
      updateGridLod();
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
      updateGridLod();
      const mapMatrix = new THREE.Matrix4().fromArray(customLayerProjectionMatrix(renderInput));
      const anchorMatrix = new THREE.Matrix4().makeTranslation(...asset.anchor);
      camera.projectionMatrix.copy(mapMatrix).multiply(anchorMatrix);
      mixer?.setTime(performance.now() / 1_000);
      renderer.resetState();
      if (options.foreground) renderer.clearDepth();
      renderer.render(scene, camera);
      if (mixer) map.triggerRepaint();
    },
    onRemove() {
      layer.cleanup();
    },
    setGridDensity(density) {
      if (gridDensity === density) return;
      gridDensity = density;
      const nextLod = resolveSceneGlbGridLod(gridDensity, map.getZoom());
      if (nextLod === currentGridLod) return;
      updateGridLod();
      map.triggerRepaint();
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

interface RadarGridMeshes {
  sparse: THREE.Object3D | null;
  standard: THREE.Object3D | null;
  detailed: THREE.Object3D | null;
}

function findRadarGridMeshes(group: THREE.Group): RadarGridMeshes {
  return {
    sparse: group.getObjectByName(RADAR_GRID_NAMES.sparse) ?? null,
    standard: group.getObjectByName(RADAR_GRID_NAMES.standard) ?? null,
    detailed: group.getObjectByName(RADAR_GRID_NAMES.detailed) ?? null
  };
}

function applyRadarGridLod(meshes: RadarGridMeshes, lod: SceneGlbGridLod) {
  const available = [...new Set(Object.values(meshes).filter((mesh) => mesh !== null))];
  if (!available.length) return;
  for (const mesh of available) mesh.visible = false;
  if (lod === "hidden") return;
  const target = meshes[lod] ?? meshes.standard ?? meshes.sparse ?? meshes.detailed;
  if (!target) return;
  target.visible = true;
  const opacity = target.userData.grid_opacity;
  if (typeof opacity !== "number" || !Number.isFinite(opacity)) return;
  const materials = target instanceof THREE.Mesh
    ? Array.isArray(target.material) ? target.material : [target.material]
    : [];
  for (const material of materials) {
    material.opacity = Math.min(1, Math.max(0, opacity));
    material.transparent = material.opacity < 1;
    material.needsUpdate = true;
  }
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
