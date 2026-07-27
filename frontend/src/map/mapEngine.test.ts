import { describe, expect, it } from "vitest";

import { selectMapEngine, type MapEngineModule } from "./mapEngine";

function fakeEngine() {
  return { accessToken: "" } as unknown as MapEngineModule;
}

describe("selectMapEngine", () => {
  it("selects MapLibre when the engine setting is missing", () => {
    const maplibre = fakeEngine();
    const mapbox = fakeEngine();

    expect(selectMapEngine({}, { maplibre, mapbox })).toBe(maplibre);
  });

  it("selects MapLibre explicitly without requiring a token", () => {
    const maplibre = fakeEngine();
    const mapbox = fakeEngine();

    expect(selectMapEngine({ name: "maplibre" }, { maplibre, mapbox })).toBe(maplibre);
  });

  it("selects Mapbox and applies its token", () => {
    const maplibre = fakeEngine();
    const mapbox = fakeEngine();

    expect(selectMapEngine(
      { name: "mapbox", mapboxAccessToken: "pk.test-mapbox-token" },
      { maplibre, mapbox }
    )).toBe(mapbox);
    expect(mapbox.accessToken).toBe("pk.test-mapbox-token");
  });

  it("rejects Mapbox mode without a token", () => {
    expect(() => selectMapEngine(
      { name: "mapbox", mapboxAccessToken: "  " },
      { maplibre: fakeEngine(), mapbox: fakeEngine() }
    )).toThrow("VITE_MAPBOX_ACCESS_TOKEN is required when VITE_MAP_ENGINE=mapbox");
  });

  it("rejects unsupported engine values", () => {
    expect(() => selectMapEngine(
      { name: "leaflet" },
      { maplibre: fakeEngine(), mapbox: fakeEngine() }
    )).toThrow('VITE_MAP_ENGINE must be "maplibre" or "mapbox"');
  });
});
