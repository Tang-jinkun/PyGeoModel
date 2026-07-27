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
  listMultiRadarTasks: vi.fn(async () => [finishedMultiRadarTask()]),
  createMultiRadarTask: vi.fn(),
  getMultiRadarTask: vi.fn(async () => finishedMultiRadarTask()),
  getMultiRadarOutputs: vi.fn(async () => [multiRadarOutputFile()]),
  findMultiRadarOutputPath: vi.fn()
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

  it("keeps the result inspector closed until a task is selected", async () => {
    const wrapper = mountApp();
    await flushPromises();

    expect(wrapper.find("[data-workbench-region='inspector']").exists()).toBe(true);
    expect(wrapper.get(".gis-workbench").attributes("data-inspector-open")).toBe("false");
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

  it("reuses the result inspector for multi-radar task downloads", async () => {
    const wrapper = mountApp();
    await flushPromises();

    await wrapper.findAll(".task-tab").find((tab) => tab.text().includes("历史记录"))!.trigger("click");
    await wrapper.get('[data-action="files"]').trigger("click");
    await flushPromises();

    expect(wrapper.get(".gis-workbench").attributes("data-inspector-open")).toBe("true");
    expect(wrapper.get("[data-result-detail]").text()).toContain("多雷达协同");
    expect(wrapper.get("[data-result-files] a").attributes("href"))
      .toBe("/api/radar/multi-coverage/multi-1/outputs/visible_union_geojson");
  });
});

function mountApp() {
  return mount(App, { global: { stubs: { MapWorkspace: MapWorkspaceStub } } });
}

function finishedMultiRadarTask() {
  return {
    task_id: "multi-1",
    dem_id: "dem-1",
    status: "finished" as const,
    result_state: "ready" as const,
    progress: 100,
    message: "done",
    metrics: {
      visible_union_area_m2: 2_500_000,
      overlap_area_m2: 500_000,
      blind_area_m2: 1_000_000,
      theoretical_union_area_m2: 3_500_000,
      successful_station_count: 2,
      failed_station_count: 0
    },
    output_files: [],
    stations: []
  };
}

function multiRadarOutputFile() {
  return {
    kind: "visible_union_geojson",
    filename: "visible_union.geojson",
    media_type: "application/geo+json",
    label: "Visible union GeoJSON",
    required: true,
    exists: true,
    download_path: "/api/radar/multi-coverage/multi-1/outputs/visible_union_geojson"
  };
}
