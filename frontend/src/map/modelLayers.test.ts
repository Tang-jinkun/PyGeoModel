import { describe, expect, it, vi } from "vitest";

import type { OutputLayerDefinition } from "../models/shared";
import {
  focusModelLayer,
  removeTaskLayers,
  setModelLayerOpacity,
  setModelLayerVisibility,
  upsertModelGeoJsonLayer
} from "./modelLayers";

const polygon: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [{
    type: "Feature",
    properties: {},
    geometry: {
      type: "Polygon",
      coordinates: [[[79, 31], [80, 31], [80, 32], [79, 31]]]
    }
  }]
};

describe("model layers", () => {
  it.each([
    ["fill", "fill", "fill-opacity"],
    ["line", "line", "line-opacity"],
    ["circle", "circle", "circle-opacity"]
  ] as const)("creates a prefixed %s layer", (geometry, layerType, opacityProperty) => {
    const map = new MemoryMap();
    const definition = layerDefinition(geometry);

    upsertModelGeoJsonLayer(map.asMap(), "uav", "task-7", definition, polygon);

    expect(map.sources.has(`uav-task-7-result_${geometry}-source`)).toBe(true);
    expect(map.layers.get(`uav-task-7-result_${geometry}-layer`)).toEqual(expect.objectContaining({
      type: layerType,
      source: `uav-task-7-result_${geometry}-source`,
      paint: expect.objectContaining({ [opacityProperty]: 0.4 })
    }));
  });

  it("updates existing source data without adding duplicate layers", () => {
    const map = new MemoryMap();
    const definition = layerDefinition("line");
    upsertModelGeoJsonLayer(map.asMap(), "mobility", "task-1", definition, polygon);
    upsertModelGeoJsonLayer(map.asMap(), "mobility", "task-1", definition, { type: "FeatureCollection", features: [] });

    expect(map.addSource).toHaveBeenCalledTimes(1);
    expect(map.addLayer).toHaveBeenCalledTimes(1);
    expect(map.sourceData.get("mobility-task-1-result_line-source")).toEqual({
      type: "FeatureCollection",
      features: []
    });
  });

  it("changes visibility and clamps geometry-specific opacity", () => {
    const map = new MemoryMap();
    const definition = layerDefinition("circle");
    upsertModelGeoJsonLayer(map.asMap(), "artillery", "task-2", definition, polygon);

    setModelLayerVisibility(map.asMap(), "artillery", "task-2", definition.kind, false);
    setModelLayerOpacity(map.asMap(), "artillery", "task-2", definition, 4);

    expect(map.setLayoutProperty).toHaveBeenCalledWith(
      "artillery-task-2-result_circle-layer",
      "visibility",
      "none"
    );
    expect(map.setPaintProperty).toHaveBeenCalledWith(
      "artillery-task-2-result_circle-layer",
      "circle-opacity",
      1
    );
  });

  it("focuses data bounds and removes only the selected task layers", () => {
    const map = new MemoryMap();
    const first = layerDefinition("fill");
    const second = { ...layerDefinition("line"), kind: "alternate" };
    upsertModelGeoJsonLayer(map.asMap(), "uav", "task-1", first, polygon);
    upsertModelGeoJsonLayer(map.asMap(), "uav", "task-1", second, polygon);
    upsertModelGeoJsonLayer(map.asMap(), "uav", "task-10", first, polygon);

    expect(focusModelLayer(map.asMap(), "uav", "task-1", first.kind)).toBe(true);
    expect(map.fitBounds).toHaveBeenCalledWith(
      expect.objectContaining({ _sw: expect.anything(), _ne: expect.anything() }),
      { padding: 48, maxZoom: 14 }
    );

    removeTaskLayers(map.asMap(), "uav", "task-1");
    expect([...map.layers.keys()]).toEqual(["uav-task-10-result_fill-layer"]);
    expect([...map.sources.keys()]).toEqual(["uav-task-10-result_fill-source"]);
  });
});

function layerDefinition(geometry: OutputLayerDefinition["geometry"]): OutputLayerDefinition {
  return {
    kind: `result_${geometry}`,
    label: `${geometry} result`,
    color: "#2563eb",
    geometry,
    defaultOpacity: 0.4
  };
}

class MemoryMap {
  sources = new Map<string, { type: "geojson"; data: string | GeoJSON.GeoJSON }>();
  sourceData = new Map<string, string | GeoJSON.GeoJSON>();
  layers = new Map<string, Record<string, unknown>>();

  addSource = vi.fn((id: string, source: { type: "geojson"; data: string | GeoJSON.GeoJSON }) => {
    this.sources.set(id, source);
    this.sourceData.set(id, source.data);
  });
  getSource = vi.fn((id: string) => {
    if (!this.sources.has(id)) return undefined;
    return { setData: (data: string | GeoJSON.GeoJSON) => this.sourceData.set(id, data) };
  });
  removeSource = vi.fn((id: string) => this.sources.delete(id));
  addLayer = vi.fn((layer: Record<string, unknown>) => this.layers.set(layer.id as string, layer));
  getLayer = vi.fn((id: string) => this.layers.get(id));
  removeLayer = vi.fn((id: string) => this.layers.delete(id));
  setLayoutProperty = vi.fn();
  setPaintProperty = vi.fn();
  fitBounds = vi.fn();

  asMap() {
    return this as never;
  }
}
