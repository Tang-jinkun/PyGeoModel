import * as THREE from "three";
import { afterEach, describe, expect, it, vi } from "vitest";
import proj4 from "proj4";

import {
  disposePreparedScene,
  fetchSceneGlb,
  inheritedUserData,
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
  it("merges inherited user data from root to leaf with child keys winning", () => {
    const root = new THREE.Group();
    root.userData = { kind: "scene", task_id: "task-a" };
    const unit = new THREE.Group();
    unit.userData = { kind: "unit", unit_id: "ad-05", status: "active" };
    const material = new THREE.MeshStandardMaterial({ color: 0x777777 });
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(100, 40, 60), material);
    mesh.userData = { kind: "unit_component", role: "body" };
    unit.add(mesh);
    root.add(unit);

    expect(inheritedUserData(mesh, root)).toEqual({
      kind: "unit_component",
      task_id: "task-a",
      unit_id: "ad-05",
      status: "active",
      role: "body"
    });

    const asset = prepareStaticScene(root, metadata, []);
    const flattened = asset.group.children[0] as THREE.Mesh;

    expect(flattened.userData).toEqual({
      kind: "unit_component",
      task_id: "task-a",
      unit_id: "ad-05",
      status: "active",
      role: "body"
    });
    expect(flattened.material).toBe(material);
  });

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

  it("retains standard animations while rejecting skinned meshes", () => {
    const root = new THREE.Group();
    root.add(new THREE.Mesh(new THREE.BoxGeometry(), new THREE.MeshBasicMaterial()));
    const animation = new THREE.AnimationClip("radar_scan", 8, []);

    const animated = prepareStaticScene(root, metadata, [animation]);

    expect(animated.animations).toEqual([animation]);
    const skinnedRoot = new THREE.Group();
    skinnedRoot.add(new THREE.SkinnedMesh(new THREE.BoxGeometry(), new THREE.MeshBasicMaterial()));
    expect(() => prepareStaticScene(skinnedRoot, metadata, [])).toThrow("skinned");
  });

  it("preserves effective visibility when flattening a hidden parent", () => {
    const root = new THREE.Group();
    const hiddenParent = new THREE.Group();
    hiddenParent.visible = false;
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(), new THREE.MeshBasicMaterial());
    mesh.name = "hidden-child";
    hiddenParent.add(mesh);
    root.add(hiddenParent);

    const asset = prepareStaticScene(root, metadata, []);

    expect(asset.group.getObjectByName("hidden-child")?.visible).toBe(false);
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

  it.each([
    { zone: 60, originLongitude: 179.9, vertexLongitude: -179.9 },
    { zone: 1, originLongitude: -179.9, vertexLongitude: 179.9 }
  ])(
    "keeps zone $zone antimeridian vertices and focus bounds in one world copy",
    ({ zone, originLongitude, vertexLongitude }) => {
      const definition = utmDefinition(zone);
      const forward = proj4("EPSG:4326", definition);
      const [originX, originY] = forward.forward([originLongitude, 10]);
      const [vertexX, vertexY] = forward.forward([vertexLongitude, 10]);
      const [northX, northY] = forward.forward([vertexLongitude, 10.01]);
      const antimeridianMetadata: Scene3dMetadata = {
        ...metadata,
        source_crs: `EPSG:326${String(zone).padStart(2, "0")}`,
        origin: {
          projected_x: originX,
          projected_y: originY,
          longitude: originLongitude,
          latitude: 10,
          altitude_amsl_m: 0
        }
      };
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.Float32BufferAttribute([
        0, 0, 0,
        vertexX - originX, 0, -(vertexY - originY),
        northX - originX, 100, -(northY - originY)
      ], 3));
      geometry.setIndex([0, 1, 2]);
      const root = new THREE.Group();
      root.add(new THREE.Mesh(geometry, new THREE.MeshBasicMaterial()));

      const asset = prepareStaticScene(root, antimeridianMetadata, []);
      const prepared = asset.group.children[0] as THREE.Mesh;
      const positions = prepared.geometry.getAttribute("position");
      const projectedXs = Array.from(
        { length: positions.count },
        (_value, index) => positions.getX(index)
      );

      expect(asset.bounds.east - asset.bounds.west).toBeLessThan(1);
      expect(Math.max(...projectedXs) - Math.min(...projectedXs)).toBeLessThan(0.01);
    }
  );
});

function utmDefinition(zone: number) {
  return `+proj=utm +zone=${zone} +datum=WGS84 +units=m +no_defs`;
}
