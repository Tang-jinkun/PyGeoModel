import type maplibregl from "maplibre-gl";

import type { ModelId, OutputLayerDefinition } from "../models/shared";
import { fitGeoJsonBounds } from "./mapLayers";

type GeoJsonData = string | GeoJSON.GeoJSON;

export interface ModelLayerIds {
  prefix: string;
  sourceId: string;
  layerId: string;
}

interface RegisteredLayer extends ModelLayerIds {
  data: GeoJsonData;
}

const layerRegistry = new WeakMap<maplibregl.Map, Map<string, RegisteredLayer>>();

export function getModelLayerIds(
  modelId: ModelId,
  taskId: string,
  kind: string
): ModelLayerIds {
  const prefix = `${modelId}-${taskId}-${kind}`;
  return {
    prefix,
    sourceId: `${prefix}-source`,
    layerId: `${prefix}-layer`
  };
}

export function upsertModelGeoJsonLayer(
  map: maplibregl.Map,
  modelId: ModelId,
  taskId: string,
  definition: OutputLayerDefinition,
  data: GeoJsonData
): ModelLayerIds {
  const ids = getModelLayerIds(modelId, taskId, definition.kind);
  const source = map.getSource(ids.sourceId) as maplibregl.GeoJSONSource | undefined;

  if (source) {
    source.setData(data);
  } else {
    map.addSource(ids.sourceId, { type: "geojson", data });
  }

  if (!map.getLayer(ids.layerId)) {
    map.addLayer(createLayerSpecification(ids, definition));
  }

  registryFor(map).set(ids.prefix, { ...ids, data });
  return ids;
}

export function setModelLayerVisibility(
  map: maplibregl.Map,
  modelId: ModelId,
  taskId: string,
  kind: string,
  visible: boolean
) {
  const { layerId } = getModelLayerIds(modelId, taskId, kind);
  if (map.getLayer(layerId)) {
    map.setLayoutProperty(layerId, "visibility", visible ? "visible" : "none");
  }
}

export function setModelLayerOpacity(
  map: maplibregl.Map,
  modelId: ModelId,
  taskId: string,
  definition: OutputLayerDefinition,
  opacity: number
) {
  const { layerId } = getModelLayerIds(modelId, taskId, definition.kind);
  if (!map.getLayer(layerId)) return;
  map.setPaintProperty(
    layerId,
    `${definition.geometry}-opacity`,
    Math.min(1, Math.max(0, opacity))
  );
}

export function focusModelLayer(
  map: maplibregl.Map,
  modelId: ModelId,
  taskId: string,
  kind: string
): boolean {
  const ids = getModelLayerIds(modelId, taskId, kind);
  const registered = layerRegistry.get(map)?.get(ids.prefix);
  if (registered && typeof registered.data !== "string") {
    return fitGeoJsonBounds(map, registered.data);
  }

  const features = map.querySourceFeatures?.(ids.sourceId) ?? [];
  return fitGeoJsonBounds(map, {
    type: "FeatureCollection",
    features: features.map(({ type, properties, geometry, id }) => ({
      type,
      properties,
      geometry,
      ...(id === undefined ? {} : { id })
    })) as GeoJSON.Feature[]
  });
}

export function removeTaskLayers(map: maplibregl.Map, modelId: ModelId, taskId: string) {
  const taskPrefix = `${modelId}-${taskId}-`;
  const registry = layerRegistry.get(map);
  const entries = [...(registry?.values() ?? [])].filter(({ prefix }) => prefix.startsWith(taskPrefix));

  for (const { layerId } of entries.reverse()) {
    if (map.getLayer(layerId)) map.removeLayer(layerId);
  }
  for (const { prefix, sourceId } of entries) {
    if (map.getSource(sourceId)) map.removeSource(sourceId);
    registry?.delete(prefix);
  }

  const style = map.getStyle?.();
  for (const layer of [...(style?.layers ?? [])].reverse()) {
    if (layer.id.startsWith(taskPrefix) && map.getLayer(layer.id)) map.removeLayer(layer.id);
  }
  for (const sourceId of Object.keys(style?.sources ?? {})) {
    if (sourceId.startsWith(taskPrefix) && map.getSource(sourceId)) map.removeSource(sourceId);
  }
}

function registryFor(map: maplibregl.Map): Map<string, RegisteredLayer> {
  const existing = layerRegistry.get(map);
  if (existing) return existing;
  const created = new Map<string, RegisteredLayer>();
  layerRegistry.set(map, created);
  return created;
}

function createLayerSpecification(
  ids: ModelLayerIds,
  definition: OutputLayerDefinition
): maplibregl.LayerSpecification {
  if (definition.geometry === "line") {
    return {
      id: ids.layerId,
      type: "line",
      source: ids.sourceId,
      paint: {
        "line-color": definition.color,
        "line-width": definition.primary ? 4 : 3,
        "line-opacity": definition.defaultOpacity
      }
    };
  }
  if (definition.geometry === "circle") {
    return {
      id: ids.layerId,
      type: "circle",
      source: ids.sourceId,
      paint: {
        "circle-color": definition.color,
        "circle-radius": definition.primary ? 7 : 5,
        "circle-opacity": definition.defaultOpacity,
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 1
      }
    };
  }
  return {
    id: ids.layerId,
    type: "fill",
    source: ids.sourceId,
    paint: {
      "fill-color": definition.color,
      "fill-opacity": definition.defaultOpacity,
      "fill-outline-color": definition.color
    }
  };
}
