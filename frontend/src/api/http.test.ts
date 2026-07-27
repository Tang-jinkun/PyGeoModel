import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, requestJson, resolveApiUrl, resolveAssetUrl } from "./http";

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

  it.each([
    ["", "/api/health", "/api/health"],
    ["/PyGeoModel/", "/api/health", "/PyGeoModel/api/health"],
    ["http://124.221.208.30:8000/", "/api/health", "http://124.221.208.30:8000/api/health"]
  ])("resolves API base %s", (base, path, expected) => {
    expect(resolveApiUrl(path, { apiBaseUrl: base })).toBe(expected);
  });

  it("preserves map template placeholders", () => {
    expect(resolveApiUrl("/api/tiles/{z}/{x}/{y}", { apiBaseUrl: "/PyGeoModel" }))
      .toBe("/PyGeoModel/api/tiles/{z}/{x}/{y}");
  });

  it("rejects raw output paths", () => {
    expect(() => resolveAssetUrl("/outputs/a.geojson")).toThrow();
  });

  it("requires an API path below the /api/ prefix", () => {
    expect(() => resolveApiUrl("/api", { apiBaseUrl: "" })).toThrow();
  });

  it("keeps an explicitly empty runtime base over the build fallback", () => {
    expect(resolveApiUrl("/api/health", { apiBaseUrl: "" }, "/build"))
      .toBe("/api/health");
  });
});
