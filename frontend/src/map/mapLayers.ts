import maplibregl from "maplibre-gl";

export type ResultLayerKey = "range" | "blocked" | "visible";
export type FusionLayerKey = "fusionVisible" | "fusionOverlap" | "fusionBlind";

const DEM_BOUNDS_SOURCE_ID = "dem-bounds-source";
const DEM_BOUNDS_FILL_LAYER_ID = "dem-bounds-fill";
const DEM_BOUNDS_OUTLINE_LAYER_ID = "dem-bounds-outline";
const DEM_RASTER_SOURCE_ID = "dem-raster-source";
const DEM_RASTER_LAYER_ID = "dem-raster-layer";
export const DEM_TERRAIN_SOURCE_ID = "dem-terrain-source";
const DEM_TERRAIN_MAX_ZOOM = 16;
const PROFILE_SOURCE_ID = "coverage-profile-source";
const PROFILE_LINE_LAYER_ID = "coverage-profile-line";
const PROFILE_TARGET_LAYER_ID = "coverage-profile-target";
const PROFILE_OBSTRUCTION_LAYER_ID = "coverage-profile-obstruction";
const FUSION_LAYER_IDS = [
  "fusion-visible-layer",
  "fusion-visible-layer-outline",
  "fusion-overlap-layer",
  "fusion-overlap-layer-outline",
  "fusion-blind-layer",
  "fusion-blind-layer-outline"
];
const FUSION_SOURCE_IDS = ["fusion-visible-layer-source", "fusion-overlap-layer-source", "fusion-blind-layer-source"];

const RESULT_LAYER_IDS: Record<ResultLayerKey, { fill: string; outline: string }> = {
  range: {
    fill: "range-layer",
    outline: "range-layer-outline"
  },
  blocked: {
    fill: "blocked-layer",
    outline: "blocked-layer-outline"
  },
  visible: {
    fill: "visible-layer",
    outline: "visible-layer-outline"
  }
};

const FUSION_LAYER_MAP: Record<FusionLayerKey, { fill: string; outline: string }> = {
  fusionVisible: {
    fill: "fusion-visible-layer",
    outline: "fusion-visible-layer-outline"
  },
  fusionOverlap: {
    fill: "fusion-overlap-layer",
    outline: "fusion-overlap-layer-outline"
  },
  fusionBlind: {
    fill: "fusion-blind-layer",
    outline: "fusion-blind-layer-outline"
  }
};

export function addOrUpdateDemBoundsLayer(map: maplibregl.Map, bounds: number[]) {
  if (bounds.length !== 4 || !bounds.every(Number.isFinite)) {
    return;
  }

  const [minLon, minLat, maxLon, maxLat] = bounds;
  const data: GeoJSON.FeatureCollection = {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: {},
        geometry: {
          type: "Polygon",
          coordinates: [
            [
              [minLon, minLat],
              [maxLon, minLat],
              [maxLon, maxLat],
              [minLon, maxLat],
              [minLon, minLat]
            ]
          ]
        }
      }
    ]
  };

  const existing = map.getSource(DEM_BOUNDS_SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
  if (existing) {
    existing.setData(data);
  } else {
    map.addSource(DEM_BOUNDS_SOURCE_ID, {
      type: "geojson",
      data
    });
  }

  if (!map.getLayer(DEM_BOUNDS_FILL_LAYER_ID)) {
    map.addLayer({
      id: DEM_BOUNDS_FILL_LAYER_ID,
      type: "fill",
      source: DEM_BOUNDS_SOURCE_ID,
      paint: {
        "fill-color": "#f59e0b",
        "fill-opacity": 0.12
      }
    });
  }

  if (!map.getLayer(DEM_BOUNDS_OUTLINE_LAYER_ID)) {
    map.addLayer({
      id: DEM_BOUNDS_OUTLINE_LAYER_ID,
      type: "line",
      source: DEM_BOUNDS_SOURCE_ID,
      paint: {
        "line-color": "#d97706",
        "line-width": 2,
        "line-opacity": 0.9
      }
    });
  }
}

export function addOrUpdateDemRasterLayer(map: maplibregl.Map, tileUrl: string, bounds: number[]) {
  if (map.getLayer(DEM_RASTER_LAYER_ID)) {
    map.removeLayer(DEM_RASTER_LAYER_ID);
  }
  if (map.getSource(DEM_RASTER_SOURCE_ID)) {
    map.removeSource(DEM_RASTER_SOURCE_ID);
  }

  const sourceBounds = bounds.length === 4 && bounds.every(Number.isFinite)
    ? (bounds as [number, number, number, number])
    : undefined;
  map.addSource(DEM_RASTER_SOURCE_ID, {
    type: "raster",
    tiles: [tileUrl],
    tileSize: 256,
    bounds: sourceBounds,
    minzoom: 0,
    maxzoom: 16
  });
  const beforeLayer = map.getLayer(DEM_BOUNDS_FILL_LAYER_ID) ? DEM_BOUNDS_FILL_LAYER_ID : undefined;
  map.addLayer(
    {
      id: DEM_RASTER_LAYER_ID,
      type: "raster",
      source: DEM_RASTER_SOURCE_ID,
      paint: {
        "raster-opacity": 0.72,
        "raster-resampling": "linear",
        "raster-fade-duration": 0
      }
    },
    beforeLayer
  );
}

export function removeDemRasterLayer(map: maplibregl.Map) {
  if (map.getLayer(DEM_RASTER_LAYER_ID)) {
    map.removeLayer(DEM_RASTER_LAYER_ID);
  }
  if (map.getSource(DEM_RASTER_SOURCE_ID)) {
    map.removeSource(DEM_RASTER_SOURCE_ID);
  }
}

export function addOrUpdateDemTerrain(map: maplibregl.Map, tileUrl: string, bounds: number[], exaggeration = 1.35) {
  map.setTerrain(null);
  if (map.getSource(DEM_TERRAIN_SOURCE_ID)) {
    map.removeSource(DEM_TERRAIN_SOURCE_ID);
  }

  const sourceBounds = bounds.length === 4 && bounds.every(Number.isFinite)
    ? (bounds as [number, number, number, number])
    : undefined;
  map.addSource(DEM_TERRAIN_SOURCE_ID, {
    type: "raster-dem",
    tiles: [tileUrl],
    tileSize: 256,
    bounds: sourceBounds,
    minzoom: 0,
    maxzoom: DEM_TERRAIN_MAX_ZOOM,
    encoding: "terrarium"
  });
  map.setTerrain({ source: DEM_TERRAIN_SOURCE_ID, exaggeration });
}

export function removeDemTerrain(map: maplibregl.Map) {
  map.setTerrain(null);
  if (map.getSource(DEM_TERRAIN_SOURCE_ID)) {
    map.removeSource(DEM_TERRAIN_SOURCE_ID);
  }
}

export function removeDemBoundsLayer(map: maplibregl.Map) {
  for (const layerId of [DEM_BOUNDS_FILL_LAYER_ID, DEM_BOUNDS_OUTLINE_LAYER_ID]) {
    if (map.getLayer(layerId)) {
      map.removeLayer(layerId);
    }
  }
  if (map.getSource(DEM_BOUNDS_SOURCE_ID)) {
    map.removeSource(DEM_BOUNDS_SOURCE_ID);
  }
}

export function addOrUpdateGeoJsonLayer(
  map: maplibregl.Map,
  id: string,
  url: string,
  paint: NonNullable<maplibregl.FillLayerSpecification["paint"]>,
  linePaint?: NonNullable<maplibregl.LineLayerSpecification["paint"]>
) {
  const sourceId = `${id}-source`;
  const existing = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;

  if (existing) {
    existing.setData(url);
  } else {
    map.addSource(sourceId, {
      type: "geojson",
      data: url
    });
  }

  if (!map.getLayer(id)) {
    map.addLayer({
      id,
      type: "fill",
      source: sourceId,
      paint
    });
  }

  const lineId = `${id}-outline`;
  if (linePaint && !map.getLayer(lineId)) {
    map.addLayer({
      id: lineId,
      type: "line",
      source: sourceId,
      paint: linePaint
    });
  }
}

export function addRadarMarker(map: maplibregl.Map, lon: number, lat: number, heightM = 30) {
  const sourceId = "radar-point-source";
  const data: GeoJSON.FeatureCollection = {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: {},
        geometry: {
          type: "Point",
          coordinates: [lon, lat]
        }
      }
    ]
  };

  const existing = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;
  if (existing) {
    existing.setData(data);
  } else {
    map.addSource(sourceId, {
      type: "geojson",
      data
    });
  }

  if (!map.getLayer("radar-point-halo")) {
    map.addLayer({
      id: "radar-point-halo",
      type: "circle",
      source: sourceId,
      paint: {
        "circle-radius": 12,
        "circle-color": "#ffffff",
        "circle-opacity": 0.8
      }
    });
  }

  if (!map.getLayer("radar-point")) {
    map.addLayer({
      id: "radar-point",
      type: "circle",
      source: sourceId,
      paint: {
        "circle-radius": 7,
        "circle-color": "#f59e0b",
        "circle-stroke-width": 2,
        "circle-stroke-color": "#111827"
      }
    });
  }

  addOrUpdateRadarTower(map, lon, lat, heightM);
}

export function addOrUpdateProfileLayer(
  map: maplibregl.Map,
  radar: [number, number],
  target: [number, number],
  obstruction?: [number, number] | null
) {
  const features: GeoJSON.Feature[] = [
    {
      type: "Feature",
      properties: { kind: "line" },
      geometry: {
        type: "LineString",
        coordinates: [radar, target]
      }
    },
    {
      type: "Feature",
      properties: { kind: "target" },
      geometry: {
        type: "Point",
        coordinates: target
      }
    }
  ];

  if (obstruction) {
    features.push({
      type: "Feature",
      properties: { kind: "obstruction" },
      geometry: {
        type: "Point",
        coordinates: obstruction
      }
    });
  }

  const data: GeoJSON.FeatureCollection = {
    type: "FeatureCollection",
    features
  };

  const existing = map.getSource(PROFILE_SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
  if (existing) {
    existing.setData(data);
  } else {
    map.addSource(PROFILE_SOURCE_ID, {
      type: "geojson",
      data
    });
  }

  if (!map.getLayer(PROFILE_LINE_LAYER_ID)) {
    map.addLayer({
      id: PROFILE_LINE_LAYER_ID,
      type: "line",
      source: PROFILE_SOURCE_ID,
      filter: ["==", ["get", "kind"], "line"],
      paint: {
        "line-color": "#111827",
        "line-width": 3,
        "line-opacity": 0.78,
        "line-dasharray": [1.2, 1]
      }
    });
  }

  if (!map.getLayer(PROFILE_TARGET_LAYER_ID)) {
    map.addLayer({
      id: PROFILE_TARGET_LAYER_ID,
      type: "circle",
      source: PROFILE_SOURCE_ID,
      filter: ["==", ["get", "kind"], "target"],
      paint: {
        "circle-radius": 7,
        "circle-color": "#2563eb",
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 2
      }
    });
  }

  if (!map.getLayer(PROFILE_OBSTRUCTION_LAYER_ID)) {
    map.addLayer({
      id: PROFILE_OBSTRUCTION_LAYER_ID,
      type: "circle",
      source: PROFILE_SOURCE_ID,
      filter: ["==", ["get", "kind"], "obstruction"],
      paint: {
        "circle-radius": 8,
        "circle-color": "#dc2626",
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 2
      }
    });
  }
}

export function addOrUpdateGeoJsonDataLayer(
  map: maplibregl.Map,
  id: string,
  data: GeoJSON.GeoJSON,
  paint: NonNullable<maplibregl.FillLayerSpecification["paint"]>,
  linePaint?: NonNullable<maplibregl.LineLayerSpecification["paint"]>
) {
  const sourceId = `${id}-source`;
  const existing = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;

  if (existing) {
    existing.setData(data);
  } else {
    map.addSource(sourceId, {
      type: "geojson",
      data
    });
  }

  if (!map.getLayer(id)) {
    map.addLayer({
      id,
      type: "fill",
      source: sourceId,
      paint
    });
  }

  const lineId = `${id}-outline`;
  if (linePaint && !map.getLayer(lineId)) {
    map.addLayer({
      id: lineId,
      type: "line",
      source: sourceId,
      paint: linePaint
    });
  }
}

export function removeProfileLayer(map: maplibregl.Map) {
  for (const layerId of [PROFILE_OBSTRUCTION_LAYER_ID, PROFILE_TARGET_LAYER_ID, PROFILE_LINE_LAYER_ID]) {
    if (map.getLayer(layerId)) {
      map.removeLayer(layerId);
    }
  }
  if (map.getSource(PROFILE_SOURCE_ID)) {
    map.removeSource(PROFILE_SOURCE_ID);
  }
}

export function removeFusionLayers(map: maplibregl.Map) {
  for (const layerId of FUSION_LAYER_IDS) {
    if (map.getLayer(layerId)) {
      map.removeLayer(layerId);
    }
  }
  for (const sourceId of FUSION_SOURCE_IDS) {
    if (map.getSource(sourceId)) {
      map.removeSource(sourceId);
    }
  }
}

function addOrUpdateRadarTower(map: maplibregl.Map, lon: number, lat: number, heightM: number) {
  const sourceId = "radar-tower-source";
  const radiusDeg = 0.002;
  const coordinates: [number, number][] = [];
  for (let index = 0; index <= 24; index++) {
    const angle = (Math.PI * 2 * index) / 24;
    coordinates.push([lon + Math.cos(angle) * radiusDeg, lat + Math.sin(angle) * radiusDeg]);
  }
  const data: GeoJSON.FeatureCollection = {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: {
          height: Math.max(30, heightM)
        },
        geometry: {
          type: "Polygon",
          coordinates: [coordinates]
        }
      }
    ]
  };

  const existing = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;
  if (existing) {
    existing.setData(data);
  } else {
    map.addSource(sourceId, {
      type: "geojson",
      data
    });
  }

  if (!map.getLayer("radar-tower")) {
    map.addLayer({
      id: "radar-tower",
      type: "fill-extrusion",
      source: sourceId,
      paint: {
        "fill-extrusion-color": "#f59e0b",
        "fill-extrusion-height": ["get", "height"],
        "fill-extrusion-base": 0,
        "fill-extrusion-opacity": 0.88,
        "fill-extrusion-vertical-gradient": true
      }
    });
  }
}

export function removeResultLayers(map: maplibregl.Map) {
  const layerIds = [
    "visible-layer",
    "visible-layer-outline",
    "blocked-layer",
    "blocked-layer-outline",
    "range-layer",
    "range-layer-outline",
    "height-layer",
    "height-layer-outline",
    "height-layer-blocked",
    "height-layer-blocked-outline"
  ];
  const sourceIds = [
    "visible-layer-source",
    "blocked-layer-source",
    "range-layer-source",
    "height-layer-source",
    "height-layer-blocked-source"
  ];

  for (const layerId of layerIds) {
    if (map.getLayer(layerId)) {
      map.removeLayer(layerId);
    }
  }

  for (const sourceId of sourceIds) {
    if (map.getSource(sourceId)) {
      map.removeSource(sourceId);
    }
  }
}

export function setResultLayerVisibility(map: maplibregl.Map, key: ResultLayerKey, visible: boolean) {
  const visibility = visible ? "visible" : "none";
  const ids = RESULT_LAYER_IDS[key];
  for (const layerId of [ids.fill, ids.outline]) {
    if (map.getLayer(layerId)) {
      map.setLayoutProperty(layerId, "visibility", visibility);
    }
  }
}

export function setResultLayerOpacity(map: maplibregl.Map, key: ResultLayerKey, opacity: number) {
  const ids = RESULT_LAYER_IDS[key];
  if (map.getLayer(ids.fill)) {
    map.setPaintProperty(ids.fill, "fill-opacity", opacity);
  }
  if (map.getLayer(ids.outline)) {
    map.setPaintProperty(ids.outline, "line-opacity", opacity > 0 ? Math.max(opacity, 0.28) : 0);
  }
}

export function setFusionLayerVisibility(map: maplibregl.Map, key: FusionLayerKey, visible: boolean) {
  const visibility = visible ? "visible" : "none";
  const ids = FUSION_LAYER_MAP[key];
  for (const layerId of [ids.fill, ids.outline]) {
    if (map.getLayer(layerId)) {
      map.setLayoutProperty(layerId, "visibility", visibility);
    }
  }
}

export function setFusionLayerOpacity(map: maplibregl.Map, key: FusionLayerKey, opacity: number) {
  const ids = FUSION_LAYER_MAP[key];
  if (map.getLayer(ids.fill)) {
    map.setPaintProperty(ids.fill, "fill-opacity", opacity);
  }
  if (map.getLayer(ids.outline)) {
    map.setPaintProperty(ids.outline, "line-opacity", opacity > 0 ? Math.max(opacity, 0.35) : 0);
  }
}

export function moveRadarMarkerToTop(map: maplibregl.Map) {
  for (const layerId of ["radar-tower", "radar-point-halo", "radar-point"]) {
    if (map.getLayer(layerId)) {
      map.moveLayer(layerId);
    }
  }
}

export function getGeoJsonBounds(data: GeoJSON.GeoJSON): maplibregl.LngLatBounds | null {
  const bounds = new maplibregl.LngLatBounds();
  let hasCoordinate = false;

  visitCoordinates(data, (coordinate) => {
    if (Number.isFinite(coordinate[0]) && Number.isFinite(coordinate[1])) {
      bounds.extend(coordinate as [number, number]);
      hasCoordinate = true;
    }
  });

  return hasCoordinate ? bounds : null;
}

export function fitGeoJsonBounds(
  map: maplibregl.Map,
  data: GeoJSON.GeoJSON,
  options: maplibregl.FitBoundsOptions = { padding: 48, maxZoom: 14 }
): boolean {
  const bounds = getGeoJsonBounds(data);
  if (!bounds) return false;
  map.fitBounds(bounds, options);
  return true;
}

function visitCoordinates(data: GeoJSON.GeoJSON, visitor: (coordinate: GeoJSON.Position) => void) {
  if (data.type === "FeatureCollection") {
    for (const feature of data.features) {
      visitCoordinates(feature, visitor);
    }
    return;
  }
  if (data.type === "Feature") {
    if (data.geometry) {
      visitCoordinates(data.geometry, visitor);
    }
    return;
  }
  if (data.type === "GeometryCollection") {
    for (const geometry of data.geometries) {
      visitCoordinates(geometry, visitor);
    }
    return;
  }
  visitGeometryCoordinates(data.coordinates, visitor);
}

function visitGeometryCoordinates(coordinates: GeoJSON.Position | GeoJSON.Position[] | GeoJSON.Position[][] | GeoJSON.Position[][][], visitor: (coordinate: GeoJSON.Position) => void) {
  if (!Array.isArray(coordinates) || coordinates.length === 0) {
    return;
  }
  if (typeof coordinates[0] === "number") {
    visitor(coordinates as GeoJSON.Position);
    return;
  }
  for (const child of coordinates as GeoJSON.Position[] | GeoJSON.Position[][] | GeoJSON.Position[][][]) {
    visitGeometryCoordinates(child, visitor);
  }
}
