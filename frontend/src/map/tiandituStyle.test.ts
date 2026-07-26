import { describe, expect, it } from "vitest";

import { createTiandituStyle } from "./tiandituStyle";

describe("createTiandituStyle", () => {
  it("creates TianDiTu vector and annotation raster sources from a browser token", () => {
    const style = createTiandituStyle("browser-token");

    expect(style.version).toBe(8);
    expect(style.sources.tianditu_vector.tiles[0]).toContain("LAYER=vec");
    expect(style.sources.tianditu_vector.tiles[0]).toContain("tk=browser-token");
    expect(style.layers.map(({ id }) => id)).toEqual(["tianditu_vector", "tianditu_annotation"]);
  });
});
