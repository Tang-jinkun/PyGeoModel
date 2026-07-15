import { describe, expect, it, vi } from "vitest";

import type { AirCorridorMetrics, AirCorridorRequest } from "../models/airCorridor/types";
import type { PreparedSceneGlb } from "../map/sceneGlbAsset";
import { MODEL_REGISTRY } from "../models/registry";
import type { OutputFile, TaskSummary } from "../models/shared";
import type { UavMetrics, UavRequest } from "../models/uav/types";
import { useMapWorkspace, type SceneGlbAdapter } from "./useMapWorkspace";

const sceneRuntime = vi.hoisted(() => ({
  fetch: vi.fn(),
  parse: vi.fn(),
  dispose: vi.fn(),
  add: vi.fn(),
  remove: vi.fn(),
  removeAll: vi.fn(),
  focus: vi.fn(() => true)
}));

vi.mock("../map/sceneGlbAsset", async (importOriginal) => ({
  ...await importOriginal<typeof import("../map/sceneGlbAsset")>(),
  fetchSceneGlb: sceneRuntime.fetch,
  parseSceneGlb: sceneRuntime.parse,
  disposePreparedScene: sceneRuntime.dispose
}));

vi.mock("../map/sceneGlbLayer", async (importOriginal) => ({
  ...await importOriginal<typeof import("../map/sceneGlbLayer")>(),
  addSceneGlbLayer: sceneRuntime.add,
  removeSceneGlbLayer: sceneRuntime.remove,
  removeAllSceneGlbLayers: sceneRuntime.removeAll,
  focusSceneGlbLayer: sceneRuntime.focus
}));

const sceneFile: OutputFile = {
  kind: "scene_glb",
  label: "Air Corridor 3D Result GLB",
  url: "/outputs/air_corridor_task_demo/air_corridor_result.glb",
  download_url: "/api/air-corridor/planning/air_corridor_task_demo/outputs/scene_glb",
  filename: "air_corridor_result.glb",
  media_type: "model/gltf-binary",
  size_bytes: 1_980_764,
  exists: true
};

const radarPlatformFile: OutputFile = {
  kind: "radar_platform_glb",
  label: "Radar Platform GLB",
  url: "/outputs/air_corridor_task_demo/radar_platform.glb",
  download_url: "/api/radar/coverage/air_corridor_task_demo/outputs/radar_platform_glb",
  filename: "radar_platform.glb",
  media_type: "model/gltf-binary",
  size_bytes: 420_000,
  exists: true
};

const finishedAirTask = {
  task_id: "air_corridor_task_demo",
  dem_id: "dem-a",
  status: "finished",
  progress: 100,
  message: "finished",
  request: { ...MODEL_REGISTRY.airCorridor.createDefaultRequest(), dem_id: "dem-a" },
  metrics: null,
  output_files: [sceneFile],
  warnings: []
} satisfies TaskSummary<AirCorridorRequest, AirCorridorMetrics>;

describe("useMapWorkspace", () => {
  it("provides immutable point and waypoint commands with undo and clear", () => {
    const workspace = useMapWorkspace("point-or-route");
    const first: [number, number] = [79.8, 31.4];
    workspace.pickPoint(first);
    first[0] = 0;
    workspace.appendWaypoint([79.9, 31.5]);
    workspace.moveWaypoint(1, [80, 32]);

    expect(workspace.draft.value.points).toEqual([[79.8, 31.4], [80, 32]]);
    workspace.removeWaypoint(0);
    workspace.undo();
    expect(workspace.draft.value.points).toHaveLength(2);
    workspace.clear();
    expect(workspace.draft.value.points).toHaveLength(0);
  });

  it("focuses GeoJSON bounds through the supplied map", () => {
    const workspace = useMapWorkspace("point");
    const fitBounds = vi.fn();
    const focused = workspace.focusBounds({ fitBounds } as never, {
      type: "Point",
      coordinates: [79.8, 31.4]
    });

    expect(focused).toBe(true);
    expect(fitBounds).toHaveBeenCalledOnce();
  });

  it("loads a GeoJSON layer from download_url before url", async () => {
    const metrics = vi.fn().mockResolvedValue({});
    const output: OutputFile = {
      kind: "visible_geojson",
      label: "Visible coverage",
      url: "/view-visible",
      download_url: "/download-visible",
      filename: "visible.geojson",
      media_type: "application/geo+json",
      exists: true
    };
    const outputs = vi.fn().mockResolvedValue([output]);
    const fetchGeoJson = vi.fn().mockResolvedValue({ type: "FeatureCollection", features: [] });
    const workspace = useMapWorkspace("point-or-route", undefined, {
      clientFactory: () => ({ metrics, outputs }),
      fetchGeoJson
    });
    const task: TaskSummary<UavRequest, UavMetrics> = {
      task_id: "uav-download-url",
      status: "finished",
      progress: 100,
      message: "分析完成",
      request: MODEL_REGISTRY.uav.createDefaultRequest(),
      metrics: null,
      output_files: [],
      warnings: []
    };

    await workspace.loadTaskOutputs("uav", task);

    expect(fetchGeoJson).toHaveBeenCalledOnce();
    expect(fetchGeoJson).toHaveBeenCalledWith("/download-visible");
  });

  it("does not fetch scene_glb until manually enabled", async () => {
    const sceneGlb = sceneGlbAdapter();
    const workspace = useMapWorkspace("start-end-threats", undefined, {
      clientFactory: () => ({
        metrics: vi.fn().mockResolvedValue({}),
        outputs: vi.fn().mockResolvedValue([sceneFile])
      }),
      sceneGlb
    });

    await workspace.loadTaskOutputs("airCorridor", finishedAirTask);

    expect(sceneGlb.load).not.toHaveBeenCalled();
    expect(workspace.sceneGlbStateFor(finishedAirTask.task_id)?.status).toBe("idle");

    await workspace.setSceneGlbVisibility(
      {} as never,
      "dem-a",
      "airCorridor",
      finishedAirTask,
      true
    );

    expect(sceneGlb.load).toHaveBeenCalledWith(expect.objectContaining({
      taskId: finishedAirTask.task_id,
      modelId: "air_corridor",
      url: "/api/air-corridor/planning/air_corridor_task_demo/outputs/scene_glb"
    }));
    expect(workspace.sceneGlbStateFor(finishedAirTask.task_id)?.status).toBe("visible");
  });

  it("loads and removes scene and radar platform GLBs independently", async () => {
    const sceneGlb = sceneGlbAdapter();
    const task = {
      ...finishedAirTask,
      output_files: [sceneFile, radarPlatformFile]
    };
    const workspace = useMapWorkspace("start-end-threats", undefined, {
      clientFactory: () => ({
        metrics: vi.fn().mockResolvedValue({}),
        outputs: vi.fn().mockResolvedValue([sceneFile, radarPlatformFile])
      }),
      sceneGlb
    });
    const map = {} as never;

    await workspace.loadTaskOutputs("airCorridor", task);
    await workspace.setSceneGlbVisibility(
      map, "dem-a", "airCorridor", task, true, "scene_glb"
    );
    await workspace.setSceneGlbVisibility(
      map, "dem-a", "airCorridor", task, true, "radar_platform_glb"
    );

    expect(sceneGlb.load).toHaveBeenNthCalledWith(1, expect.objectContaining({
      taskId: task.task_id,
      assetId: task.task_id,
      url: sceneFile.download_url
    }));
    expect(sceneGlb.load).toHaveBeenNthCalledWith(2, expect.objectContaining({
      taskId: task.task_id,
      assetId: `${task.task_id}--radar_platform_glb`,
      url: radarPlatformFile.download_url
    }));
    expect(workspace.sceneGlbStateFor(task.task_id, "scene_glb")?.status).toBe("visible");
    expect(workspace.sceneGlbStateFor(task.task_id, "radar_platform_glb")?.status).toBe("visible");

    await workspace.setSceneGlbVisibility(
      map, "dem-a", "airCorridor", task, false, "radar_platform_glb"
    );
    expect(workspace.sceneGlbStateFor(task.task_id, "scene_glb")?.status).toBe("visible");
    expect(workspace.sceneGlbStateFor(task.task_id, "radar_platform_glb")?.status).toBe("idle");
    expect(sceneGlb.remove).toHaveBeenCalledWith(
      map,
      `${task.task_id}--radar_platform_glb`
    );
  });

  it("rejects a DEM mismatch before fetching", async () => {
    const sceneGlb = sceneGlbAdapter();
    const workspace = sceneWorkspace(sceneGlb);
    await workspace.loadTaskOutputs("airCorridor", finishedAirTask);

    await workspace.setSceneGlbVisibility(
      {} as never,
      "dem-b",
      "airCorridor",
      finishedAirTask,
      true
    );

    expect(sceneGlb.load).not.toHaveBeenCalled();
    expect(workspace.sceneGlbStateFor(finishedAirTask.task_id)?.error).toContain("DEM");
  });

  it("aborts loading and removes resources when toggled off", async () => {
    const pending = deferred<void>();
    const sceneGlb = sceneGlbAdapter();
    sceneGlb.load.mockReturnValueOnce(pending.promise);
    const workspace = sceneWorkspace(sceneGlb);
    const map = {} as never;
    await workspace.loadTaskOutputs("airCorridor", finishedAirTask);

    const loading = workspace.setSceneGlbVisibility(
      map,
      "dem-a",
      "airCorridor",
      finishedAirTask,
      true
    );
    await Promise.resolve();
    const signal = sceneGlb.load.mock.calls[0][0].signal;
    await workspace.setSceneGlbVisibility(
      map,
      "dem-a",
      "airCorridor",
      finishedAirTask,
      false
    );

    expect(signal.aborted).toBe(true);
    expect(sceneGlb.remove).toHaveBeenCalledWith(map, finishedAirTask.task_id);
    expect(workspace.sceneGlbStateFor(finishedAirTask.task_id)?.status).toBe("idle");
    pending.resolve();
    await loading;
    expect(workspace.sceneGlbStateFor(finishedAirTask.task_id)?.status).toBe("idle");
  });

  it("keeps multiple visible task states independent", async () => {
    const sceneGlb = sceneGlbAdapter();
    const secondFile = {
      ...sceneFile,
      url: "/outputs/air_corridor_task_second/air_corridor_result.glb",
      download_url: "/api/air-corridor/planning/air_corridor_task_second/outputs/scene_glb"
    };
    const secondTask = {
      ...finishedAirTask,
      task_id: "air_corridor_task_second",
      output_files: [secondFile]
    };
    const workspace = useMapWorkspace("start-end-threats", undefined, {
      clientFactory: () => ({
        metrics: vi.fn().mockResolvedValue({}),
        outputs: vi.fn(async (taskId: string) => (
          taskId === secondTask.task_id ? [secondFile] : [sceneFile]
        ))
      }),
      sceneGlb
    });
    const map = {} as never;

    await workspace.loadTaskOutputs("airCorridor", finishedAirTask);
    await workspace.setSceneGlbVisibility(map, "dem-a", "airCorridor", finishedAirTask, true);
    await workspace.loadTaskOutputs("airCorridor", secondTask);
    await workspace.setSceneGlbVisibility(map, "dem-a", "airCorridor", secondTask, true);

    expect(workspace.sceneGlbStateFor(finishedAirTask.task_id)?.status).toBe("visible");
    expect(workspace.sceneGlbStateFor(secondTask.task_id)?.status).toBe("visible");
    await workspace.setSceneGlbVisibility(map, "dem-a", "airCorridor", finishedAirTask, false);
    expect(workspace.sceneGlbStateFor(finishedAirTask.task_id)?.status).toBe("idle");
    expect(workspace.sceneGlbStateFor(secondTask.task_id)?.status).toBe("visible");
  });

  it("does not add a parsed asset after the load was turned off", async () => {
    const parsed = deferred<PreparedSceneGlb>();
    const asset = { disposed: false } as PreparedSceneGlb;
    sceneRuntime.fetch.mockReset().mockResolvedValue(new ArrayBuffer(8));
    sceneRuntime.parse.mockReset().mockReturnValue(parsed.promise);
    sceneRuntime.dispose.mockReset();
    sceneRuntime.add.mockReset();
    sceneRuntime.remove.mockReset();
    const workspace = useMapWorkspace("start-end-threats", undefined, {
      clientFactory: () => ({
        metrics: vi.fn().mockResolvedValue({}),
        outputs: vi.fn().mockResolvedValue([sceneFile])
      })
    });
    const map = {} as never;
    await workspace.loadTaskOutputs("airCorridor", finishedAirTask);

    const loading = workspace.setSceneGlbVisibility(
      map,
      "dem-a",
      "airCorridor",
      finishedAirTask,
      true
    );
    await Promise.resolve();
    await Promise.resolve();
    await workspace.setSceneGlbVisibility(
      map,
      "dem-a",
      "airCorridor",
      finishedAirTask,
      false
    );
    parsed.resolve(asset);
    await loading;

    expect(sceneRuntime.add).not.toHaveBeenCalled();
    expect(sceneRuntime.dispose).toHaveBeenCalledWith(asset);
    expect(workspace.sceneGlbStateFor(finishedAirTask.task_id)?.status).toBe("idle");
  });

  it("removes incompatible and all overlays without cross-task state leaks", async () => {
    const sceneGlb = sceneGlbAdapter();
    const workspace = sceneWorkspace(sceneGlb);
    const map = {} as never;
    await workspace.loadTaskOutputs("airCorridor", finishedAirTask);
    await workspace.setSceneGlbVisibility(map, "dem-a", "airCorridor", finishedAirTask, true);

    workspace.removeIncompatibleSceneGlbs(map, "dem-b");
    expect(sceneGlb.remove).toHaveBeenCalledWith(map, finishedAirTask.task_id);
    expect(workspace.sceneGlbStateFor(finishedAirTask.task_id)).toBeNull();

    await workspace.loadTaskOutputs("airCorridor", finishedAirTask);
    workspace.removeAllSceneGlbs(map);
    expect(sceneGlb.removeAll).toHaveBeenCalledWith(map);
    expect(workspace.sceneGlbStates.value).toEqual({});
  });

  it("removes one task overlay when its server task is deleted", async () => {
    const sceneGlb = sceneGlbAdapter();
    const workspace = sceneWorkspace(sceneGlb);
    const map = {} as never;
    await workspace.loadTaskOutputs("airCorridor", finishedAirTask);
    await workspace.setSceneGlbVisibility(map, "dem-a", "airCorridor", finishedAirTask, true);

    workspace.removeSceneGlb(map, finishedAirTask.task_id);

    expect(sceneGlb.remove).toHaveBeenCalledWith(map, finishedAirTask.task_id);
    expect(workspace.sceneGlbStateFor(finishedAirTask.task_id)).toBeNull();
  });

  it("returns a visible lost layer to idle and resets destroyed-map state locally", async () => {
    const sceneGlb = sceneGlbAdapter();
    let onLayerLost: (() => void) | undefined;
    sceneGlb.load.mockImplementation(async (request) => {
      onLayerLost = request.onLayerLost;
    });
    const workspace = sceneWorkspace(sceneGlb);
    const map = {} as never;
    await workspace.loadTaskOutputs("airCorridor", finishedAirTask);
    await workspace.setSceneGlbVisibility(map, "dem-a", "airCorridor", finishedAirTask, true);

    expect(workspace.focusSceneGlb(map, finishedAirTask.task_id)).toBe(true);
    onLayerLost?.();
    expect(workspace.sceneGlbStateFor(finishedAirTask.task_id)?.status).toBe("idle");
    workspace.resetSceneGlbStates();
    expect(workspace.sceneGlbStates.value).toEqual({});
    expect(sceneGlb.removeAll).not.toHaveBeenCalled();
  });
});

function sceneGlbAdapter() {
  return {
    load: vi.fn<SceneGlbAdapter["load"]>().mockResolvedValue(undefined),
    remove: vi.fn<SceneGlbAdapter["remove"]>(),
    removeAll: vi.fn<SceneGlbAdapter["removeAll"]>(),
    focus: vi.fn<SceneGlbAdapter["focus"]>(() => true)
  };
}

function sceneWorkspace(sceneGlb: ReturnType<typeof sceneGlbAdapter>) {
  return useMapWorkspace("start-end-threats", undefined, {
    clientFactory: () => ({
      metrics: vi.fn().mockResolvedValue({}),
      outputs: vi.fn().mockResolvedValue([sceneFile])
    }),
    sceneGlb
  });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}
