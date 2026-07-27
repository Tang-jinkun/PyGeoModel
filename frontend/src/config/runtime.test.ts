import { afterEach, describe, expect, it } from "vitest";

import { getRuntimeConfig, normalizeApiBase } from "./runtime";


afterEach(() => {
  delete window.__PYGEOMODEL_RUNTIME_CONFIG__;
});


describe("runtime API configuration", () => {
  it.each([
    ["", ""],
    ["/PyGeoModel/", "/PyGeoModel"],
    ["http://124.221.208.30:8000/", "http://124.221.208.30:8000"]
  ])("normalizes %s", (value, expected) => {
    expect(normalizeApiBase(value)).toBe(expected);
  });

  it("prefers runtime configuration over the build fallback", () => {
    window.__PYGEOMODEL_RUNTIME_CONFIG__ = { apiBaseUrl: "/runtime" };
    expect(getRuntimeConfig("/build").apiBaseUrl).toBe("/runtime");
  });

  it("rejects unsafe or ambiguous bases", () => {
    for (const value of [
      "/root?x=1", "/root#x", "https://u:p@example.com", "/PyGeoModel/api",
      "javascript:alert(1)", "//other.example/root", "api-root"
    ]) {
      expect(() => normalizeApiBase(value)).toThrow();
    }
  });
});
