import { flushPromises, mount } from "@vue/test-utils";
import { defineComponent, h, nextTick, toRaw } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App.vue";
import ModelParameterPanel from "./components/forms/ModelParameterPanel.vue";
import TaskHistoryDrawer from "./components/tasks/TaskHistoryDrawer.vue";
import { getModelDefinition, MODEL_IDS, type ModelId } from "./models/registry";
import type { BaseModelRequest, TaskSummary } from "./models/shared";

const clients = new Map<string, ReturnType<typeof makeClient>>();
let taskSequence = 0;
const radarLayerAdapter = vi.hoisted(() => ({
  errors: {},
  showTask: vi.fn(async () => undefined),
  setRadarVisible: vi.fn(),
  clear: vi.fn(),
  dispose: vi.fn()
}));

vi.mock("./api/dem", () => ({
  listDems: vi.fn(async () => []),
  uploadDem: vi.fn(),
  deleteDem: vi.fn(),
  demTileUrlTemplate: vi.fn(() => ""),
  demTerrainUrlTemplate: vi.fn(() => "")
}));

vi.mock("./api/tasks", () => ({
  createTaskClient: vi.fn((basePath: string) => {
    const existing = clients.get(basePath);
    if (existing) return existing;
    const client = makeClient();
    clients.set(basePath, client);
    return client;
  })
}));

vi.mock("./models/radar/layerAdapter", () => ({
  createRadarLayerAdapter: vi.fn(() => radarLayerAdapter)
}));

vi.mock("maplibre-gl", () => ({
  default: {
    Map: class {
      addControl() {}
      on() {}
      off() {}
      remove() {}
    },
    NavigationControl: class {}
  }
}));

const MapWorkspaceStub = defineComponent({
  name: "MapWorkspace",
  emits: ["map-ready", "spatial-edit", "finish"],
  setup() {
    return () => h("div", { "data-map-workspace": "" });
  }
});

describe("App workspace wiring", () => {
  beforeEach(() => {
    clients.clear();
    taskSequence = 0;
    vi.clearAllMocks();
    installMatchMedia();
  });

  it("switches all seven model parameter workspaces", async () => {
    const wrapper = mountApp();
    await flushPromises();

    for (const modelId of MODEL_IDS) {
      await wrapper.get(`[data-model-id="${modelId}"]`).trigger("click");
      expect(wrapper.get("[data-parameter-heading]").text()).toContain(
        getModelDefinition(modelId).label
      );
      expect(wrapper.get(".model-parameter-panel").attributes("data-model-id")).toBe(modelId);
    }
  });

  it("submits every model through its registered task base path", async () => {
    const wrapper = mountApp();
    await flushPromises();

    for (const modelId of MODEL_IDS) {
      await selectModel(wrapper, modelId);
      const panel = wrapper.getComponent(ModelParameterPanel);
      panel.vm.$emit("submit", structuredClone(toRaw(panel.props("modelValue"))));
      await flushPromises();

      expect(clients.get(getModelDefinition(modelId).taskBasePath)?.create).toHaveBeenCalledTimes(1);
    }
  });

  it("keeps the selected task while navigating between models", async () => {
    const wrapper = mountApp();
    await flushPromises();
    const panel = wrapper.getComponent(ModelParameterPanel);
    panel.vm.$emit("submit", structuredClone(toRaw(panel.props("modelValue"))));
    await flushPromises();

    expect(wrapper.get("[data-selected-task-id]").attributes("data-selected-task-id")).toBe("task-1");
    await selectModel(wrapper, "uav");
    expect(wrapper.get("[data-selected-task-id]").attributes("data-selected-task-id")).toBe("task-1");
    await selectModel(wrapper, "radar");
    expect(wrapper.get("[data-selected-task-id]").attributes("data-selected-task-id")).toBe("task-1");
  });

  it("restores a task draft without submitting it again", async () => {
    const wrapper = mountApp();
    await flushPromises();
    const panel = wrapper.getComponent(ModelParameterPanel);
    const original = structuredClone(toRaw(
      panel.props("modelValue") as BaseModelRequest & { radar: { lon: number } }
    ));
    original.radar.lon = 88.25;
    panel.vm.$emit("submit", original);
    await flushPromises();

    await wrapper.get('[data-action="open-history"]').trigger("click");
    await flushPromises();
    await wrapper.getComponent(TaskHistoryDrawer).get('[data-action="restore"]').trigger("click");
    await flushPromises();

    expect((wrapper.getComponent(ModelParameterPanel).props("modelValue") as typeof original).radar.lon).toBe(88.25);
    expect(clients.get(getModelDefinition("radar").taskBasePath)?.create).toHaveBeenCalledTimes(1);
  });

  it("does not restore stale radar layers after a newer task selection", async () => {
    const wrapper = mountApp();
    await flushPromises();
    const radarClient = clients.get(getModelDefinition("radar").taskBasePath)!;
    const uavClient = clients.get(getModelDefinition("uav").taskBasePath)!;
    const staleMetrics = deferred<Record<string, unknown>>();
    radarClient.create.mockImplementationOnce(async (request) => finishedTask(request, "radar-stale"));
    radarClient.metrics.mockReturnValueOnce(staleMetrics.promise);

    let panel = wrapper.getComponent(ModelParameterPanel);
    panel.vm.$emit("submit", structuredClone(toRaw(panel.props("modelValue"))));
    await nextTick();
    await selectModel(wrapper, "uav");
    uavClient.create.mockImplementationOnce(async (request) => finishedTask(request, "uav-current"));
    panel = wrapper.getComponent(ModelParameterPanel);
    panel.vm.$emit("submit", structuredClone(toRaw(panel.props("modelValue"))));
    await flushPromises();

    staleMetrics.resolve({});
    await flushPromises();

    expect(wrapper.get("[data-selected-task-id]").attributes("data-selected-task-id")).toBe("uav-current");
    expect(radarLayerAdapter.showTask).not.toHaveBeenCalled();
  });

  it("keeps radar profile and fusion workflows reachable", async () => {
    const wrapper = mountApp();
    await flushPromises();
    const radarClient = clients.get(getModelDefinition("radar").taskBasePath)!;
    radarClient.create
      .mockImplementationOnce(async (request) => finishedTask(request, "radar-finished-1"))
      .mockImplementationOnce(async (request) => finishedTask(request, "radar-finished-2"));

    let panel = wrapper.getComponent(ModelParameterPanel);
    panel.vm.$emit("submit", structuredClone(toRaw(panel.props("modelValue"))));
    await flushPromises();
    expect(wrapper.get('[data-action="profile-tool"]')).toBeTruthy();

    panel = wrapper.getComponent(ModelParameterPanel);
    panel.vm.$emit("submit", structuredClone(toRaw(panel.props("modelValue"))));
    await flushPromises();
    expect(wrapper.text()).toContain("融合分析");
  });

  it("keeps profile picking and spatial editing mutually exclusive", async () => {
    const wrapper = mountApp();
    await flushPromises();
    const radarClient = clients.get(getModelDefinition("radar").taskBasePath)!;
    radarClient.create.mockImplementationOnce(async (request) => finishedTask(request, "radar-profile"));
    const panel = wrapper.getComponent(ModelParameterPanel);
    panel.vm.$emit("submit", structuredClone(toRaw(panel.props("modelValue"))));
    await flushPromises();

    const profileButton = wrapper.get('[data-action="profile-tool"]');
    await profileButton.trigger("click");
    expect(profileButton.classes()).toContain("el-button--primary");

    panel.vm.$emit("activate-map-tool", "point");
    await nextTick();
    expect(profileButton.classes()).not.toContain("el-button--primary");
  });

  it("clears old radar layers before a replacement task finishes loading outputs", async () => {
    const wrapper = mountApp();
    await flushPromises();
    const radarClient = clients.get(getModelDefinition("radar").taskBasePath)!;
    radarClient.create
      .mockImplementationOnce(async (request) => finishedTask(request, "radar-old"))
      .mockImplementationOnce(async (request) => finishedTask(request, "radar-new"));
    const panel = wrapper.getComponent(ModelParameterPanel);
    panel.vm.$emit("submit", structuredClone(toRaw(panel.props("modelValue"))));
    await flushPromises();
    const clearCount = radarLayerAdapter.clear.mock.calls.length;
    const pendingMetrics = deferred<Record<string, unknown>>();
    radarClient.metrics.mockReturnValueOnce(pendingMetrics.promise);

    panel.vm.$emit("submit", structuredClone(toRaw(panel.props("modelValue"))));
    await flushPromises();

    expect(radarLayerAdapter.clear.mock.calls.length).toBeGreaterThan(clearCount);
    pendingMetrics.resolve({});
    await flushPromises();
  });
});

function mountApp() {
  return mount(App, {
    global: {
      stubs: {
        MapWorkspace: MapWorkspaceStub,
        FusionPanel: defineComponent({ name: "FusionPanel", template: "<div>融合分析</div>" })
      },
      directives: { loading: () => undefined }
    }
  });
}

async function selectModel(wrapper: ReturnType<typeof mountApp>, modelId: ModelId) {
  await wrapper.get(`[data-model-id="${modelId}"]`).trigger("click");
  await nextTick();
}

function makeClient() {
  return {
    list: vi.fn(async () => [] as TaskSummary[]),
    create: vi.fn(async (request: BaseModelRequest): Promise<TaskSummary> => ({
      task_id: `task-${++taskSequence}`,
      dem_id: request.dem_id,
      status: "pending",
      progress: 0,
      message: "queued",
      request: structuredClone(request),
      metrics: null,
      model: null,
      diagnostics: null,
      outputs: null,
      output_files: [],
      warnings: []
    })),
    get: vi.fn(),
    metrics: vi.fn(async () => ({})),
    outputs: vi.fn(async () => []),
    delete: vi.fn()
  };
}

function finishedTask(request: BaseModelRequest, taskId: string): TaskSummary {
  return {
    task_id: taskId,
    dem_id: request.dem_id,
    status: "finished",
    progress: 100,
    message: "finished",
    request: structuredClone(request),
    metrics: null,
    model: null,
    diagnostics: null,
    outputs: null,
    output_files: [],
    warnings: []
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

function installMatchMedia() {
  vi.spyOn(window, "matchMedia").mockReturnValue({
    matches: false,
    media: "(max-width: 800px)",
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(() => true)
  } as unknown as MediaQueryList);
}
