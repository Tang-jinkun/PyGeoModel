import * as maplibregl from "maplibre-gl";
import * as THREE from "three";

const CLIPPED_VOLUME_LAYER_ID = "clipped-volume-layer";
const CLIPPED_VOLUME_LEGACY_LAYER_PREFIX = `${CLIPPED_VOLUME_LAYER_ID}-`;
let activeClippedVolumeLayer: ClippedVolumeCustomLayer | null = null;

export interface ClippedVolumeCell {
  lon: number;
  lat: number;
  beamBottomM: number;
  blockedTopM: number;
  visibleTopM: number;
}

interface ClippedVolumeManifest {
  cell_size_m: number;
  cell_count: number;
  fields: string[];
  bytes_per_cell: number;
}

interface ClippedVolumeRenderOptions {
  opacity: number;
  maxCells: number;
  scanMode: "omni" | "sector";
  azimuthDeg: number;
  beamWidthDeg: number;
  radarLon: number;
  radarLat: number;
}

type ClippedVolumeCustomLayer = maplibregl.CustomLayerInterface & {
  update: (cells: ClippedVolumeCell[], manifest: ClippedVolumeManifest, options?: ClippedVolumeRenderOptions) => void;
};

interface ClippedVolumeState {
  map: maplibregl.Map | null;
  camera: THREE.Camera | null;
  scene: THREE.Scene | null;
  renderer: THREE.WebGLRenderer | null;
  group: THREE.Group | null;
  scanGroup: THREE.Group | null;
  cells: ClippedVolumeCell[];
  manifest: ClippedVolumeManifest;
  options: ClippedVolumeRenderOptions;
  startedAt: number;
}

export function addOrUpdateClippedVolumeLayer(
  map: maplibregl.Map,
  cells: ClippedVolumeCell[],
  manifest: ClippedVolumeManifest,
  options?: Partial<ClippedVolumeRenderOptions>
) {
  const renderOptions = normalizeOptions(options);
  if (activeClippedVolumeLayer?.id === CLIPPED_VOLUME_LAYER_ID && map.getLayer(CLIPPED_VOLUME_LAYER_ID)) {
    activeClippedVolumeLayer.update(cells, manifest, renderOptions);
    return;
  }
  removeClippedVolumeLayer(map);
  activeClippedVolumeLayer = createClippedVolumeLayer(cells, manifest, renderOptions);
  map.addLayer(activeClippedVolumeLayer);
}

export function removeClippedVolumeLayer(map: maplibregl.Map) {
  removeLayerIfPresent(map, CLIPPED_VOLUME_LAYER_ID);
  for (const layer of map.getStyle().layers ?? []) {
    if (layer.id.startsWith(CLIPPED_VOLUME_LEGACY_LAYER_PREFIX)) {
      removeLayerIfPresent(map, layer.id);
    }
  }
  activeClippedVolumeLayer = null;
}

export async function loadClippedVolumeData(
  cellsUrl: string,
  manifestUrl: string
): Promise<{ cells: ClippedVolumeCell[]; manifest: ClippedVolumeManifest }> {
  const manifestResponse = await fetch(manifestUrl);
  if (!manifestResponse.ok) {
    throw new Error(`裁切波束清单读取失败：${manifestResponse.status}`);
  }
  const manifest = await manifestResponse.json() as ClippedVolumeManifest;

  const cellsResponse = await fetch(cellsUrl);
  if (!cellsResponse.ok) {
    throw new Error(`裁切波束体读取失败：${cellsResponse.status}`);
  }
  const buffer = await cellsResponse.arrayBuffer();
  const values = new Float32Array(buffer);
  const fields = manifest.fields;
  const lonIndex = fields.indexOf("lon");
  const latIndex = fields.indexOf("lat");
  const bottomIndex = fields.indexOf("beam_bottom_m");
  const blockedIndex = fields.indexOf("blocked_top_m");
  const visibleIndex = fields.indexOf("visible_top_m");
  const valuesPerCell = manifest.bytes_per_cell / 4;

  if ([lonIndex, latIndex, bottomIndex, blockedIndex, visibleIndex].some((index) => index < 0) || valuesPerCell <= 0) {
    throw new Error("裁切波束体字段不完整");
  }

  const cells: ClippedVolumeCell[] = [];
  for (let index = 0; index < values.length; index += valuesPerCell) {
    cells.push({
      lon: values[index + lonIndex],
      lat: values[index + latIndex],
      beamBottomM: values[index + bottomIndex],
      blockedTopM: values[index + blockedIndex],
      visibleTopM: values[index + visibleIndex]
    });
  }
  return { cells, manifest };
}

function createClippedVolumeLayer(
  initialCells: ClippedVolumeCell[],
  initialManifest: ClippedVolumeManifest,
  initialOptions: ClippedVolumeRenderOptions
): ClippedVolumeCustomLayer {
  const state: ClippedVolumeState = {
    map: null,
    camera: null,
    scene: null,
    renderer: null,
    group: null,
    scanGroup: null,
    cells: initialCells,
    manifest: initialManifest,
    options: initialOptions,
    startedAt: performance.now()
  };

  return {
    id: CLIPPED_VOLUME_LAYER_ID,
    type: "custom",
    renderingMode: "3d",
    onAdd(map, gl) {
      state.map = map;
      state.camera = new THREE.Camera();
      state.scene = new THREE.Scene();
      state.renderer = new THREE.WebGLRenderer({
        canvas: map.getCanvas(),
        context: gl,
        antialias: true
      });
      state.renderer.autoClear = false;
      rebuildVolume(state);
    },
    render(_gl, matrix) {
      if (!state.map || !state.camera || !state.scene || !state.renderer) {
        return;
      }
      state.camera.projectionMatrix = new THREE.Matrix4().fromArray(matrix as number[]);
      state.renderer.resetState();
      updateClippedScanSlice(state);
      state.renderer.render(state.scene, state.camera);
      state.map.triggerRepaint();
    },
    onRemove() {
      disposeVolume(state);
      state.renderer?.dispose();
      state.map = null;
      state.camera = null;
      state.scene = null;
      state.renderer = null;
    },
    update(cells, manifest, options) {
      state.cells = cells;
      state.manifest = manifest;
      if (options) {
        state.options = options;
      }
      rebuildVolume(state);
      state.map?.triggerRepaint();
    }
  };
}

function rebuildVolume(state: ClippedVolumeState) {
  if (!state.scene) {
    return;
  }
  disposeVolume(state);
  state.group = new THREE.Group();
  state.scanGroup = new THREE.Group();

  const sampledCells = sampleCells(state.cells, state.options.maxCells);
  const cellSize = Math.max(30, state.manifest.cell_size_m || 120);
  const blockedMesh = buildInstancedSegments(sampledCells, cellSize, "blocked", state.options.opacity);
  const visibleMesh = buildInstancedSegments(sampledCells, cellSize, "visible", state.options.opacity);
  if (blockedMesh) {
    state.group.add(blockedMesh);
  }
  if (visibleMesh) {
    state.group.add(visibleMesh);
  }
  state.scene.add(state.group);
  state.scene.add(state.scanGroup);
}

function buildInstancedSegments(
  cells: ClippedVolumeCell[],
  cellSizeM: number,
  kind: "blocked" | "visible",
  opacity: number
) {
  const segments = cells
    .map((cell) => {
      const bottom = kind === "blocked" ? cell.beamBottomM : Math.max(cell.blockedTopM, cell.beamBottomM);
      const top = kind === "blocked" ? cell.blockedTopM : cell.visibleTopM;
      return { cell, bottom, top };
    })
    .filter((segment) => segment.top > segment.bottom + 0.5);

  if (!segments.length) {
    return null;
  }

  const geometry = new THREE.BoxGeometry(1, 1, 1);
  const material = new THREE.MeshBasicMaterial({
    color: kind === "blocked" ? 0xef4444 : 0x22c55e,
    transparent: true,
    opacity: opacity * (kind === "blocked" ? 0.52 : 0.34),
    depthWrite: false
  });
  const mesh = new THREE.InstancedMesh(geometry, material, segments.length);
  mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);

  const matrix = new THREE.Matrix4();
  const position = new THREE.Vector3();
  const scale = new THREE.Vector3();
  const quaternion = new THREE.Quaternion();
  for (let index = 0; index < segments.length; index++) {
    const { cell, bottom, top } = segments[index];
    const mid = (bottom + top) / 2;
    const coordinate = maplibregl.MercatorCoordinate.fromLngLat({ lng: cell.lon, lat: cell.lat }, mid);
    const meter = coordinate.meterInMercatorCoordinateUnits();
    position.set(coordinate.x, coordinate.y, coordinate.z);
    scale.set(cellSizeM * meter, cellSizeM * meter, Math.max(1, top - bottom) * meter);
    matrix.compose(position, quaternion, scale);
    mesh.setMatrixAt(index, matrix);
  }
  mesh.instanceMatrix.needsUpdate = true;
  return mesh;
}

function sampleCells(cells: ClippedVolumeCell[], maxCells: number) {
  if (cells.length <= maxCells) {
    return cells;
  }
  const step = Math.ceil(cells.length / maxCells);
  return cells.filter((_, index) => index % step === 0);
}

function disposeVolume(state: ClippedVolumeState) {
  if (!state.scene) {
    return;
  }
  const groups = [state.group, state.scanGroup].filter((group): group is THREE.Group => Boolean(group));
  for (const group of groups) {
    state.scene.remove(group);
    group.traverse((object) => {
      if (object instanceof THREE.Mesh || object instanceof THREE.InstancedMesh) {
        object.geometry.dispose();
        const material = object.material;
        if (Array.isArray(material)) {
          material.forEach((item) => item.dispose());
        } else {
          material.dispose();
        }
      }
    });
  }
  state.group = null;
  state.scanGroup = null;
}

function updateClippedScanSlice(state: ClippedVolumeState) {
  if (!state.scanGroup || !state.map) {
    return;
  }
  disposeGroupChildren(state.scanGroup);
  const elapsed = (performance.now() - state.startedAt) / 1000;
  const scanAzimuth = getCurrentScanAzimuth(state.options, elapsed);
  const sliceWidth = Math.min(10, Math.max(3, state.options.beamWidthDeg / 12));
  const sliceCells = state.cells
    .map((cell) => ({
      cell,
      azimuthDelta: angularDeltaDeg(scanAzimuth, bearingDeg(state.options.radarLon, state.options.radarLat, cell.lon, cell.lat)),
      distance: distanceScore(state.options.radarLon, state.options.radarLat, cell.lon, cell.lat)
    }))
    .filter((item) => item.azimuthDelta <= sliceWidth)
    .sort((a, b) => a.distance - b.distance)
    .filter((_, index) => index % 2 === 0)
    .slice(0, 700)
    .map((item) => item.cell);

  const blocked = buildScanSegments(sliceCells, "blocked", state.options.opacity);
  const visible = buildScanSegments(sliceCells, "visible", state.options.opacity);
  if (blocked) {
    state.scanGroup.add(blocked);
  }
  if (visible) {
    state.scanGroup.add(visible);
  }
}

function buildScanSegments(cells: ClippedVolumeCell[], kind: "blocked" | "visible", opacity: number) {
  const positions: number[] = [];
  for (const cell of cells) {
    const bottom = kind === "blocked" ? cell.beamBottomM : Math.max(cell.blockedTopM, cell.beamBottomM);
    const top = kind === "blocked" ? cell.blockedTopM : cell.visibleTopM;
    if (top <= bottom + 0.5) {
      continue;
    }
    const lower = maplibregl.MercatorCoordinate.fromLngLat({ lng: cell.lon, lat: cell.lat }, bottom);
    const upper = maplibregl.MercatorCoordinate.fromLngLat({ lng: cell.lon, lat: cell.lat }, top);
    positions.push(lower.x, lower.y, lower.z, upper.x, upper.y, upper.z);
  }
  if (!positions.length) {
    return null;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  return new THREE.LineSegments(
    geometry,
    new THREE.LineBasicMaterial({
      color: kind === "blocked" ? 0xff1f3d : 0x7cff6b,
      transparent: true,
      opacity: opacity * (kind === "blocked" ? 1 : 0.82),
      linewidth: 2,
      depthWrite: false
    })
  );
}

function disposeGroupChildren(group: THREE.Group) {
  for (const child of [...group.children]) {
    group.remove(child);
    child.traverse((object) => {
      if (object instanceof THREE.Mesh || object instanceof THREE.InstancedMesh) {
        object.geometry.dispose();
        const material = object.material;
        if (Array.isArray(material)) {
          material.forEach((item) => item.dispose());
        } else {
          material.dispose();
        }
      }
      if (object instanceof THREE.LineSegments) {
        object.geometry.dispose();
        object.material.dispose();
      }
    });
    if (child instanceof THREE.LineSegments) {
      child.geometry.dispose();
      child.material.dispose();
    }
  }
}

function getCurrentScanAzimuth(options: ClippedVolumeRenderOptions, elapsed: number) {
  if (options.scanMode === "omni") {
    return normalizeDeg(elapsed * 37.2);
  }
  const start = options.azimuthDeg - options.beamWidthDeg / 2;
  const sweep = (Math.sin(elapsed * 1.2) + 1) / 2;
  return normalizeDeg(start + options.beamWidthDeg * sweep);
}

function bearingDeg(fromLon: number, fromLat: number, toLon: number, toLat: number) {
  const dx = toLon - fromLon;
  const dy = toLat - fromLat;
  return normalizeDeg(THREE.MathUtils.radToDeg(Math.atan2(dx, dy)));
}

function angularDeltaDeg(a: number, b: number) {
  return Math.abs(((a - b + 540) % 360) - 180);
}

function normalizeDeg(value: number) {
  return ((value % 360) + 360) % 360;
}

function distanceScore(fromLon: number, fromLat: number, toLon: number, toLat: number) {
  const dx = toLon - fromLon;
  const dy = toLat - fromLat;
  return dx * dx + dy * dy;
}

function removeLayerIfPresent(map: maplibregl.Map, layerId: string) {
  if (map.getLayer(layerId)) {
    map.removeLayer(layerId);
  }
}

function normalizeOptions(options?: Partial<ClippedVolumeRenderOptions>): ClippedVolumeRenderOptions {
  return {
    opacity: Math.min(1, Math.max(0, options?.opacity ?? 0.66)),
    maxCells: Math.max(1000, Math.min(12000, Math.round(options?.maxCells ?? 7000))),
    scanMode: options?.scanMode ?? "omni",
    azimuthDeg: options?.azimuthDeg ?? 0,
    beamWidthDeg: options?.beamWidthDeg ?? 360,
    radarLon: options?.radarLon ?? 0,
    radarLat: options?.radarLat ?? 0
  };
}
