import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type maplibregl from "maplibre-gl";

import { createSpatialDraft } from "../../map/spatialInput";
import MapWorkspace from "./MapWorkspace.vue";

const demA = {
  dem_id: "dem-a",
  filename: "a.tif",
  crs: "EPSG:4326",
  bounds: [79, 31, 80, 32],
  resolution: [30, 30],
  width: 100,
  height: 100,
  nodata: null,
  task_count: 0,
  active_task_count: 0
};

const mapHarness = vi.hoisted(() => {
  const instances: FakeMap[] = [];
  return { instances, constructor: vi.fn() };
});

vi.mock("maplibre-gl", () => ({
  default: {
    Map: class {
      constructor(options: unknown) {
        const map = new FakeMap(options);
        mapHarness.instances.push(map);
        mapHarness.constructor(options);
        return map;
      }
    },
    NavigationControl: class {}
  }
}));

beforeEach(() => {
  mapHarness.instances.length = 0;
  mapHarness.constructor.mockClear();
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
    callback(0);
    return 1;
  });
});

describe("MapWorkspace", () => {
  it("passes a caller-provided local style object through unchanged", () => {
    const explicitStyle: maplibregl.StyleSpecification = {
      version: 8,
      sources: {
        workspace: {
          type: "geojson",
          data: {
            type: "FeatureCollection",
            features: []
          }
        }
      },
      layers: [{
        id: "workspace-fill",
        type: "fill",
        source: "workspace",
        paint: {
          "fill-color": "#2563eb",
          "fill-opacity": 0.15
        }
      }]
    };
    const wrapper = mount(MapWorkspace, {
      props: {
        kind: "point",
        draft: createSpatialDraft("point"),
        mapStyle: explicitStyle
      }
    });
    const map = mapHarness.instances[0];
    const style = (map.options as { style: unknown }).style;

    expect(style).toBe(explicitStyle);
    expect(style).not.toStrictEqual({
      version: 8,
      sources: {},
      layers: []
    });

    wrapper.unmount();
  });

  it("uses a local empty style by default instead of an external URL", () => {
    const wrapper = mount(MapWorkspace, {
      props: {
        kind: "point",
        draft: createSpatialDraft("point")
      }
    });
    const map = mapHarness.instances[0];
    const style = (map.options as { style: unknown }).style;

    expect(style).toStrictEqual({
      version: 8,
      sources: {},
      layers: []
    });
    expect(JSON.stringify(style)).not.toContain("https://");

    wrapper.unmount();
  });

  it("creates one map, emits normalized route edits, resizes after transitions, and removes on unmount", async () => {
    const host = document.createElement("div");
    host.className = "workspace-shell";
    document.body.append(host);
    const wrapper = mount(MapWorkspace, {
      attachTo: host,
      props: {
        kind: "point-or-route",
        draft: createSpatialDraft("point-or-route"),
        editing: true
      }
    });
    const map = mapHarness.instances[0];

    expect(mapHarness.constructor).toHaveBeenCalledOnce();
    map.emit("click", { lngLat: { lng: 79.8123456789, lat: 31.4123456789 } });
    expect(wrapper.emitted("coordinate-edit")?.[0]).toEqual([[79.812346, 31.412346]]);
    expect(wrapper.emitted("spatial-edit")?.[0]).toEqual([{
      type: "append",
      coordinate: [79.812346, 31.412346]
    }]);

    host.dispatchEvent(new Event("transitionend"));
    expect(map.resize).toHaveBeenCalled();

    wrapper.unmount();
    expect(map.remove).toHaveBeenCalledOnce();
    expect(mapHarness.constructor).toHaveBeenCalledOnce();
  });

  it("sequences start and end edits from its controlled draft", async () => {
    const wrapper = mount(MapWorkspace, {
      props: {
        kind: "start-end",
        draft: createSpatialDraft("start-end"),
        editing: true
      }
    });
    const map = mapHarness.instances[0];
    map.emit("click", { lngLat: { lng: 10, lat: 20 } });
    expect(wrapper.emitted("spatial-edit")?.[0]).toEqual([{ type: "set-start", coordinate: [10, 20] }]);

    await wrapper.setProps({
      draft: {
        ...createSpatialDraft("start-end"),
        start: [10, 20]
      }
    });
    map.emit("click", { lngLat: { lng: 30, lat: 40 } });
    expect(wrapper.emitted("spatial-edit")?.[1]).toEqual([{ type: "set-end", coordinate: [30, 40] }]);
  });

  it("adds a threat from the map when no existing threat is active", () => {
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "threat-map-1") });
    const wrapper = mount(MapWorkspace, {
      props: {
        kind: "start-end-threats",
        draft: createSpatialDraft("start-end-threats"),
        editing: true,
        editTarget: "threat"
      }
    });
    const map = mapHarness.instances[0];

    map.emit("click", { lngLat: { lng: 80.25, lat: 32.5 } });

    expect(wrapper.emitted("spatial-edit")?.[0]).toEqual([{
      type: "add-threat",
      threat: { id: "threat-map-1", coordinate: [80.25, 32.5] }
    }]);
  });

  it("always renders finish, undo, and clear commands while editing", () => {
    const wrapper = mount(MapWorkspace, {
      props: {
        kind: "point",
        draft: createSpatialDraft("point"),
        editing: true
      }
    });

    expect(wrapper.get('[data-action="finish-editing"]')).toBeTruthy();
    expect(wrapper.get('[data-action="undo-editing"]')).toBeTruthy();
    expect(wrapper.get('[data-action="clear-editing"]')).toBeTruthy();
  });

  it("runs custom layer cleanup when the map is removed", () => {
    const wrapper = mount(MapWorkspace, {
      props: {
        kind: "point",
        draft: createSpatialDraft("point")
      }
    });
    const map = mapHarness.instances[0];
    const onRemove = vi.fn();
    map.addLayer({ id: "custom-scene", onRemove });

    wrapper.unmount();

    expect(onRemove).toHaveBeenCalledOnce();
  });

  it("does not reinstall unchanged DEM terrain but does sync a new DEM", async () => {
    const wrapper = mount(MapWorkspace, {
      props: {
        kind: "point",
        draft: createSpatialDraft("point"),
        dem: demA
      }
    });
    const map = mapHarness.instances[0];
    map.emit("load", undefined);
    expect(map.setTerrain).toHaveBeenCalledTimes(2);

    await wrapper.setProps({ dem: { ...demA } });
    expect(map.setTerrain).toHaveBeenCalledTimes(2);

    await wrapper.setProps({ dem: { ...demA, dem_id: "dem-b", filename: "b.tif" } });
    expect(map.setTerrain).toHaveBeenCalledTimes(4);
  });
});

class FakeMap {
  handlers = new Map<string, (event?: never) => void>();
  resize = vi.fn();
  layers = new Map<string, { id: string; onRemove?: () => void }>();
  remove = vi.fn(() => {
    for (const layer of this.layers.values()) layer.onRemove?.();
    this.layers.clear();
  });
  addControl = vi.fn();
  addSource = vi.fn();
  getSource = vi.fn();
  getLayer = vi.fn((id: string) => this.layers.get(id));
  addLayer = vi.fn((layer: { id: string; onRemove?: () => void }) => {
    this.layers.set(layer.id, layer);
  });
  removeLayer = vi.fn((id: string) => {
    const layer = this.layers.get(id);
    layer?.onRemove?.();
    this.layers.delete(id);
  });
  removeSource = vi.fn();
  setTerrain = vi.fn();

  constructor(public options: unknown) {}

  on = vi.fn((name: string, handler: (event?: never) => void) => {
    this.handlers.set(name, handler);
    return this;
  });

  off = vi.fn((name: string, handler: (event?: never) => void) => {
    if (this.handlers.get(name) === handler) this.handlers.delete(name);
    return this;
  });

  emit(name: string, event: unknown) {
    this.handlers.get(name)?.(event as never);
  }
}
