/// <reference types="node" />

import { mount } from "@vue/test-utils";
import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it, vi } from "vitest";

import WorkspaceShell from "./WorkspaceShell.vue";

const appCss = readFileSync("src/styles/app.css", "utf8");

afterEach(() => {
  vi.restoreAllMocks();
});

describe("WorkspaceShell", () => {
  it("toggles desktop panels independently", async () => {
    installMatchMedia(false);
    const wrapper = mount(WorkspaceShell);

    expect(region(wrapper, "parameters").attributes("data-open")).toBe("true");
    expect(region(wrapper, "results").attributes("data-open")).toBe("true");

    await wrapper.get('[data-action="toggle-parameters"]').trigger("click");
    expect(region(wrapper, "parameters").attributes("data-open")).toBe("false");
    expect(region(wrapper, "results").attributes("data-open")).toBe("true");
    expect(wrapper.get('[data-action="toggle-parameters"]').attributes("aria-expanded")).toBe("false");
    expect(wrapper.get('[data-action="toggle-results"]').attributes("aria-expanded")).toBe("true");

    await wrapper.get('[data-action="toggle-results"]').trigger("click");
    expect(region(wrapper, "parameters").attributes("data-open")).toBe("false");
    expect(region(wrapper, "results").attributes("data-open")).toBe("false");
  });

  it("keeps narrow drawers mutually exclusive and cleans up its media listener", async () => {
    const mediaQuery = installMatchMedia(true);
    const wrapper = mount(WorkspaceShell);
    await wrapper.vm.$nextTick();

    expect(region(wrapper, "parameters").attributes("data-open")).toBe("false");
    expect(region(wrapper, "results").attributes("data-open")).toBe("false");

    await wrapper.get('[data-action="toggle-parameters"]').trigger("click");
    expect(region(wrapper, "parameters").attributes("data-open")).toBe("true");
    expect(region(wrapper, "results").attributes("data-open")).toBe("false");

    await wrapper.get('[data-action="toggle-results"]').trigger("click");
    expect(region(wrapper, "parameters").attributes("data-open")).toBe("false");
    expect(region(wrapper, "results").attributes("data-open")).toBe("true");
    expect(wrapper.get('[data-action="toggle-parameters"]').attributes("aria-expanded")).toBe("false");
    expect(wrapper.get('[data-action="toggle-results"]').attributes("aria-expanded")).toBe("true");

    await wrapper.get('[data-action="toggle-results"]').trigger("click");
    expect(region(wrapper, "results").attributes("data-open")).toBe("false");
    expect(mediaQuery.addEventListener).toHaveBeenCalledWith("change", expect.any(Function));

    wrapper.unmount();
    expect(mediaQuery.removeEventListener).toHaveBeenCalledWith("change", expect.any(Function));
  });

  it("emits the shell command events", async () => {
    installMatchMedia(false);
    const wrapper = mount(WorkspaceShell);

    await wrapper.get('[data-model-id="mobility"]').trigger("click");
    await wrapper.get('[data-action="open-history"]').trigger("click");
    await wrapper.get('[data-action="toggle-parameters"]').trigger("click");
    await wrapper.get('[data-action="toggle-results"]').trigger("click");

    expect(wrapper.emitted("select-model")?.[0]).toEqual(["mobility"]);
    expect(wrapper.emitted("open-history")).toHaveLength(1);
    expect(wrapper.emitted("toggle-parameters")).toHaveLength(1);
    expect(wrapper.emitted("toggle-results")).toHaveLength(1);
  });

  it("keeps the compact grid minimum within 801 pixels", () => {
    const normalizedCss = appCss.replace(/\s+/g, " ");

    expect(normalizedCss).toContain("--workspace-parameter-track: minmax(180px, var(--parameter-width));");
    expect(normalizedCss).toContain("--workspace-map-track: minmax(240px, 1fr);");
    expect(normalizedCss).toContain("--workspace-result-track: minmax(200px, var(--result-width));");
    expect(52 + 180 + 240 + 200).toBeLessThanOrEqual(801);
  });

  it("isolates desktop collapse rules from the narrow grid cascade", () => {
    const desktop = mediaBlock("(min-width: 1101px)");
    const compact = mediaBlock("(min-width: 801px) and (max-width: 1100px)");
    const narrow = mediaBlock("(max-width: 800px)");
    const firstScopedGrid = appCss.indexOf("@media (min-width: 1101px)");

    expect(appCss.slice(0, firstScopedGrid)).not.toMatch(
      /\.workspace-shell\[data-(?:parameters|results)-open[^\{]*\]\s*\{[^}]*grid-template-columns/
    );
    expect(desktop).toContain('.workspace-shell[data-parameters-open="false"]');
    expect(desktop).toContain('.workspace-shell[data-results-open="false"]');
    expect(desktop).toContain("grid-template-columns:");
    expect(compact).toContain('.workspace-shell[data-parameters-open="false"]');
    expect(compact).toContain('.workspace-shell[data-results-open="false"]');
    expect(compact).toContain("--workspace-map-track: minmax(240px, 1fr);");
    expect(narrow).toContain("grid-template-columns: var(--model-nav-width) minmax(0, 1fr);");
    expect(narrow).not.toMatch(/\.workspace-shell\[data-(?:parameters|results)-open/);
    expect(appCss.indexOf("@media (min-width: 801px) and (max-width: 1100px)")).toBeLessThan(
      appCss.indexOf("@media (max-width: 800px)")
    );
  });
});

function region(wrapper: ReturnType<typeof mount>, name: "parameters" | "results") {
  return wrapper.get(`[data-region="${name}"]`);
}

function mediaBlock(query: string) {
  const start = appCss.indexOf(`@media ${query}`);
  expect(start, `missing @media ${query}`).toBeGreaterThanOrEqual(0);

  const openBrace = appCss.indexOf("{", start);
  let depth = 0;
  for (let index = openBrace; index < appCss.length; index++) {
    if (appCss[index] === "{") depth++;
    if (appCss[index] === "}") depth--;
    if (depth === 0) return appCss.slice(start, index + 1);
  }

  throw new Error(`unterminated @media ${query}`);
}

function installMatchMedia(matches: boolean) {
  const listeners = new Set<(event: MediaQueryListEvent) => void>();
  const mediaQuery = {
    matches,
    media: "(max-width: 800px)",
    onchange: null,
    addListener: vi.fn((listener: (event: MediaQueryListEvent) => void) => listeners.add(listener)),
    removeListener: vi.fn((listener: (event: MediaQueryListEvent) => void) => listeners.delete(listener)),
    addEventListener: vi.fn((type: string, listener: (event: MediaQueryListEvent) => void) => {
      if (type === "change") listeners.add(listener);
    }),
    removeEventListener: vi.fn((type: string, listener: (event: MediaQueryListEvent) => void) => {
      if (type === "change") listeners.delete(listener);
    }),
    dispatchEvent: vi.fn((event: Event) => {
      listeners.forEach((listener) => listener(event as MediaQueryListEvent));
      return true;
    })
  } as unknown as MediaQueryList;

  vi.spyOn(window, "matchMedia").mockImplementation(() => mediaQuery);
  return mediaQuery;
}
