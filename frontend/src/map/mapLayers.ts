import maplibregl from "maplibre-gl";

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
