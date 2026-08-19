import { afterEach, describe, expect, it } from "vitest";

import { createOfflineStyle, createTiandituStyle } from "./tiandituStyle";

describe("createTiandituStyle", () => {
  afterEach(() => {
    delete window.__PYGEOMODEL_RUNTIME_CONFIG__;
  });

  it("routes TianDiTu raster requests through the same-origin tile proxy", () => {
    window.__PYGEOMODEL_RUNTIME_CONFIG__ = { apiBaseUrl: "http://localhost:8000" };
    const style = createTiandituStyle();

    expect(style.version).toBe(8);
    expect(style.sources.tianditu_vector.tiles[0]).toBe(
      "http://localhost:8000/api/map/tianditu/t0/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=vec&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}"
    );
    expect(JSON.stringify(style)).not.toContain("tk=");
    expect(style.layers.map(({ id }) => id)).toEqual(["tianditu_vector", "tianditu_annotation"]);
  });

  it("creates a style with no external sources for offline mode", () => {
    const style = createOfflineStyle();

    expect(style).toEqual({ version: 8, sources: {}, layers: [] });
  });
});
