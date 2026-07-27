import { execFile } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { promisify } from "node:util";
import vm from "node:vm";
import { afterEach, describe, expect, it } from "vitest";

import { getRuntimeConfig, normalizeApiBase } from "./runtime";

const execFileAsync = promisify(execFile);

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

  it("preserves an explicitly empty runtime base over the build fallback", () => {
    window.__PYGEOMODEL_RUNTIME_CONFIG__ = { apiBaseUrl: "" };
    expect(getRuntimeConfig("/build").apiBaseUrl).toBe("");
  });

  it("rejects unsafe or ambiguous bases", () => {
    for (const value of [
      "/root?x=1", "/root#x", "https://u:p@example.com", "/PyGeoModel/api",
      "javascript:alert(1)", "//other.example/root", "api-root"
    ]) {
      expect(() => normalizeApiBase(value)).toThrow();
    }
  });

  it("round-trips hostile text through the generated external script", async () => {
    const directory = await mkdtemp(join(tmpdir(), "pygeomodel-runtime-"));
    const output = join(directory, "runtime-config.js");
    const value = '/PyGeoModel"</script><script>bad()</script>';
    try {
      await execFileAsync(process.execPath, [
        resolve(process.cwd(), "docker/write-runtime-config.mjs"),
        output
      ], { env: { ...process.env, PYGEOMODEL_API_BASE_URL: value } });
      const context = { window: {}, bad: () => { throw new Error("injected code executed"); } };
      vm.runInNewContext(await readFile(output, "utf8"), context);
      expect(context.window).toEqual({
        __PYGEOMODEL_RUNTIME_CONFIG__: { apiBaseUrl: value }
      });
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  });
});
