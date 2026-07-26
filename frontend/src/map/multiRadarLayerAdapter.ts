import type mapboxgl from "mapbox-gl";

export interface MultiRadarAggregateLayers {
  visible: GeoJSON.GeoJSON;
  overlap: GeoJSON.GeoJSON;
  blind: GeoJSON.GeoJSON;
  coverageCount: GeoJSON.GeoJSON;
  stations: GeoJSON.GeoJSON;
}

export interface MultiRadarLayerAdapterOptions {
  maxDetailedSelections?: number;
  removeDetail?(stationId: string): void;
}

const LAYER_IDS = ["multi-radar-visible", "multi-radar-overlap", "multi-radar-blind", "multi-radar-count", "multi-radar-station-clusters", "multi-radar-stations"] as const;

export function createMultiRadarLayerAdapter(options: MultiRadarLayerAdapterOptions = {}) {
  const maxDetailedSelections = options.maxDetailedSelections ?? 5;
  const selected: string[] = [];

  function selectStationDetail(stationId: string) {
    const existing = selected.indexOf(stationId);
    if (existing >= 0) selected.splice(existing, 1);
    selected.push(stationId);
    while (selected.length > maxDetailedSelections) {
      const evicted = selected.shift();
      if (evicted) options.removeDetail?.(evicted);
    }
  }

  function removeStationDetail(stationId: string) {
    const index = selected.indexOf(stationId);
    if (index >= 0) selected.splice(index, 1);
    options.removeDetail?.(stationId);
  }

  return {
    showAggregate(map: mapboxgl.Map, layers: MultiRadarAggregateLayers) {
      upsertGeoJsonLayer(map, "multi-radar-visible", layers.visible, "fill", { "fill-color": "#16a34a", "fill-opacity": 0.22 });
      upsertGeoJsonLayer(map, "multi-radar-overlap", layers.overlap, "fill", { "fill-color": "#7c3aed", "fill-opacity": 0.3 });
      upsertGeoJsonLayer(map, "multi-radar-blind", layers.blind, "fill", { "fill-color": "#dc2626", "fill-opacity": 0.22 });
      upsertGeoJsonLayer(map, "multi-radar-count", layers.coverageCount, "line", { "line-color": "#f59e0b", "line-width": 1.2, "line-opacity": 0.75 });
      upsertStationLayers(map, layers.stations);
    },
    selectStationDetail,
    removeStationDetail,
    selectedStationIds: () => [...selected],
    clear(map: mapboxgl.Map) {
      for (const id of LAYER_IDS) removeLayerAndSource(map, id);
      selected.splice(0).forEach((stationId) => options.removeDetail?.(stationId));
    }
  };
}

function upsertGeoJsonLayer(
  map: mapboxgl.Map,
  id: string,
  data: GeoJSON.GeoJSON,
  type: "fill" | "line",
  paint: Record<string, number | string>
) {
  const sourceId = `${id}-source`;
  const source = map.getSource(sourceId) as mapboxgl.GeoJSONSource | undefined;
  if (source) source.setData(data);
  else map.addSource(sourceId, { type: "geojson", data });
  if (map.getLayer(id)) return;
  if (type === "fill") {
    map.addLayer({ id, source: sourceId, type: "fill", paint } as never);
  } else {
    map.addLayer({ id, source: sourceId, type: "line", paint } as never);
  }
}

function upsertStationLayers(map: mapboxgl.Map, data: GeoJSON.GeoJSON) {
  const sourceId = "multi-radar-stations-source";
  const source = map.getSource(sourceId) as mapboxgl.GeoJSONSource | undefined;
  if (source) source.setData(data);
  else map.addSource(sourceId, { type: "geojson", data, cluster: true, clusterRadius: 42, clusterMaxZoom: 12 });
  if (!map.getLayer("multi-radar-station-clusters")) {
    map.addLayer({ id: "multi-radar-station-clusters", source: sourceId, type: "circle", filter: ["has", "point_count"], paint: { "circle-color": "#2563eb", "circle-radius": ["step", ["get", "point_count"], 14, 20, 18, 80, 23], "circle-opacity": 0.9 } });
  }
  if (!map.getLayer("multi-radar-stations")) {
    map.addLayer({ id: "multi-radar-stations", source: sourceId, type: "circle", filter: ["!", ["has", "point_count"]], paint: { "circle-color": ["match", ["get", "status"], "finished", "#16a34a", "#dc2626"], "circle-radius": 6, "circle-stroke-color": "#ffffff", "circle-stroke-width": 1.5 } });
  }
}

function removeLayerAndSource(map: mapboxgl.Map, id: string) {
  if (map.getLayer(id)) map.removeLayer(id);
  const sourceId = `${id}-source`;
  if (map.getSource(sourceId)) map.removeSource(sourceId);
  if (id === "multi-radar-stations" && map.getSource("multi-radar-stations-source")) map.removeSource("multi-radar-stations-source");
}
