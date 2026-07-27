import { describe, expect, it } from "vitest";

import { customLayerProjectionMatrix } from "./customLayerProjection";

describe("customLayerProjectionMatrix", () => {
  it("extracts the MapLibre model-view-projection matrix", () => {
    const matrix = new Float32Array(16);

    expect(customLayerProjectionMatrix({ modelViewProjectionMatrix: matrix })).toBe(matrix);
  });

  it("preserves the Mapbox matrix argument", () => {
    const matrix = Array.from({ length: 16 }, (_, index) => index);

    expect(customLayerProjectionMatrix(matrix)).toBe(matrix);
  });
});
