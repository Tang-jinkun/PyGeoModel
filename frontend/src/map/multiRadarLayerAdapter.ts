import { fitGeoJsonBounds } from "./mapLayers";
import type { GeoJSONSource, Map } from "./mapEngineTypes";
import type { OutputLayerDefinition } from "../models/shared";

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

export interface MultiRadarLayerState {
  kind: string;
  status: "ready";
  visible: boolean;
  opacity: number;
  data: GeoJSON.GeoJSON;
  error: null;
}

const AGGREGATE_LAYER_CONFIG = [
  { kind: "visible_union_geojson", label: "Visible union", color: "#16a34a", geometry: "fill", defaultOpacity: 0.22, primary: true, mapId: "multi-radar-visible", opacityProperty: "fill-opacity", dataKey: "visible" },
  { kind: "overlap_geojson", label: "Overlap", color: "#d4a017", geometry: "fill", defaultOpacity: 0.58, mapId: "multi-radar-overlap", opacityProperty: "fill-opacity", dataKey: "overlap" },
  { kind: "blind_geojson", label: "Blind area", color: "#dc2626", geometry: "fill", defaultOpacity: 0.22, mapId: "multi-radar-blind", opacityProperty: "fill-opacity", dataKey: "blind" },
  { kind: "coverage_count_geojson", label: "Coverage count", color: "#f59e0b", geometry: "line", defaultOpacity: 0.75, mapId: "multi-radar-count", opacityProperty: "line-opacity", dataKey: "coverageCount" }
] as const;

export const MULTI_RADAR_LAYER_DEFINITIONS: readonly OutputLayerDefinition[] = AGGREGATE_LAYER_CONFIG.map(({ mapId, opacityProperty, dataKey, ...definition }) => definition);

const LAYER_IDS = ["multi-radar-visible", "multi-radar-overlap", "multi-radar-blind", "multi-radar-count", "multi-radar-station-clusters", "multi-radar-stations"] as const;

export function createMultiRadarLayerAdapter(options: MultiRadarLayerAdapterOptions = {}) {
  const maxDetailedSelections = options.maxDetailedSelections ?? 5;
  const selected: string[] = [];
  let aggregateStates: MultiRadarLayerState[] = [];

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
    showAggregate(map: Map, layers: MultiRadarAggregateLayers) {
      upsertGeoJsonLayer(map, "multi-radar-visible", layers.visible, "fill", { "fill-color": "#16a34a", "fill-opacity": 0.22 });
      upsertGeoJsonLayer(map, "multi-radar-overlap", layers.overlap, "fill", { "fill-color": "#d4a017", "fill-outline-color": "#facc15", "fill-opacity": 0.58 });
      upsertGeoJsonLayer(map, "multi-radar-blind", layers.blind, "fill", { "fill-color": "#dc2626", "fill-opacity": 0.22 });
      upsertGeoJsonLayer(map, "multi-radar-count", layers.coverageCount, "line", { "line-color": "#f59e0b", "line-width": 1.2, "line-opacity": 0.75 });
      upsertStationLayers(map, layers.stations);
      aggregateStates = AGGREGATE_LAYER_CONFIG.map((config) => {
        const previous = aggregateStates.find((state) => state.kind === config.kind);
        const state: MultiRadarLayerState = {
          kind: config.kind,
          status: "ready",
          visible: previous?.visible ?? true,
          opacity: previous?.opacity ?? config.defaultOpacity,
          data: layers[config.dataKey],
          error: null
        };
        applyLayerPresentation(map, config, state);
        return state;
      });
    },
    definitions: () => MULTI_RADAR_LAYER_DEFINITIONS,
    layerStates: () => aggregateStates.map((state) => ({ ...state })),
    setLayerVisibility(map: Map, kind: string, visible: boolean) {
      updateAggregateState(map, kind, { visible });
    },
    setLayerOpacity(map: Map, kind: string, opacity: number) {
      updateAggregateState(map, kind, { opacity: Math.min(1, Math.max(0, opacity)) });
    },
    focusLayer(map: Map, kind: string) {
      const state = aggregateStates.find((candidate) => candidate.kind === kind);
      return state ? fitGeoJsonBounds(map, state.data) : false;
    },
    raiseLayer(map: Map, kind: string) {
      const config = AGGREGATE_LAYER_CONFIG.find((candidate) => candidate.kind === kind);
      if (config && map.getLayer(config.mapId)) map.moveLayer(config.mapId);
    },
    selectStationDetail,
    removeStationDetail,
    selectedStationIds: () => [...selected],
    clear(map: Map) {
      for (const id of LAYER_IDS) removeLayerAndSource(map, id);
      selected.splice(0).forEach((stationId) => options.removeDetail?.(stationId));
      aggregateStates = [];
    }
  };

  function updateAggregateState(map: Map, kind: string, patch: Partial<Pick<MultiRadarLayerState, "visible" | "opacity">>) {
    const config = AGGREGATE_LAYER_CONFIG.find((candidate) => candidate.kind === kind);
    const current = aggregateStates.find((candidate) => candidate.kind === kind);
    if (!config || !current) return;
    const next = { ...current, ...patch };
    aggregateStates = aggregateStates.map((state) => state.kind === kind ? next : state);
    applyLayerPresentation(map, config, next);
  }
}

function applyLayerPresentation(
  map: Map,
  config: (typeof AGGREGATE_LAYER_CONFIG)[number],
  state: MultiRadarLayerState
) {
  if (!map.getLayer(config.mapId)) return;
  map.setLayoutProperty(config.mapId, "visibility", state.visible ? "visible" : "none");
  map.setPaintProperty(config.mapId, config.opacityProperty, state.opacity);
}

function upsertGeoJsonLayer(
  map: Map,
  id: string,
  data: GeoJSON.GeoJSON,
  type: "fill" | "line",
  paint: Record<string, number | string>
) {
  const sourceId = `${id}-source`;
  const source = map.getSource(sourceId) as GeoJSONSource | undefined;
  if (source) source.setData(data);
  else map.addSource(sourceId, { type: "geojson", data });
  if (map.getLayer(id)) return;
  if (type === "fill") {
    map.addLayer({ id, source: sourceId, type: "fill", paint } as never);
  } else {
    map.addLayer({ id, source: sourceId, type: "line", paint } as never);
  }
}

function upsertStationLayers(map: Map, data: GeoJSON.GeoJSON) {
  const sourceId = "multi-radar-stations-source";
  const source = map.getSource(sourceId) as GeoJSONSource | undefined;
  if (source) source.setData(data);
  else map.addSource(sourceId, { type: "geojson", data, cluster: true, clusterRadius: 42, clusterMaxZoom: 12 });
  if (!map.getLayer("multi-radar-station-clusters")) {
    map.addLayer({ id: "multi-radar-station-clusters", source: sourceId, type: "circle", filter: ["has", "point_count"], paint: { "circle-color": "#2563eb", "circle-radius": ["step", ["get", "point_count"], 14, 20, 18, 80, 23], "circle-opacity": 0.9 } });
  }
  if (!map.getLayer("multi-radar-stations")) {
    map.addLayer({ id: "multi-radar-stations", source: sourceId, type: "circle", filter: ["!", ["has", "point_count"]], paint: { "circle-color": ["match", ["get", "status"], "finished", "#16a34a", "#dc2626"], "circle-radius": 6, "circle-stroke-color": "#ffffff", "circle-stroke-width": 1.5 } });
  }
}

function removeLayerAndSource(map: Map, id: string) {
  if (map.getLayer(id)) map.removeLayer(id);
  const sourceId = `${id}-source`;
  if (map.getSource(sourceId)) map.removeSource(sourceId);
  if (id === "multi-radar-stations" && map.getSource("multi-radar-stations-source")) map.removeSource("multi-radar-stations-source");
}
