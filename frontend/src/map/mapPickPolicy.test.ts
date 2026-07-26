import { describe, expect, it } from "vitest";

import { isCoordinateInDemBounds, isSingleClickTarget } from "./mapPickPolicy";

describe("map pick policy", () => {
  it("rejects a coordinate outside the selected DEM bounds", () => {
    expect(isCoordinateInDemBounds([80.1, 31.5], [79.7, 31.4, 79.9, 31.6])).toBe(false);
    expect(isCoordinateInDemBounds([79.8, 31.5], [79.7, 31.4, 79.9, 31.6])).toBe(true);
  });

  it("finishes one-click targets immediately but keeps routes open", () => {
    expect(isSingleClickTarget("point")).toBe(true);
    expect(isSingleClickTarget("start")).toBe(true);
    expect(isSingleClickTarget("route")).toBe(false);
  });
});
