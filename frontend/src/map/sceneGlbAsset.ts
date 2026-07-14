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

export interface SceneGlbProgress {
  loaded: number;
  total: number | null;
}

export const SCENE_GLB_PREVIEW_MAX_BYTES = 50_000_000;
export const SCENE_GLB_PROGRESS_THRESHOLD_BYTES = 15_000_000;

export async function fetchSceneGlb(
  url: string,
  signal: AbortSignal,
  onProgress?: (progress: SceneGlbProgress) => void
): Promise<ArrayBuffer> {
  const response = await fetch(url, { signal });
  if (!response.ok) {
    throw new Error(`GLB request failed with HTTP ${response.status}`);
  }
  const total = parseContentLength(response.headers.get("Content-Length"));
  if (total !== null && total > SCENE_GLB_PREVIEW_MAX_BYTES) {
    throw new Error("GLB file exceeds the 50 MB preview limit");
  }
  const reportProgress = total === null || total > SCENE_GLB_PROGRESS_THRESHOLD_BYTES;

  if (!response.body) {
    const buffer = await response.arrayBuffer();
    assertPreviewSize(buffer.byteLength);
    if (reportProgress) onProgress?.({ loaded: buffer.byteLength, total });
    return buffer;
  }

  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let loaded = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    loaded += value.byteLength;
    if (loaded > SCENE_GLB_PREVIEW_MAX_BYTES) {
      await reader.cancel();
      throw new Error("GLB file exceeds the 50 MB preview limit");
    }
    chunks.push(value);
    if (reportProgress) onProgress?.({ loaded, total });
  }

  const buffer = new Uint8Array(loaded);
  let offset = 0;
  for (const chunk of chunks) {
    buffer.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return buffer.buffer;
}

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

export function prepareStaticScene(
  root: THREE.Object3D,
  metadata: Scene3dMetadata,
  animations: readonly THREE.AnimationClip[]
): PreparedSceneGlb {
  if (animations.length > 0) {
    throw new Error("GLB preview does not support animated scenes");
  }
  root.updateMatrixWorld(true);
  let hasSkinnedMesh = false;
  root.traverse((object) => {
    if (object instanceof THREE.SkinnedMesh) hasSkinnedMesh = true;
  });
  if (hasSkinnedMesh) {
    throw new Error("GLB preview does not support skinned meshes");
  }

  const reference = createSceneGeoReference(metadata);
  const group = new THREE.Group();
  const bounds: SceneGlbBounds = {
    west: Infinity,
    south: Infinity,
    east: -Infinity,
    north: -Infinity,
    minAltitudeM: Infinity,
    maxAltitudeM: -Infinity
  };
  let vertexCount = 0;

  root.traverse((object) => {
    if (!(object instanceof THREE.Mesh)) return;
    const geometry = object.geometry.clone();
    geometry.applyMatrix4(object.matrixWorld);
    const positions = geometry.getAttribute("position");
    if (!positions) {
      geometry.dispose();
      return;
    }
    for (let index = 0; index < positions.count; index += 1) {
      const result = reference.project([
        positions.getX(index),
        positions.getY(index),
        positions.getZ(index)
      ]);
      positions.setXYZ(index, ...result.mercator);
      bounds.west = Math.min(bounds.west, result.longitude);
      bounds.south = Math.min(bounds.south, result.latitude);
      bounds.east = Math.max(bounds.east, result.longitude);
      bounds.north = Math.max(bounds.north, result.latitude);
      bounds.minAltitudeM = Math.min(bounds.minAltitudeM, result.altitudeAmslM);
      bounds.maxAltitudeM = Math.max(bounds.maxAltitudeM, result.altitudeAmslM);
      vertexCount += 1;
    }
    positions.needsUpdate = true;
    geometry.computeBoundingBox();
    geometry.computeBoundingSphere();
    geometry.computeVertexNormals();

    const mesh = new THREE.Mesh(geometry, object.material);
    mesh.name = object.name;
    mesh.userData = { ...object.userData };
    mesh.renderOrder = object.renderOrder;
    mesh.visible = object.visible;
    group.add(mesh);
  });

  if (vertexCount === 0 || !Object.values(bounds).every(Number.isFinite)) {
    group.traverse((object) => {
      if (object instanceof THREE.Mesh) object.geometry.dispose();
    });
    throw new Error("GLB scene does not contain finite mesh vertices");
  }

  return {
    group,
    anchor: [reference.anchor.x, reference.anchor.y, reference.anchor.z],
    bounds,
    metadata,
    disposed: false
  };
}

export function disposePreparedScene(asset: PreparedSceneGlb) {
  if (asset.disposed) return;
  asset.disposed = true;
  const geometries = new Set<THREE.BufferGeometry>();
  const materials = new Set<THREE.Material>();
  const textures = new Set<THREE.Texture>();

  asset.group.traverse((object) => {
    if (!(object instanceof THREE.Mesh)) return;
    geometries.add(object.geometry);
    const meshMaterials = Array.isArray(object.material)
      ? object.material
      : [object.material];
    for (const material of meshMaterials) {
      materials.add(material);
      collectMaterialTextures(material, textures);
    }
  });

  for (const geometry of geometries) geometry.dispose();
  for (const texture of textures) texture.dispose();
  for (const material of materials) material.dispose();
  asset.group.clear();
}

function parseGltf(buffer: ArrayBuffer): Promise<GLTF> {
  return new Promise((resolve, reject) => {
    new GLTFLoader().parse(buffer, "", resolve, reject);
  });
}

function collectMaterialTextures(material: THREE.Material, textures: Set<THREE.Texture>) {
  for (const value of Object.values(material)) {
    if (value instanceof THREE.Texture) textures.add(value);
  }
  if (material instanceof THREE.ShaderMaterial) {
    for (const uniform of Object.values(material.uniforms)) {
      collectTextureValue(uniform.value, textures);
    }
  }
}

function collectTextureValue(value: unknown, textures: Set<THREE.Texture>) {
  if (value instanceof THREE.Texture) {
    textures.add(value);
  } else if (Array.isArray(value)) {
    for (const item of value) collectTextureValue(item, textures);
  }
}

function parseContentLength(value: string | null): number | null {
  if (value === null) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : null;
}

function assertPreviewSize(size: number) {
  if (size > SCENE_GLB_PREVIEW_MAX_BYTES) {
    throw new Error("GLB file exceeds the 50 MB preview limit");
  }
}
