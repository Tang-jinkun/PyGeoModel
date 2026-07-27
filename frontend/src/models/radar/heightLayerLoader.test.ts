import { describe, expect, it, vi } from "vitest";

import { createHeightLayerLoader, resolveHeightLayerDescriptors } from "./heightLayerLoader";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => { resolve = resolvePromise; });
  return { promise, resolve };
}

describe("createHeightLayerLoader", () => {
  it("maps manifest artifact kinds through the live descriptor URLs", () => {
    expect(resolveHeightLayerDescriptors({
      height_layers: [{ height_m: 100, visible_kind: "height_visible_100", blocked_kind: "height_blocked_100" }]
    }, {
      height_visible_100: "/api/radar/coverage/radar-1/outputs/height_visible_100",
      height_blocked_100: "/api/radar/coverage/radar-1/outputs/height_blocked_100"
    })).toEqual([{
      heightM: 100,
      visibleUrl: "/api/radar/coverage/radar-1/outputs/height_visible_100",
      blockedUrl: "/api/radar/coverage/radar-1/outputs/height_blocked_100"
    }]);
  });

  it("reuses pending and cached data for the same task and height", async () => {
    const visible = deferred<GeoJSON.GeoJSON>();
    const fetchGeoJson = vi.fn(() => visible.promise);
    const loader = createHeightLayerLoader(fetchGeoJson);
    loader.setTask("radar-1");

    const first = loader.load(100, "/visible.json", null);
    const second = loader.load(100, "/visible.json", null);
    expect(fetchGeoJson).toHaveBeenCalledTimes(1);
    visible.resolve({ type: "FeatureCollection", features: [] });
    expect(await first).toEqual(await second);

    await loader.load(100, "/visible.json", null);
    expect(fetchGeoJson).toHaveBeenCalledTimes(1);
  });

  it("rejects stale completion after changing tasks", async () => {
    const oldVisible = deferred<GeoJSON.GeoJSON>();
    const fetchGeoJson = vi.fn()
      .mockReturnValueOnce(oldVisible.promise)
      .mockResolvedValueOnce({ type: "FeatureCollection", features: [] });
    const loader = createHeightLayerLoader(fetchGeoJson);
    loader.setTask("radar-old");
    const stale = loader.load(100, "/old.json", null);

    loader.setTask("radar-new");
    const current = loader.load(100, "/new.json", null);
    oldVisible.resolve({ type: "FeatureCollection", features: [] });

    expect(await stale).toBeNull();
    expect(await current).not.toBeNull();
    expect(fetchGeoJson).toHaveBeenCalledTimes(2);
  });
});
