import * as THREE from "three";
import { describe, expect, it, vi } from "vitest";

import { DEM_TERRAIN_SOURCE_ID } from "./mapLayers";
import type { PreparedSceneGlb } from "./sceneGlbAsset";
import {
  addSceneGlbLayer,
  focusSceneGlbLayer,
  getSceneGlbTerrainTaskCount,
  hasSceneGlbLayer,
  removeAllSceneGlbLayers,
  removeSceneGlbLayer,
  createSceneGlbLights,
  sceneGlbLayerId
} from "./sceneGlbLayer";

vi.mock("three", async () => {
  const actual = await vi.importActual<typeof import("three")>("three");
  return {
    ...actual,
    WebGLRenderer: class {
      autoClear = true;
      resetState = vi.fn();
      render = vi.fn();
      dispose = vi.fn();
    }
  };
});

describe("scene GLB map layer", () => {
  it("creates neutral baseline lights for the custom scene", () => {
    const lights = createSceneGlbLights();

    expect(lights.children).toHaveLength(2);
    expect(lights.name).toBe("scene-glb-baseline-lights");
    expect(lights.children[0]).toBeInstanceOf(THREE.HemisphereLight);
    expect(lights.children[1]).toBeInstanceOf(THREE.DirectionalLight);

    const hemisphere = lights.children[0] as THREE.HemisphereLight;
    const directional = lights.children[1] as THREE.DirectionalLight;
    expect(hemisphere.color.getHex()).toBe(0xffffff);
    expect(hemisphere.groundColor.getHex()).toBe(0x52606b);
    expect(hemisphere.intensity).toBe(1.35);
    expect(directional.color.getHex()).toBe(0xffffff);
    expect(directional.intensity).toBe(1.6);
    expect(directional.position.toArray()).toEqual([0.6, 1, 0.4]);
  });

  it("keeps terrain at true scale until the final task is removed", () => {
    const map = new FakeMap();
    const first = preparedAsset("task-a");
    const second = preparedAsset("task-b");

    addSceneGlbLayer(map as never, "task-a", first);
    addSceneGlbLayer(map as never, "task-b", second);

    expect(map.layers.get("scene-glb-task-a")?.renderingMode).toBe("3d");
    expect(map.setTerrain).toHaveBeenLastCalledWith({
      source: DEM_TERRAIN_SOURCE_ID,
      exaggeration: 1
    });
    expect(getSceneGlbTerrainTaskCount(map as never)).toBe(2);

    removeSceneGlbLayer(map as never, "task-a");
    expect(getSceneGlbTerrainTaskCount(map as never)).toBe(1);
    expect(map.setTerrain).toHaveBeenLastCalledWith({
      source: DEM_TERRAIN_SOURCE_ID,
      exaggeration: 1
    });

    removeSceneGlbLayer(map as never, "task-b");
    expect(map.setTerrain).toHaveBeenLastCalledWith({
      source: DEM_TERRAIN_SOURCE_ID,
      exaggeration: 1.35
    });
    expect(first.disposed).toBe(true);
    expect(second.disposed).toBe(true);
  });

  it("adds the baseline lights before the asset group in the custom scene", () => {
    const map = new FakeMap();
    const sceneAdd = vi.spyOn(THREE.Scene.prototype, "add");
    const asset = preparedAsset("task-a");

    try {
      addSceneGlbLayer(map as never, "task-a", asset);

      const [firstCall, secondCall] = sceneAdd.mock.calls as Array<[THREE.Group]>;
      expect(firstCall[0]).toBeInstanceOf(THREE.Group);
      expect(firstCall[0].name).toBe("scene-glb-baseline-lights");
      expect(firstCall[0].children[0]).toBeInstanceOf(THREE.HemisphereLight);
      expect(firstCall[0].children[1]).toBeInstanceOf(THREE.DirectionalLight);
      expect(secondCall[0]).toBe(asset.group);
    } finally {
      sceneAdd.mockRestore();
    }
  });

  it("focuses transformed WGS84 bounds with a stable 3D camera", () => {
    const map = new FakeMap();
    addSceneGlbLayer(map as never, "task-a", preparedAsset("task-a"));

    expect(focusSceneGlbLayer(map as never, "task-a")).toBe(true);
    expect(map.fitBounds).toHaveBeenCalledWith(
      [[79, 31.4], [80, 31.6]],
      { padding: 60, pitch: 55, bearing: -25, duration: 800 }
    );
  });

  it("replaces the same task, removes all tasks, and makes removal idempotent", () => {
    const map = new FakeMap();
    const replaced = preparedAsset("task-a");
    const replacement = preparedAsset("task-a");
    addSceneGlbLayer(map as never, "task-a", replaced);
    addSceneGlbLayer(map as never, "task-a", replacement);
    addSceneGlbLayer(map as never, "task-b", preparedAsset("task-b"));

    expect(replaced.disposed).toBe(true);
    expect(getSceneGlbTerrainTaskCount(map as never)).toBe(2);
    removeAllSceneGlbLayers(map as never);
    removeSceneGlbLayer(map as never, "task-a");

    expect(replacement.disposed).toBe(true);
    expect(getSceneGlbTerrainTaskCount(map as never)).toBe(0);
    expect(hasSceneGlbLayer(map as never, "task-a")).toBe(false);
  });

  it("inserts before the first symbol layer and sanitizes the task id", () => {
    const map = new FakeMap();
    addSceneGlbLayer(map as never, "task/a:1", preparedAsset("task/a:1"));

    expect(sceneGlbLayerId("task/a:1")).toBe("scene-glb-task_a_1");
    expect(map.addLayer).toHaveBeenCalledWith(
      expect.objectContaining({ id: "scene-glb-task_a_1" }),
      "place-label"
    );
  });

  it("disposes and refuses registration when DEM terrain is unavailable", () => {
    const map = new FakeMap(false);
    const asset = preparedAsset("task-a");

    expect(() => addSceneGlbLayer(map as never, "task-a", asset))
      .toThrow("DEM terrain is not ready");
    expect(asset.disposed).toBe(true);
    expect(hasSceneGlbLayer(map as never, "task-a")).toBe(false);
    expect(map.addLayer).not.toHaveBeenCalled();
  });

  it("remains harmless when terrain disappears before layer cleanup", () => {
    const map = new FakeMap();
    addSceneGlbLayer(map as never, "task-a", preparedAsset("task-a"));
    map.hasTerrainSource = false;

    expect(() => removeSceneGlbLayer(map as never, "task-a")).not.toThrow();
    expect(getSceneGlbTerrainTaskCount(map as never)).toBe(0);
  });

  it("disposes the asset and shared material once when a layer is removed twice", () => {
    const map = new FakeMap();
    const material = new THREE.MeshStandardMaterial();
    const asset = preparedAsset("task-a", material);
    const materialDispose = vi.spyOn(material, "dispose");

    addSceneGlbLayer(map as never, "task-a", asset);
    removeSceneGlbLayer(map as never, "task-a");
    removeSceneGlbLayer(map as never, "task-a");

    expect(asset.disposed).toBe(true);
    expect(materialDispose).toHaveBeenCalledOnce();
  });

  it("removes a lost WebGL layer and allows a manual retry", async () => {
    const map = new FakeMap();
    const onLost = vi.fn();
    addSceneGlbLayer(map as never, "task-a", preparedAsset("task-a"), { onLost });
    const event = new Event("webglcontextlost", { cancelable: true });

    map.canvas.dispatchEvent(event);
    await Promise.resolve();

    expect(event.defaultPrevented).toBe(true);
    expect(onLost).toHaveBeenCalledOnce();
    expect(hasSceneGlbLayer(map as never, "task-a")).toBe(false);
    expect(() => addSceneGlbLayer(map as never, "task-a", preparedAsset("task-a")))
      .not.toThrow();
  });
});

function preparedAsset(taskId: string, material: THREE.Material = new THREE.MeshBasicMaterial()): PreparedSceneGlb {
  const group = new THREE.Group();
  group.add(new THREE.Mesh(new THREE.BoxGeometry(), material));
  return {
    group,
    anchor: [0.5, 0.4, 0.0001],
    bounds: {
      west: 79,
      south: 31.4,
      east: 80,
      north: 31.6,
      minAltitudeM: 5000,
      maxAltitudeM: 6000
    },
    metadata: {
      schema_version: 1,
      task_id: taskId,
      model_id: "air_corridor",
      units: "metre",
      source_crs: "EPSG:32644",
      geographic_crs: "EPSG:4326",
      origin: {
        projected_x: 0,
        projected_y: 0,
        longitude: 79,
        latitude: 31.4,
        altitude_amsl_m: 5000
      },
      axes: { x: "east", y: "up", z: "south" }
    },
    disposed: false
  };
}

class FakeMap {
  layers = new Map<string, Record<string, unknown>>();
  canvas = document.createElement("canvas");
  setTerrain = vi.fn();
  fitBounds = vi.fn();
  hasTerrainSource: boolean;

  constructor(hasTerrainSource = true) {
    this.hasTerrainSource = hasTerrainSource;
  }

  getSource = vi.fn((id: string) => (
    id === DEM_TERRAIN_SOURCE_ID && this.hasTerrainSource ? {} : undefined
  ));

  getStyle = vi.fn(() => ({
    layers: [
      { id: "background", type: "background" },
      { id: "place-label", type: "symbol" }
    ]
  }));

  getCanvas = vi.fn(() => this.canvas);
  getLayer = vi.fn((id: string) => this.layers.get(id));

  addLayer = vi.fn((layer: Record<string, unknown>, _before?: string) => {
    this.layers.set(layer.id as string, layer);
    const onAdd = layer.onAdd as ((map: FakeMap, gl: WebGLRenderingContext) => void) | undefined;
    onAdd?.(this, {} as WebGLRenderingContext);
  });

  removeLayer = vi.fn((id: string) => {
    const layer = this.layers.get(id);
    if (!layer) return;
    this.layers.delete(id);
    const onRemove = layer.onRemove as ((map: FakeMap, gl: WebGLRenderingContext) => void) | undefined;
    onRemove?.(this, {} as WebGLRenderingContext);
  });
}
