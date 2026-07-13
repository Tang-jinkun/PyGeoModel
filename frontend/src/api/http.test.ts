import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, requestJson, resolveAssetUrl } from "./http";

afterEach(() => vi.unstubAllGlobals());

describe("requestJson", () => {
  it("normalizes FastAPI detail messages", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: { message: "DEM missing" } }),
      { status: 404, headers: { "Content-Type": "application/json" } }
    )));
    await expect(requestJson("/api/test")).rejects.toEqual(expect.objectContaining<Pick<ApiError, "message" | "status">>({ message: "DEM missing", status: 404 }));
  });

  it("resolves relative output URLs", () => {
    expect(resolveAssetUrl("/outputs/a.geojson")).toBe("/outputs/a.geojson");
  });
});
