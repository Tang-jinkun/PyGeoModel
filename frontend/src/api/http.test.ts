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

  it("retains structured FastAPI detail in the error message", async () => {
    const detail = [{
      type: "missing",
      loc: ["body", "dem_id"],
      msg: "Field required",
      input: { radar: { lon: 79.8, lat: 31.4 } }
    }];
    const payload = { detail };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify(payload),
      { status: 422, headers: { "Content-Type": "application/json" } }
    )));

    await expect(requestJson("/api/test")).rejects.toEqual(expect.objectContaining<Pick<ApiError, "message" | "status" | "payload">>({
      message: JSON.stringify(detail),
      status: 422,
      payload
    }));
  });

  it("resolves relative output URLs", () => {
    expect(resolveAssetUrl("/outputs/a.geojson")).toBe("/outputs/a.geojson");
  });
});
