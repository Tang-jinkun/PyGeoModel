import { describe, expect, it } from "vitest";

import { applyMapboxAccessToken } from "./mapboxAccessToken";

describe("applyMapboxAccessToken", () => {
  it("assigns the configured browser token before a Mapbox map is created", () => {
    const engine = { accessToken: "" };
    applyMapboxAccessToken(engine, "pk.test-token");
    expect(engine.accessToken).toBe("pk.test-token");
  });
});
