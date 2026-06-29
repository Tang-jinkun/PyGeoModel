import * as maplibregl from "maplibre-gl";
import * as THREE from "three";

const VOXEL_LAYER_ID = "voxel-layer";
const VOXEL_LEGACY_LAYER_PREFIX = `${VOXEL_LAYER_ID}-`;
let activeVoxelLayer: VoxelCustomLayer | null = null;

export interface VoxelPoint {
  x: number;
  y: number;
  z: number;
  clearance: number;
}

interface VoxelManifest {
  grid_size: number;
  vertical_levels: number;
  max_height_m: number;
  max_elevation_deg: number;
  point_count: number;
  point_format: string;
  fields: string[];
  bytes_per_point: number;
}

type VoxelCustomLayer = maplibregl.CustomLayerInterface & {
  update: (points: VoxelPoint[], options?: VoxelRenderOptions) => void;
};

interface VoxelRenderOptions {
  opacity: number;
}

interface VoxelState {
  map: maplibregl.Map | null;
  camera: THREE.Camera | null;
  scene: THREE.Scene | null;
  renderer: THREE.WebGLRenderer | null;
  points: VoxelPoint[];
  options: VoxelRenderOptions;
  pointCloud: THREE.Points | null;
}

export function addOrUpdateVoxelLayer(map: maplibregl.Map, points: VoxelPoint[], options?: Partial<VoxelRenderOptions>) {
  const renderOptions = normalizeOptions(options);
  if (activeVoxelLayer?.id === VOXEL_LAYER_ID && map.getLayer(VOXEL_LAYER_ID)) {
    activeVoxelLayer.update(points, renderOptions);
    return;
  }
  removeVoxelLayer(map);
  activeVoxelLayer = createVoxelLayer(points, renderOptions);
  map.addLayer(activeVoxelLayer);
}

export function removeVoxelLayer(map: maplibregl.Map) {
  removeLayerIfPresent(map, VOXEL_LAYER_ID);
  for (const layer of map.getStyle().layers ?? []) {
    if (layer.id.startsWith(VOXEL_LEGACY_LAYER_PREFIX)) {
      removeLayerIfPresent(map, layer.id);
    }
  }
  activeVoxelLayer = null;
}

function removeLayerIfPresent(map: maplibregl.Map, layerId: string) {
  if (map.getLayer(layerId)) {
    map.removeLayer(layerId);
  }
}

function createVoxelLayer(initialPoints: VoxelPoint[], initialOptions: VoxelRenderOptions): VoxelCustomLayer {
  const state: VoxelState = {
    map: null,
    camera: null,
    scene: null,
    renderer: null,
    points: initialPoints,
    options: initialOptions,
    pointCloud: null,
  };

  return {
    id: VOXEL_LAYER_ID,
    type: "custom",
    renderingMode: "3d",
    onAdd(map, gl) {
      state.map = map;
      state.camera = new THREE.Camera();
      state.scene = new THREE.Scene();
      state.renderer = new THREE.WebGLRenderer({
        canvas: map.getCanvas(),
        context: gl,
        antialias: true,
      });
      state.renderer.autoClear = false;
      rebuildPointCloud(state);
    },
    render(_gl, matrix) {
      if (!state.map || !state.camera || !state.scene || !state.renderer) {
        return;
      }
      state.camera.projectionMatrix = new THREE.Matrix4().fromArray(matrix as number[]);
      state.renderer.resetState();
      state.renderer.render(state.scene, state.camera);
      state.map.triggerRepaint();
    },
    onRemove() {
      disposePointCloud(state);
      state.renderer?.dispose();
      state.map = null;
      state.camera = null;
      state.scene = null;
      state.renderer = null;
    },
    update(points: VoxelPoint[], options?: VoxelRenderOptions) {
      state.points = points;
      if (options) {
        state.options = options;
      }
      rebuildPointCloud(state);
      state.map?.triggerRepaint();
    },
  };
}

function rebuildPointCloud(state: VoxelState) {
  if (!state.scene) {
    return;
  }
  disposePointCloud(state);
  if (state.points.length === 0) {
    return;
  }

  const positions = new Float32Array(state.points.length * 3);
  const colors = new Float32Array(state.points.length * 3);

  for (let i = 0; i < state.points.length; i++) {
    const pt = state.points[i];
    const coordinate = maplibregl.MercatorCoordinate.fromLngLat({ lng: pt.x, lat: pt.y }, pt.z);
    positions[i * 3] = coordinate.x;
    positions[i * 3 + 1] = coordinate.y;
    positions[i * 3 + 2] = coordinate.z;

    // Color based on clearance: low clearance = warm (red/orange), high clearance = cool (cyan/blue)
    const clearanceNorm = Math.min(1, Math.max(0, pt.clearance / 1000));
    const r = clearanceNorm < 0.5 ? 1 : 1 - (clearanceNorm - 0.5) * 2;
    const g = clearanceNorm < 0.5 ? clearanceNorm * 2 : 1;
    const b = clearanceNorm > 0.5 ? 1 : clearanceNorm * 2;
    colors[i * 3] = r;
    colors[i * 3 + 1] = g;
    colors[i * 3 + 2] = b;
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));

  const material = new THREE.PointsMaterial({
    size: 3,
    vertexColors: true,
    transparent: true,
    opacity: state.options.opacity,
    sizeAttenuation: true,
    depthWrite: false,
  });

  state.pointCloud = new THREE.Points(geometry, material);
  state.scene.add(state.pointCloud);
}

function normalizeOptions(options?: Partial<VoxelRenderOptions>): VoxelRenderOptions {
  return {
    opacity: Math.min(1, Math.max(0, options?.opacity ?? 0.8)),
  };
}

function disposePointCloud(state: VoxelState) {
  if (state.pointCloud && state.scene) {
    state.scene.remove(state.pointCloud);
    state.pointCloud.geometry.dispose();
    if (Array.isArray(state.pointCloud.material)) {
      state.pointCloud.material.forEach((m) => m.dispose());
    } else {
      state.pointCloud.material.dispose();
    }
    state.pointCloud = null;
  }
}

export async function loadVoxelData(
  binUrl: string,
  manifestUrl: string
): Promise<VoxelPoint[]> {
  const manifestResponse = await fetch(manifestUrl);
  if (!manifestResponse.ok) {
    throw new Error(`Failed to load voxel manifest: ${manifestResponse.status}`);
  }
  const manifest: VoxelManifest = await manifestResponse.json();

  const binResponse = await fetch(binUrl);
  if (!binResponse.ok) {
    throw new Error(`Failed to load voxel binary: ${binResponse.status}`);
  }
  const buffer = await binResponse.arrayBuffer();
  const floatArray = new Float32Array(buffer);

  const points: VoxelPoint[] = [];
  const fields = manifest.fields;
  const xIdx = fields.indexOf("lon");
  const yIdx = fields.indexOf("lat");
  const zIdx = fields.indexOf("z_agl_m");
  const cIdx = fields.indexOf("clearance_m");

  const valuesPerPoint = manifest.bytes_per_point / 4;
  for (let i = 0; i < floatArray.length; i += valuesPerPoint) {
    points.push({
      x: floatArray[i + xIdx],
      y: floatArray[i + yIdx],
      z: floatArray[i + zIdx],
      clearance: floatArray[i + cIdx],
    });
  }

  return points;
}
