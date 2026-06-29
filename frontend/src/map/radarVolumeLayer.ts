import maplibregl from "maplibre-gl";
import * as THREE from "three";

import type { CoverageRequest } from "../api/client";

const RADAR_VOLUME_LAYER_PREFIX = "radar-volume-layer";
const RADAR_VOLUME_MAX_SEGMENTS = 72;
let activeRadarVolumeLayer: RadarVolumeCustomLayer | null = null;

type RadarVolumeCustomLayer = maplibregl.CustomLayerInterface & {
  update: (request: CoverageRequest, options?: RadarVolumeRenderOptions) => void;
};

interface RadarVolumeRenderOptions {
  opacity: number;
}

interface RadarVolumeState {
  request: CoverageRequest;
  options: RadarVolumeRenderOptions;
  anchorAltitudeM: number | null;
  map: maplibregl.Map | null;
  camera: THREE.Camera | null;
  scene: THREE.Scene | null;
  renderer: THREE.WebGLRenderer | null;
  group: THREE.Group | null;
  startedAt: number;
}

export function addOrUpdateRadarVolume(
  map: maplibregl.Map,
  request: CoverageRequest,
  options?: Partial<RadarVolumeRenderOptions>
) {
  const renderOptions = normalizeOptions(options);
  if (activeRadarVolumeLayer && map.getLayer(activeRadarVolumeLayer.id)) {
    activeRadarVolumeLayer.update(request, renderOptions);
    return;
  }
  removeRadarVolume(map);
  activeRadarVolumeLayer = createRadarVolumeLayer(request, renderOptions);
  map.addLayer(activeRadarVolumeLayer);
}

export function removeRadarVolume(map: maplibregl.Map) {
  for (const layer of map.getStyle().layers ?? []) {
    if (layer.id.startsWith(RADAR_VOLUME_LAYER_PREFIX) && map.getLayer(layer.id)) {
      map.removeLayer(layer.id);
    }
  }
  activeRadarVolumeLayer = null;
}

function createRadarVolumeLayer(
  initialRequest: CoverageRequest,
  initialOptions: RadarVolumeRenderOptions
): RadarVolumeCustomLayer {
  const state: RadarVolumeState = {
    request: cloneRequest(initialRequest),
    options: initialOptions,
    anchorAltitudeM: null,
    map: null,
    camera: null,
    scene: null,
    renderer: null,
    group: null,
    startedAt: performance.now()
  };

  return {
    id: `${RADAR_VOLUME_LAYER_PREFIX}-${Math.random().toString(36).slice(2, 10)}`,
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
      rebuildMesh(state);
    },
    render(_gl, matrix) {
      if (!state.map || !state.camera || !state.scene || !state.renderer) {
        return;
      }
      state.camera.projectionMatrix = new THREE.Matrix4().fromArray(matrix as number[]);
      const nextAnchorAltitudeM = getRadarAnchorAltitudeM(state.request, state.map);
      if (state.anchorAltitudeM == null || Math.abs(nextAnchorAltitudeM - state.anchorAltitudeM) > 1) {
        rebuildMesh(state);
      }
      updateAnimatedRadarVolume(state);
      state.renderer.resetState();
      state.renderer.render(state.scene, state.camera);
      state.map.triggerRepaint();
    },
    onRemove() {
      disposeMesh(state);
      state.renderer?.dispose();
      state.map = null;
      state.camera = null;
      state.scene = null;
      state.renderer = null;
    },
    update(request: CoverageRequest, options?: RadarVolumeRenderOptions) {
      state.request = cloneRequest(request);
      if (options) {
        state.options = options;
      }
      rebuildMesh(state);
      state.map?.triggerRepaint();
    }
  };
}

function rebuildMesh(state: RadarVolumeState) {
  if (!state.scene) {
    return;
  }
  disposeMesh(state);
  state.anchorAltitudeM = getRadarAnchorAltitudeM(state.request, state.map);
  const volume = buildRadarVolume(state.request, state.options, state.anchorAltitudeM);
  state.group = volume;
  state.scene.add(volume);
}

function buildRadarVolume(request: CoverageRequest, options: RadarVolumeRenderOptions, anchorAltitudeM: number) {
  const group = new THREE.Group();
  const shape = getVolumeShape(request, anchorAltitudeM);
  const geometry = buildRadarVolumeGeometry(shape);
  const mainColor = request.coverage.scan_mode === "sector" ? 0x2563eb : 0x0891b2;

  const material = new THREE.MeshBasicMaterial({
    color: mainColor,
    transparent: true,
    opacity: options.opacity * (request.coverage.scan_mode === "sector" ? 0.36 : 0.28),
    depthWrite: false,
    side: THREE.DoubleSide
  });
  group.add(new THREE.Mesh(geometry, material));
  group.add(buildTopCap(shape, request.coverage.scan_mode, options));

  const wireframe = new THREE.LineSegments(
    new THREE.WireframeGeometry(geometry),
    new THREE.LineBasicMaterial({
      color: 0x7dd3fc,
      transparent: true,
      opacity: options.opacity * 0.72,
      depthWrite: false
    })
  );
  group.add(wireframe);

  group.add(buildRadarGrid(shape, options));
  group.add(buildSupplementaryLobes(shape, request, options));
  group.add(buildRayLines(shape, request.coverage.scan_mode === "sector" ? 18 : 36, options));
  group.add(buildBoundaryLines(shape, options));
  group.add(buildGroundConnectionLines(shape, request.coverage.scan_mode === "sector" ? 9 : 16, options));
  group.add(buildScanPlane(shape, options));
  return group;
}

function buildTopCap(
  shape: VolumeShape,
  scanMode: CoverageRequest["coverage"]["scan_mode"],
  options: RadarVolumeRenderOptions
) {
  const geometry = buildTopCapGeometry(shape);
  return new THREE.Mesh(
    geometry,
    new THREE.MeshBasicMaterial({
      color: scanMode === "sector" ? 0x60a5fa : 0x22d3ee,
      transparent: true,
      opacity: options.opacity * (scanMode === "sector" ? 0.42 : 0.34),
      depthWrite: false,
      side: THREE.DoubleSide
    })
  );
}

function disposeMesh(state: RadarVolumeState) {
  if (!state.group || !state.scene) {
    return;
  }
  state.scene.remove(state.group);
  state.group.traverse((object) => {
    if (object instanceof THREE.Mesh || object instanceof THREE.Line || object instanceof THREE.LineSegments) {
      object.geometry.dispose();
      const material = object.material;
      if (Array.isArray(material)) {
        material.forEach((item) => item.dispose());
      } else {
        material.dispose();
      }
    }
  });
  state.group = null;
}

function updateAnimatedRadarVolume(state: RadarVolumeState) {
  if (!state.group) {
    return;
  }
  const scanPlane = state.group.getObjectByName("radar-scan-plane");
  if (!scanPlane) {
    return;
  }
  const elapsed = (performance.now() - state.startedAt) / 1000;
  const shape = getVolumeShape(state.request, state.anchorAltitudeM ?? getRadarAnchorAltitudeM(state.request, state.map));
  const scanAzimuth = getCurrentScanAzimuth(shape, state.request.coverage.scan_mode, elapsed);
  updateScanPlaneGeometry(scanPlane, shape, scanAzimuth);
}

function getCurrentScanAzimuth(shape: VolumeShape, scanMode: CoverageRequest["coverage"]["scan_mode"], elapsed: number) {
  if (scanMode === "omni") {
    return elapsed * 0.65;
  }
  const sweep = (Math.sin(elapsed * 1.2) + 1) / 2;
  return shape.startAzimuth + (shape.endAzimuth - shape.startAzimuth) * sweep;
}

interface VolumeShape {
  origin: maplibregl.MercatorCoordinate;
  meter: number;
  radius: number;
  verticalAngle: number;
  startAzimuth: number;
  endAzimuth: number;
  horizontalSegments: number;
  verticalSegments: number;
}

function getVolumeShape(request: CoverageRequest, anchorAltitudeM: number): VolumeShape {
  const origin = maplibregl.MercatorCoordinate.fromLngLat(
    { lng: request.radar.lon, lat: request.radar.lat },
    anchorAltitudeM
  );
  const meter = origin.meterInMercatorCoordinateUnits();
  const radius = Math.max(1, request.coverage.max_range_m) * meter;
  const requestedElevation = request.advanced.max_elevation_deg ?? 32;
  const verticalAngle = THREE.MathUtils.degToRad(Math.min(86, Math.max(72, requestedElevation)));
  const startAzimuth = getStartAzimuth(request);
  const endAzimuth = getEndAzimuth(request);
  const horizontalSegments = request.coverage.scan_mode === "omni"
    ? RADAR_VOLUME_MAX_SEGMENTS
    : Math.max(10, Math.ceil(Math.abs(endAzimuth - startAzimuth) / 4));
  const verticalSegments = 12;
  return { origin, meter, radius, verticalAngle, startAzimuth, endAzimuth, horizontalSegments, verticalSegments };
}

function buildRadarVolumeGeometry(shape: VolumeShape) {
  const positions: number[] = [];
  const indices: number[] = [];
  positions.push(shape.origin.x, shape.origin.y, shape.origin.z);
  for (let h = 0; h <= shape.horizontalSegments; h++) {
    const azimuth = interpolateAzimuth(shape, h / shape.horizontalSegments);
    for (let v = 0; v <= shape.verticalSegments; v++) {
      const point = volumePoint(shape, azimuth, v / shape.verticalSegments);
      positions.push(point.x, point.y, point.z);
    }
  }

  const row = shape.verticalSegments + 1;
  const vertex = (h: number, v: number) => 1 + h * row + v;
  for (let h = 0; h < shape.horizontalSegments; h++) {
    for (let v = 0; v < shape.verticalSegments; v++) {
      indices.push(vertex(h, v), vertex(h + 1, v), vertex(h + 1, v + 1));
      indices.push(vertex(h, v), vertex(h + 1, v + 1), vertex(h, v + 1));
    }
  }

  if (Math.abs(shape.endAzimuth - shape.startAzimuth) < Math.PI * 2 - 0.001) {
    for (const h of [0, shape.horizontalSegments]) {
      for (let v = 0; v < shape.verticalSegments; v++) {
        indices.push(0, vertex(h, v), vertex(h, v + 1));
      }
    }
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

function buildTopCapGeometry(shape: VolumeShape) {
  const positions: number[] = [];
  const indices: number[] = [];
  const topStartT = 0.55;
  const topSegments = 6;

  for (let h = 0; h <= shape.horizontalSegments; h++) {
    const azimuth = interpolateAzimuth(shape, h / shape.horizontalSegments);
    for (let v = 0; v <= topSegments; v++) {
      const verticalT = topStartT + (1 - topStartT) * (v / topSegments);
      const point = volumePoint(shape, azimuth, verticalT, 1.002);
      positions.push(point.x, point.y, point.z);
    }
  }

  const row = topSegments + 1;
  const vertex = (h: number, v: number) => h * row + v;
  for (let h = 0; h < shape.horizontalSegments; h++) {
    for (let v = 0; v < topSegments; v++) {
      indices.push(vertex(h, v), vertex(h + 1, v), vertex(h + 1, v + 1));
      indices.push(vertex(h, v), vertex(h + 1, v + 1), vertex(h, v + 1));
    }
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

function buildSupplementaryLobes(
  shape: VolumeShape,
  request: CoverageRequest,
  options: RadarVolumeRenderOptions
) {
  const group = new THREE.Group();
  const lobes = request.coverage.scan_mode === "omni"
    ? [
        { center: 0, width: 84, radiusScale: 0.88, verticalScale: 0.82 },
        { center: 90, width: 84, radiusScale: 0.88, verticalScale: 0.82 },
        { center: 180, width: 84, radiusScale: 0.88, verticalScale: 0.82 },
        { center: 270, width: 84, radiusScale: 0.88, verticalScale: 0.82 }
      ]
    : [
        {
          center: request.coverage.azimuth_deg - request.coverage.beam_width_deg * 0.72,
          width: Math.max(12, request.coverage.beam_width_deg * 0.32),
          radiusScale: 0.62,
          verticalScale: 0.72
        },
        {
          center: request.coverage.azimuth_deg + request.coverage.beam_width_deg * 0.72,
          width: Math.max(12, request.coverage.beam_width_deg * 0.32),
          radiusScale: 0.62,
          verticalScale: 0.72
        }
      ];

  for (const lobe of lobes) {
    const lobeShape = {
      ...shape,
      radius: shape.radius * lobe.radiusScale,
      verticalAngle: shape.verticalAngle * lobe.verticalScale,
      startAzimuth: THREE.MathUtils.degToRad(lobe.center - lobe.width / 2),
      endAzimuth: THREE.MathUtils.degToRad(lobe.center + lobe.width / 2),
      horizontalSegments: Math.max(16, Math.ceil(lobe.width / 3)),
      verticalSegments: 10
    };
    const geometry = buildRadarVolumeGeometry(lobeShape);
    group.add(
      new THREE.Mesh(
        geometry,
        new THREE.MeshBasicMaterial({
          color: 0x34d399,
          transparent: true,
          opacity: options.opacity * 0.15,
          depthWrite: false,
          side: THREE.DoubleSide
        })
      )
    );
    group.add(buildRadarGrid(lobeShape, { opacity: options.opacity * 0.62 }));
  }
  return group;
}

function buildRadarGrid(shape: VolumeShape, options: RadarVolumeRenderOptions) {
  const group = new THREE.Group();
  const material = new THREE.LineBasicMaterial({
    color: 0x86efac,
    transparent: true,
    opacity: Math.min(1, options.opacity * 0.78),
    depthWrite: false
  });

  for (let v = 1; v <= shape.verticalSegments; v += 2) {
    group.add(buildGridLine(shape, material, (t) => volumePoint(shape, interpolateAzimuth(shape, t), v / shape.verticalSegments)));
  }
  const meridianCount = shape.endAzimuth - shape.startAzimuth >= Math.PI * 2 - 0.001 ? 12 : 6;
  for (let h = 0; h <= meridianCount; h++) {
    const azimuth = interpolateAzimuth(shape, h / meridianCount);
    group.add(buildGridLine(shape, material, (t) => volumePoint(shape, azimuth, t)));
  }
  return group;
}

function buildGridLine(shape: VolumeShape, material: THREE.LineBasicMaterial, pointAt: (t: number) => THREE.Vector3) {
  const positions: number[] = [];
  const count = Math.max(16, Math.floor(shape.horizontalSegments / 2));
  for (let index = 0; index <= count; index++) {
    const point = pointAt(index / count);
    positions.push(point.x, point.y, point.z);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  return new THREE.Line(geometry, material.clone());
}

function buildRayLines(shape: VolumeShape, count: number, options: RadarVolumeRenderOptions) {
  const positions: number[] = [];
  for (let index = 0; index < count; index++) {
    const t = count === 1 ? 0.5 : index / (count - 1);
    const azimuth = interpolateAzimuth(shape, t);
    const end = volumePoint(shape, azimuth, 0.82);
    positions.push(shape.origin.x, shape.origin.y, shape.origin.z, end.x, end.y, end.z);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  return new THREE.LineSegments(
    geometry,
    new THREE.LineBasicMaterial({
      color: 0x67e8f9,
      transparent: true,
      opacity: options.opacity * 0.72,
      depthWrite: false
    })
  );
}

function buildBoundaryLines(shape: VolumeShape, options: RadarVolumeRenderOptions) {
  const positions: number[] = [];
  const addLine = (a: THREE.Vector3, b: THREE.Vector3) => {
    positions.push(a.x, a.y, a.z, b.x, b.y, b.z);
  };
  for (let h = 0; h < shape.horizontalSegments; h++) {
    addLine(volumePoint(shape, interpolateAzimuth(shape, h / shape.horizontalSegments), 0), volumePoint(shape, interpolateAzimuth(shape, (h + 1) / shape.horizontalSegments), 0));
    addLine(volumePoint(shape, interpolateAzimuth(shape, h / shape.horizontalSegments), 1), volumePoint(shape, interpolateAzimuth(shape, (h + 1) / shape.horizontalSegments), 1));
  }
  for (const t of [0, 1]) {
    const azimuth = interpolateAzimuth(shape, t);
    for (let v = 0; v < shape.verticalSegments; v++) {
      addLine(volumePoint(shape, azimuth, v / shape.verticalSegments), volumePoint(shape, azimuth, (v + 1) / shape.verticalSegments));
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  return new THREE.LineSegments(
    geometry,
    new THREE.LineBasicMaterial({
      color: 0xbfdbfe,
      transparent: true,
      opacity: options.opacity * 0.9,
      depthWrite: false
    })
  );
}

function buildGroundConnectionLines(shape: VolumeShape, count: number, options: RadarVolumeRenderOptions) {
  const positions: number[] = [];
  for (let index = 0; index < count; index++) {
    const t = count === 1 ? 0.5 : index / (count - 1);
    const azimuth = interpolateAzimuth(shape, t);
    const top = volumePoint(shape, azimuth, 0.75);
    const ground = volumePoint(shape, azimuth, 0);
    positions.push(top.x, top.y, top.z, ground.x, ground.y, shape.origin.z);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  return new THREE.LineSegments(
    geometry,
    new THREE.LineBasicMaterial({
      color: 0xf8fafc,
      transparent: true,
      opacity: options.opacity * 0.36,
      depthWrite: false
    })
  );
}

function buildScanPlane(shape: VolumeShape, options: RadarVolumeRenderOptions) {
  const group = new THREE.Group();
  group.name = "radar-scan-plane";
  const bands = [
    { from: 0, to: 0.2, color: 0xef4444 },
    { from: 0.2, to: 0.4, color: 0xf59e0b },
    { from: 0.4, to: 0.6, color: 0xfacc15 },
    { from: 0.6, to: 0.8, color: 0x22c55e },
    { from: 0.8, to: 1, color: 0x60a5fa }
  ];
  for (const band of bands) {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(getScanBandPositions(shape, shape.startAzimuth, band.from, band.to), 3)
    );
    geometry.setIndex([0, 1, 2, 0, 2, 4, 0, 4, 3, 0, 3, 1]);
    const mesh = new THREE.Mesh(
      geometry,
      new THREE.MeshBasicMaterial({
        color: band.color,
        transparent: true,
        opacity: options.opacity * 0.72,
        depthWrite: false,
        side: THREE.DoubleSide
      })
    );
    mesh.userData.verticalStart = band.from;
    mesh.userData.verticalEnd = band.to;
    group.add(mesh);
  }
  return group;
}

function updateScanPlaneGeometry(object: THREE.Object3D, shape: VolumeShape, azimuth: number) {
  if (object instanceof THREE.Group) {
    for (const child of object.children) {
      updateScanPlaneGeometry(child, shape, azimuth);
    }
    return;
  }
  if (!(object instanceof THREE.Mesh) || !(object.geometry instanceof THREE.BufferGeometry)) {
    return;
  }
  const verticalStart = typeof object.userData.verticalStart === "number" ? object.userData.verticalStart : 0;
  const verticalEnd = typeof object.userData.verticalEnd === "number" ? object.userData.verticalEnd : 1;
  const nextPositions = getScanBandPositions(shape, azimuth, verticalStart, verticalEnd);
  const position = object.geometry.getAttribute("position");
  if (!(position instanceof THREE.BufferAttribute) || position.count !== nextPositions.length / 3) {
    object.geometry.setAttribute("position", new THREE.Float32BufferAttribute(nextPositions, 3));
  } else {
    for (let index = 0; index < nextPositions.length; index++) {
      position.array[index] = nextPositions[index];
    }
    position.needsUpdate = true;
  }
  object.geometry.computeBoundingSphere();
}

function getScanBandPositions(shape: VolumeShape, azimuth: number, verticalStart: number, verticalEnd: number) {
  const positions: number[] = [
    shape.origin.x,
    shape.origin.y,
    shape.origin.z
  ];
  const scanWidth = Math.min(
    THREE.MathUtils.degToRad(10),
    Math.max(THREE.MathUtils.degToRad(3), Math.abs(shape.endAzimuth - shape.startAzimuth) / 8)
  );
  for (const offset of [-scanWidth / 2, scanWidth / 2]) {
    for (const verticalT of [verticalStart, verticalEnd]) {
      const point = volumePoint(shape, azimuth + offset, verticalT);
      positions.push(point.x, point.y, point.z);
    }
  }
  return positions;
}

function volumePoint(shape: VolumeShape, azimuth: number, verticalT: number, radiusScale = 1) {
  const elevation = shape.verticalAngle * verticalT;
  const radius = shape.radius * radiusScale;
  const horizontalDistance = Math.cos(elevation) * radius;
  return new THREE.Vector3(
    shape.origin.x + Math.sin(azimuth) * horizontalDistance,
    shape.origin.y - Math.cos(azimuth) * horizontalDistance,
    shape.origin.z + Math.sin(elevation) * radius
  );
}

function interpolateAzimuth(shape: VolumeShape, t: number) {
  return shape.startAzimuth + (shape.endAzimuth - shape.startAzimuth) * t;
}

function getStartAzimuth(request: CoverageRequest) {
  if (request.coverage.scan_mode === "omni") {
    return 0;
  }
  return THREE.MathUtils.degToRad(request.coverage.azimuth_deg - request.coverage.beam_width_deg / 2);
}

function getEndAzimuth(request: CoverageRequest) {
  if (request.coverage.scan_mode === "omni") {
    return Math.PI * 2;
  }
  return THREE.MathUtils.degToRad(request.coverage.azimuth_deg + request.coverage.beam_width_deg / 2);
}

function getRadarAnchorAltitudeM(request: CoverageRequest, map: maplibregl.Map | null) {
  const queryTerrainElevation = map?.queryTerrainElevation?.bind(map);
  const terrainElevation = queryTerrainElevation
    ? queryTerrainElevation({ lng: request.radar.lon, lat: request.radar.lat })
    : null;
  return (Number.isFinite(terrainElevation) ? terrainElevation ?? 0 : 0) + request.radar.height_m;
}

function normalizeOptions(options?: Partial<RadarVolumeRenderOptions>): RadarVolumeRenderOptions {
  return {
    opacity: Math.min(1, Math.max(0, options?.opacity ?? 0.62))
  };
}

function cloneRequest(request: CoverageRequest): CoverageRequest {
  return {
    ...request,
    radar: { ...request.radar },
    target: { ...request.target },
    coverage: { ...request.coverage },
    advanced: { ...request.advanced },
    reserved_radar_params: { ...(request.reserved_radar_params ?? {}) }
  };
}
