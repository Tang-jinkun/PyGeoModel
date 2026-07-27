import { describe, expect, it } from "vitest";

import { demTerrainUrlTemplate, demTileUrlTemplate } from "./dem";

describe("demTerrainUrlTemplate", () => {
  it("returns an absolute URL for Mapbox worker tile requests", () => {
    expect(demTerrainUrlTemplate("dem-a")).toBe(
      `${window.location.origin}/api/dem/dem-a/terrain/{z}/{x}/{y}.png`
    );
  });

  it("returns an absolute URL for Mapbox raster tile requests", () => {
    expect(demTileUrlTemplate("dem-a")).toBe(
      `${window.location.origin}/api/dem/dem-a/tiles/{z}/{x}/{y}.png`
    );
  });
});
