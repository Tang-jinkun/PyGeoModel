import * as THREE from "three";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  disposePreparedScene,
  fetchSceneGlb,
  prepareStaticScene
} from "./sceneGlbAsset";
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

afterEach(() => {
  vi.unstubAllGlobals();
});

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
    expect(() => prepareStaticScene(
      new THREE.Group(),
      metadata,
      [new THREE.AnimationClip("move", 1, [])]
    )).toThrow("animated");
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

  it("rejects files above 50 MB before parsing", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(new Uint8Array(1), {
      headers: { "Content-Length": "50000001" }
    })));

    await expect(fetchSceneGlb("/large.glb", new AbortController().signal))
      .rejects.toThrow("50 MB");
  });

  it("reports streamed byte progress for files above the progress threshold", async () => {
    const bytes = new Uint8Array(15_000_001);
    const progress = vi.fn();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(bytes, {
      headers: { "Content-Length": String(bytes.byteLength) }
    })));

    const buffer = await fetchSceneGlb(
      "/scene.glb",
      new AbortController().signal,
      progress
    );

    expect(buffer.byteLength).toBe(bytes.byteLength);
    expect(progress).toHaveBeenLastCalledWith({
      loaded: bytes.byteLength,
      total: bytes.byteLength
    });
  });

  it("does not report progress for small files with a known length", async () => {
    const progress = vi.fn();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(new Uint8Array([1, 2, 3]), {
      headers: { "Content-Length": "3" }
    })));

    const buffer = await fetchSceneGlb(
      "/small.glb",
      new AbortController().signal,
      progress
    );

    expect(buffer.byteLength).toBe(3);
    expect(progress).not.toHaveBeenCalled();
  });
});
