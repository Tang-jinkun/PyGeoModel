import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

import {
  useMapWorkspace,
  type SceneGlbOverlayState,
  type TaskOutputLayerState
} from "../../composables/useMapWorkspace";
import { MODEL_REGISTRY } from "../../models/registry";
import type { OutputFile, TaskSummary } from "../../models/shared";
import type { UavMetrics, UavRequest } from "../../models/uav/types";
import MetricGrid from "./MetricGrid.vue";
import OutputFileList from "./OutputFileList.vue";
import TaskHistoryDrawer from "./TaskHistoryDrawer.vue";
import TaskResultPanel from "./TaskResultPanel.vue";
import TaskStatusView from "./TaskStatusView.vue";

const finishedUavTask: TaskSummary<UavRequest, UavMetrics> = {
  task_id: "uav-finished-1",
  status: "finished",
  progress: 100,
  message: "分析完成",
  request: MODEL_REGISTRY.uav.createDefaultRequest(),
  metrics: null,
  output_files: [],
  warnings: []
};

const failedVisibleLayerState: TaskOutputLayerState[] = [
  {
    kind: "footprint_geojson",
    status: "ready",
    visible: true,
    opacity: 0.18,
    data: { type: "FeatureCollection", features: [] } as GeoJSON.FeatureCollection,
    error: null
  },
  {
    kind: "blocked_geojson",
    status: "idle",
    visible: false,
    opacity: 0.28,
    data: null,
    error: null
  },
  {
    kind: "visible_geojson",
    status: "error",
    visible: true,
    opacity: 0.35,
    data: null,
    error: "可见区加载失败"
  }
];

describe("TaskResultPanel", () => {
  it("isolates one failed GeoJSON layer without failing the task", async () => {
    const wrapper = mount(TaskResultPanel, {
      props: {
        modelId: "uav",
        task: finishedUavTask,
        layerStates: failedVisibleLayerState
      }
    });

    expect(wrapper.text()).toContain("任务已完成");
    expect(wrapper.findAll('[role="tab"]').map((tab) => tab.text())).toEqual(["任务", "指标", "图层", "文件"]);
    await wrapper.get('[data-tab="layers"]').trigger("click");
    expect(wrapper.text()).toContain("可见区加载失败");
    expect(wrapper.text()).toContain("传感器足迹");
  });

  it.each([
    ["pending", "任务等待中"],
    ["running", "任务运行中"],
    ["finished", "任务已完成"],
    ["failed", "任务失败"]
  ] as const)("renders the %s task status in readable Chinese", (status, label) => {
    const wrapper = mount(TaskStatusView, {
      props: { task: { ...finishedUavTask, status } }
    });

    expect(wrapper.text()).toContain(label);
  });

  it("formats registered metric values at the required thresholds", () => {
    const wrapper = mount(MetricGrid, {
      props: {
        definitions: [
          { key: "largeArea", label: "大面积", format: "area" },
          { key: "boundaryArea", label: "边界面积", format: "area" },
          { key: "longDistance", label: "长距离", format: "distance" },
          { key: "boundaryDistance", label: "边界距离", format: "distance" },
          { key: "duration", label: "耗时", format: "duration" },
          { key: "ratio", label: "比例", format: "percent" }
        ],
        metrics: {
          largeArea: 1_250_000,
          boundaryArea: 1_000_000,
          longDistance: 1_250,
          boundaryDistance: 1_000,
          duration: 3_661,
          ratio: 0.125
        }
      }
    });

    expect(wrapper.text()).toContain("1.25 km²");
    expect(wrapper.text()).toContain("1,000,000 m²");
    expect(wrapper.text()).toContain("1.25 km");
    expect(wrapper.text()).toContain("1,000 m");
    expect(wrapper.text()).toContain("1 h 1 m 1 s");
    expect(wrapper.text()).toContain("12.5%");
  });

  it("prefers download_url and falls back to url", () => {
    const wrapper = mount(OutputFileList, {
      props: {
        files: [
          outputFile("visible_geojson", "/view-visible", "/download-visible"),
          outputFile("blocked_geojson", "/view-blocked", "")
        ]
      }
    });

    const links = wrapper.findAll("a");
    expect(links[0].attributes("href")).toBe("/download-visible");
    expect(links[1].attributes("href")).toBe("/view-blocked");
    expect(wrapper.text()).toContain("下载visible_geojson");
  });

  it("renders downloads only for available output files", () => {
    const wrapper = mount(OutputFileList, {
      props: {
        files: [
          outputFile("available", "/available"),
          { ...outputFile("missing", "/missing"), exists: false }
        ]
      }
    });

    expect(wrapper.text()).toContain("available");
    expect(wrapper.text()).not.toContain("missing");
    expect(wrapper.findAll("a")).toHaveLength(1);
  });

  it("fetches result metadata in parallel and isolates each registered GeoJSON layer", async () => {
    const metricsPending = deferred<UavMetrics>();
    const outputsPending = deferred<OutputFile[]>();
    const metrics = vi.fn().mockReturnValue(metricsPending.promise);
    const outputs = vi.fn().mockReturnValue(outputsPending.promise);
    const fetchGeoJson = vi.fn().mockImplementation((url: string) => {
      if (url.includes("blocked")) return Promise.reject(new Error("invalid GeoJSON"));
      return Promise.resolve({ type: "FeatureCollection", features: [] });
    });
    const workspace = useMapWorkspace("point-or-route", undefined, {
      clientFactory: () => ({ metrics, outputs }),
      fetchGeoJson
    });

    const loading = workspace.loadTaskOutputs("uav", finishedUavTask);
    expect(metrics).toHaveBeenCalledWith(finishedUavTask.task_id);
    expect(outputs).toHaveBeenCalledWith(finishedUavTask.task_id);
    expect(fetchGeoJson).not.toHaveBeenCalled();

    metricsPending.resolve({
      theoretical_area_m2: 100,
      visible_area_m2: 60,
      blocked_area_m2: 40,
      blocked_ratio: 0.4,
      max_ground_distance_m: 10,
      coverage_point_count: 2,
      route_length_m: 20,
      average_visible_area_m2: 30,
      overlap_area_m2: 5
    });
    outputsPending.resolve([
      outputFile("footprint_geojson", "/footprint"),
      outputFile("blocked_geojson", "/blocked"),
      outputFile("visible_geojson", "/visible")
    ]);
    await loading;

    expect(fetchGeoJson).toHaveBeenCalledTimes(3);
    expect(workspace.layerStates.value.find(({ kind }) => kind === "footprint_geojson")?.status).toBe("ready");
    expect(workspace.layerStates.value.find(({ kind }) => kind === "blocked_geojson")).toMatchObject({
      status: "error",
      error: "地形遮挡区加载失败"
    });
    expect(workspace.layerStates.value.find(({ kind }) => kind === "visible_geojson")?.status).toBe("ready");
    expect(workspace.loadedTask.value?.status).toBe("finished");
  });

  it("ignores stale metrics, files, and layers from an earlier task", async () => {
    const oldMetrics = deferred<UavMetrics>();
    const oldOutputs = deferred<OutputFile[]>();
    const metrics = vi.fn().mockImplementation((taskId: string) => taskId === "old" ? oldMetrics.promise : Promise.resolve({ visible_area_m2: 22 }));
    const outputs = vi.fn().mockImplementation((taskId: string) => taskId === "old" ? oldOutputs.promise : Promise.resolve([
      outputFile("visible_geojson", "/new-visible")
    ]));
    const fetchGeoJson = vi.fn().mockImplementation((url: string) => Promise.resolve({
      type: "FeatureCollection",
      features: [{ type: "Feature", properties: { url }, geometry: null }]
    }));
    const workspace = useMapWorkspace("point-or-route", undefined, {
      clientFactory: () => ({ metrics, outputs }),
      fetchGeoJson
    });
    const oldTask = { ...finishedUavTask, task_id: "old" };
    const newTask = { ...finishedUavTask, task_id: "new" };

    const oldLoading = workspace.loadTaskOutputs("uav", oldTask);
    await workspace.loadTaskOutputs("uav", newTask);
    oldMetrics.resolve({ visible_area_m2: 999 } as UavMetrics);
    oldOutputs.resolve([outputFile("visible_geojson", "/old-visible")]);
    await oldLoading;

    expect(workspace.loadedTask.value?.task_id).toBe("new");
    expect(workspace.taskMetrics.value).toEqual({ visible_area_m2: 22 });
    expect(fetchGeoJson).not.toHaveBeenCalledWith("/old-visible");
    expect(workspace.outputFiles.value[0].url).toBe("/new-visible");
  });

  it("shows independent radar scene and platform GLBs in Layers", async () => {
    const sceneGlbFile = outputFile("scene_glb", "/view-scene", "/download-scene");
    sceneGlbFile.media_type = "model/gltf-binary";
    sceneGlbFile.filename = "result.glb";
    const platformGlbFile = outputFile(
      "radar_platform_glb",
      "/view-platform",
      "/download-platform"
    );
    platformGlbFile.label = "Radar Platform GLB";
    platformGlbFile.media_type = "model/gltf-binary";
    platformGlbFile.filename = "radar_platform.glb";
    const state: SceneGlbOverlayState = {
      taskId: finishedUavTask.task_id,
      modelId: "uav",
      demId: "dem-a",
      status: "idle",
      visible: false,
      progress: null,
      error: null
    };
    const platformState: SceneGlbOverlayState = {
      ...state,
      status: "visible",
      visible: true
    };
    const wrapper = mount(TaskResultPanel, {
      props: {
        modelId: "uav",
        task: { ...finishedUavTask, output_files: [sceneGlbFile, platformGlbFile] },
        sceneGlbState: state,
        radarPlatformGlbState: platformState
      }
    });

    expect(wrapper.find('[data-scene-glb-row]').exists()).toBe(false);
    await wrapper.get('[data-tab="layers"]').trigger("click");
    expect(wrapper.findAll('[data-scene-glb-row]')).toHaveLength(2);
    const toggles = wrapper.findAll('[data-scene-glb-toggle] input[role="switch"]');
    await toggles[0].trigger("click");
    await toggles[1].trigger("click");
    expect(wrapper.emitted("scene-glb-visibility")?.[0]).toEqual(["scene_glb", true]);
    expect(wrapper.emitted("scene-glb-visibility")?.[1]).toEqual(["radar_platform_glb", false]);
    await wrapper.get('[data-tab="files"]').trigger("click");
    expect(wrapper.find('[data-scene-glb-row]').exists()).toBe(false);
    expect(wrapper.get('a[href="/download-scene"]')).toBeTruthy();
    expect(wrapper.get('a[href="/download-platform"]')).toBeTruthy();
  });

  it("does not show a scene control without an existing scene_glb file", async () => {
    const wrapper = mount(TaskResultPanel, {
      props: {
        modelId: "uav",
        task: finishedUavTask,
        sceneGlbState: {
          taskId: finishedUavTask.task_id,
          modelId: "uav",
          demId: "dem-a",
          status: "idle",
          visible: false,
          progress: null,
          error: null
        }
      }
    });

    await wrapper.get('[data-tab="layers"]').trigger("click");
    expect(wrapper.find('[data-scene-glb-row]').exists()).toBe(false);
  });

  it("awaits async history restore and confirms destructive deletion explicitly", async () => {
    const restorePending = deferred<UavRequest | null>();
    const restoreRequest = vi.fn().mockReturnValue(restorePending.promise);
    const remove = vi.fn().mockResolvedValue(undefined);
    const confirmDelete = vi.fn().mockResolvedValue(true);
    const wrapper = mount(TaskHistoryDrawer, {
      props: {
        open: true,
        tasksByModel: { uav: [finishedUavTask] },
        taskManager: { restoreRequest, remove },
        confirmDelete
      }
    });

    expect(wrapper.text()).toContain("任务历史");
    expect(wrapper.text()).toContain("无人机侦察");
    expect(wrapper.text()).toContain("已完成");

    await wrapper.get('[data-action="restore"]').trigger("click");
    expect(wrapper.emitted("restore")).toBeUndefined();
    restorePending.resolve(finishedUavTask.request ?? null);
    await flushPromises();
    expect(wrapper.emitted("restore")?.[0]).toEqual(["uav", finishedUavTask.request]);

    await wrapper.get('[data-action="delete"]').trigger("click");
    await flushPromises();
    expect(confirmDelete).toHaveBeenCalledWith("删除后，后端任务记录和输出文件将被移除，且无法恢复。确定删除吗？");
    expect(remove).toHaveBeenCalledWith("uav", finishedUavTask.task_id);
  });
});

function outputFile(kind: string, url: string, downloadUrl = ""): OutputFile {
  return {
    kind,
    label: kind,
    url,
    download_url: downloadUrl,
    filename: `${kind}.geojson`,
    media_type: "application/geo+json",
    exists: true
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve;
  });
  return { promise, resolve };
}
