import { describe, expect, it } from "vitest";

import { customLayerProjectionMatrix } from "./customLayerProjection";

describe("customLayerProjectionMatrix", () => {
  it("extracts the MapLibre custom-layer mercator projection matrix", () => {
    const worldSpaceMatrix = new Float32Array(16).fill(1);
    const mercatorMatrix = new Float64Array(16).fill(2);

    expect(customLayerProjectionMatrix({
      modelViewProjectionMatrix: worldSpaceMatrix,
      defaultProjectionData: { mainMatrix: mercatorMatrix }
    })).toBe(mercatorMatrix);
  });

  it("preserves the Mapbox matrix argument", () => {
    const matrix = Array.from({ length: 16 }, (_, index) => index);

    expect(customLayerProjectionMatrix(matrix)).toBe(matrix);
  });
});
