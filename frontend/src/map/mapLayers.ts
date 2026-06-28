import maplibregl from "maplibre-gl";

export type ResultLayerKey = "range" | "blocked" | "visible";

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

export function addRadarMarker(map: maplibregl.Map, lon: number, lat: number) {
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
}

export function removeResultLayers(map: maplibregl.Map) {
  const layerIds = [
    "visible-layer",
    "visible-layer-outline",
    "blocked-layer",
    "blocked-layer-outline",
    "range-layer",
    "range-layer-outline"
  ];
  const sourceIds = ["visible-layer-source", "blocked-layer-source", "range-layer-source"];

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

export function moveRadarMarkerToTop(map: maplibregl.Map) {
  for (const layerId of ["radar-point-halo", "radar-point"]) {
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
