import { describe, expect, it, vi } from "vitest";

import { createMultiRadarLayerAdapter } from "./multiRadarLayerAdapter";

describe("multi-radar layer adapter", () => {
  it("evicts the oldest detailed station after five selections", () => {
    const removeDetail = vi.fn();
    const adapter = createMultiRadarLayerAdapter({ removeDetail, maxDetailedSelections: 5 });

    ["a", "b", "c", "d", "e", "f"].forEach((id) => adapter.selectStationDetail(id));

    expect(removeDetail).toHaveBeenCalledWith("a");
    expect(adapter.selectedStationIds()).toEqual(["b", "c", "d", "e", "f"]);
  });

  it("exposes aggregate overlays and controls their map presentation", () => {
    const adapter = createMultiRadarLayerAdapter();
    const map = fakeMap();

    adapter.showAggregate(map as never, aggregate());

    expect(adapter.definitions()).toHaveLength(4);
    expect(adapter.layerStates()).toEqual(expect.arrayContaining([
      expect.objectContaining({ kind: "visible_union_geojson", status: "ready", visible: true })
    ]));
    expect(map.addLayer).toHaveBeenCalledWith(expect.objectContaining({
      id: "multi-radar-overlap",
      paint: expect.objectContaining({ "fill-color": "#d4a017", "fill-outline-color": "#facc15" })
    }));

    adapter.setLayerVisibility(map as never, "visible_union_geojson", false);
    adapter.setLayerOpacity(map as never, "visible_union_geojson", 0.4);
    adapter.raiseLayer(map as never, "overlap_geojson");

    expect(map.setLayoutProperty).toHaveBeenCalledWith("multi-radar-visible", "visibility", "none");
    expect(map.setPaintProperty).toHaveBeenCalledWith("multi-radar-visible", "fill-opacity", 0.4);
    expect(map.moveLayer).toHaveBeenCalledWith("multi-radar-overlap");
    expect(adapter.layerStates().find((layer) => layer.kind === "visible_union_geojson"))
      .toMatchObject({ visible: false, opacity: 0.4 });
  });
});

function aggregate() {
  return {
    visible: polygon(), overlap: polygon(), blind: polygon(), coverageCount: polygon(), stations: polygon()
  };
}

function polygon(): GeoJSON.FeatureCollection {
  return { type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [[[79, 31], [80, 31], [80, 32], [79, 31]]] } }] };
}

function fakeMap() {
  const layers = new Set<string>();
  const sources = new Map<string, { setData: ReturnType<typeof vi.fn> }>();
  return {
    getSource: vi.fn((id: string) => sources.get(id)),
    addSource: vi.fn((id: string) => sources.set(id, { setData: vi.fn() })),
    getLayer: vi.fn((id: string) => layers.has(id) ? { id } : undefined),
    addLayer: vi.fn((layer: { id: string }) => layers.add(layer.id)),
    removeLayer: vi.fn((id: string) => layers.delete(id)),
    removeSource: vi.fn((id: string) => sources.delete(id)),
    setLayoutProperty: vi.fn(),
    setPaintProperty: vi.fn(),
    moveLayer: vi.fn()
  };
}
