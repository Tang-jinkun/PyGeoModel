import { describe, expect, it } from "vitest";

import { createTiandituStyle } from "./tiandituStyle";

describe("createTiandituStyle", () => {
  it("routes TianDiTu raster requests through the same-origin tile proxy", () => {
    const style = createTiandituStyle();

    expect(style.version).toBe(8);
    expect(style.sources.tianditu_vector.tiles[0]).toContain("LAYER=vec");
    expect(style.sources.tianditu_vector.tiles[0]).toContain("/PyGeoModel/tianditu/t0/vec_w/wmts");
    expect(style.sources.tianditu_vector.tiles[0]).toContain("PROXY_VERSION=2");
    expect(style.sources.tianditu_vector.tiles[0]).not.toContain("tk=");
    expect(style.layers.map(({ id }) => id)).toEqual(["tianditu_vector", "tianditu_annotation"]);
  });
});
