import { flushPromises, mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App.vue";

vi.mock("./api/dem", () => ({
  listDems: vi.fn(async () => []), uploadDem: vi.fn(), deleteDem: vi.fn(),
  demTileUrlTemplate: vi.fn(() => ""), demTerrainUrlTemplate: vi.fn(() => "")
}));
vi.mock("./api/tasks", () => ({
  createTaskClient: vi.fn(() => ({ create: vi.fn(), get: vi.fn(), list: vi.fn(), metrics: vi.fn(), delete: vi.fn() }))
}));
vi.mock("./api/multiRadar", () => ({
  listMultiRadarTasks: vi.fn(async () => []), createMultiRadarTask: vi.fn(), getMultiRadarTask: vi.fn()
}));
vi.mock("./models/radar/layerAdapter", () => ({
  createRadarLayerAdapter: vi.fn(() => ({ errors: {}, clear: vi.fn(), dispose: vi.fn(), setRadarVisible: vi.fn() }))
}));
vi.mock("./map/mapEngine", () => ({
  default: { Map: class {}, NavigationControl: class {} }
}));

const MapWorkspaceStub = defineComponent({
  name: "MapWorkspace",
  emits: ["map-ready", "spatial-edit", "out-of-bounds"],
  setup() { return () => h("div", { "data-map-workspace": "" }); }
});

describe("App model run workflow", () => {
  beforeEach(() => vi.clearAllMocks());

  it("opens a configuration dialog immediately when a catalog model is clicked", async () => {
    const wrapper = mountApp();
    await flushPromises();

    expect(wrapper.find("[data-model-run-dialog]").exists()).toBe(false);
    await wrapper.get("[data-model-id='radar']").trigger("click");

    expect(wrapper.get("[data-model-run-dialog='radar']").isVisible()).toBe(true);
  });

  it("uses the expanded map layout without an inspector or map run command", async () => {
    const wrapper = mountApp();
    await flushPromises();

    expect(wrapper.find("[data-workbench-region='inspector']").exists()).toBe(false);
    expect(wrapper.find("[data-action='run-analysis-on-map']").exists()).toBe(false);
    expect(wrapper.find("[data-workbench-region='map']").exists()).toBe(true);
  });

  it("renders the reference status bar with Chinese map and connection details", async () => {
    const wrapper = mountApp();
    await flushPromises();

    const status = wrapper.get("[data-workbench-region='status']");
    expect(status.text()).toContain("坐标");
    expect(status.text()).toContain("高程");
    expect(status.text()).toContain("比例尺");
    expect(status.text()).toContain("坐标系");
    expect(status.text()).toContain("当前 DEM：未选择");
    expect(status.find(".workbench-status__live").exists()).toBe(true);
  });
});

function mountApp() {
  return mount(App, { global: { stubs: { MapWorkspace: MapWorkspaceStub } } });
}
