import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createSpatialDraft } from "../../map/spatialInput";
import MapWorkspace from "./MapWorkspace.vue";

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
});

class FakeMap {
  handlers = new Map<string, (event?: never) => void>();
  resize = vi.fn();
  remove = vi.fn();
  addControl = vi.fn();
  addSource = vi.fn();
  getSource = vi.fn();
  getLayer = vi.fn();
  removeLayer = vi.fn();
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
