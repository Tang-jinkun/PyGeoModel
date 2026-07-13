import { describe, expect, it, vi } from "vitest";

import { radarDefinition } from "./definition";
import {
  createRadarLayerAdapter,
  resolveRadarLayerPlan,
  type RadarLayerPlan,
  type RadarTask
} from "./layerAdapter";
import type { BeamClipProfile, RadarModelMetadata } from "./types";

function makeTask(overrides: Partial<RadarTask> = {}): RadarTask {
  const request = radarDefinition.createDefaultRequest();
  request.coverage.max_range_m = 10_000;
  return {
    task_id: "radar-1",
    dem_id: "dem-1",
    status: "finished",
    progress: 100,
    message: "finished",
    request,
    metrics: null,
    model: null,
    diagnostics: null,
    outputs: null,
    output_files: [],
    warnings: [],
    ...overrides
  };
}

function makeModel(overrides: Partial<RadarModelMetadata> = {}): RadarModelMetadata {
  return {
    coverage_contract_version: 2,
    target_epsg: 32644,
    radar_projected_xy: [0, 0],
    projected_dem_bounds: [-1000, -1000, 1000, 1000],
    projected_dem_resolution_m: [30, 30],
    dem_coverage_ratio: 0.8,
    max_range_m: 10_000,
    scan_mode: "omni",
    azimuth_deg: 0,
    beam_width_deg: 360,
    simplify_tolerance_m: 30,
    gdal_viewshed_command: [],
    voxel_grid_size: 128,
    voxel_vertical_levels: 16,
    voxel_max_height_m: 3000,
    min_elevation_deg: 0,
    max_elevation_deg: 32,
    vertical_beam_width_deg: 32,
    visual_dome_mode: true,
    height_layers_m: [],
    radar_equation_active: false,
    radar_equation_max_range_m: null,
    effective_max_range_m: 4000,
    beam_clip_profile: null,
    ...overrides
  };
}

function makeLayerTask(taskId = "radar-1"): RadarTask {
  return makeTask({
    task_id: taskId,
    output_files: [
      outputFile("voxel_manifest_json"),
      outputFile("voxel_points_bin"),
      outputFile("clipped_volume_manifest_json"),
      outputFile("clipped_volume_cells_bin"),
      outputFile("height_layers_manifest_json")
    ]
  });
}

function outputFile(kind: string) {
  return {
    kind,
    label: kind,
    url: `/view-${kind}`,
    download_url: `/download-${kind}`,
    filename: kind,
    media_type: "application/octet-stream",
    exists: true
  };
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

function runtimeDependencies() {
  return {
    renderVolume: vi.fn(),
    removeVolume: vi.fn(),
    loadVoxel: vi.fn(async (_plan: RadarLayerPlan) => "voxel"),
    renderVoxel: vi.fn(),
    removeVoxel: vi.fn(),
    loadClipped: vi.fn(async (_plan: RadarLayerPlan) => "clipped"),
    renderClipped: vi.fn(),
    removeClipped: vi.fn(),
    loadHeightLayers: vi.fn(async (_plan: RadarLayerPlan) => "height"),
    renderHeightLayers: vi.fn(),
    removeHeightLayers: vi.fn()
  };
}

describe("resolveRadarLayerPlan", () => {
  it("uses the effective range and exact beam clip profile without mutating the task request", () => {
    const profile: BeamClipProfile = { azimuth_step_deg: 2, radius_m: [3000, 2800] };
    const task = makeTask({ model: makeModel({ beam_clip_profile: profile }) });

    const plan = resolveRadarLayerPlan(task, [79.7, 31.4, 79.9, 31.6]);

    expect(plan?.request).not.toBe(task.request);
    expect(plan?.request.coverage.max_range_m).toBe(4000);
    expect(task.request?.coverage.max_range_m).toBe(10_000);
    expect(plan?.clipProfile).toBe(profile);
    expect(plan?.coverageContractVersion).toBe(2);
  });

  it("falls back to DEM bounds and legacy contract version", () => {
    const task = makeTask();

    const plan = resolveRadarLayerPlan(task, [79.7, 31.4, 79.9, 31.6]);

    expect(plan?.clipProfile).not.toBeNull();
    expect(plan?.clipProfile?.radius_m.length).toBe(180);
    expect(plan?.coverageContractVersion).toBe(1);
  });

  it("prefers existing download URLs and ignores missing output files", () => {
    const task = makeTask({
      output_files: [
        {
          kind: "voxel_points_bin",
          label: "Voxel points",
          url: "/view-voxel",
          download_url: "/download-voxel",
          filename: "voxel.bin",
          media_type: "application/octet-stream",
          exists: true
        },
        {
          kind: "height_layers_manifest_json",
          label: "Height layers",
          url: "/view-height",
          download_url: "",
          filename: "height.json",
          media_type: "application/json",
          exists: true
        },
        {
          kind: "clipped_volume_cells_bin",
          label: "Missing cells",
          url: "/missing-cells",
          download_url: "/download-missing",
          filename: "missing.bin",
          media_type: "application/octet-stream",
          exists: false
        }
      ]
    });

    const plan = resolveRadarLayerPlan(task, []);

    expect(plan?.outputUrls).toEqual({
      voxel_points_bin: "/download-voxel",
      height_layers_manifest_json: "/view-height"
    });
  });

  it("does not create a plan for unfinished tasks or tasks without a request", () => {
    expect(resolveRadarLayerPlan(makeTask({ status: "running" }), [])).toBeNull();
    expect(resolveRadarLayerPlan(makeTask({ request: null }), [])).toBeNull();
  });
});

describe("createRadarLayerAdapter", () => {
  it("loads eligible layers once and reuses cached data after hiding radar", async () => {
    const deps = runtimeDependencies();
    const adapter = createRadarLayerAdapter(deps);

    await adapter.showTask(makeLayerTask(), [79.7, 31.4, 79.9, 31.6]);

    expect(deps.renderVolume).toHaveBeenCalledTimes(1);
    expect(deps.renderVoxel).toHaveBeenCalledWith("voxel", expect.objectContaining({ taskId: "radar-1" }));
    expect(deps.renderClipped).toHaveBeenCalledTimes(1);
    expect(deps.renderHeightLayers).toHaveBeenCalledTimes(1);

    adapter.setRadarVisible(false);
    expect(deps.removeVolume).toHaveBeenCalled();
    expect(deps.removeVoxel).toHaveBeenCalled();
    expect(deps.removeClipped).toHaveBeenCalled();
    expect(deps.removeHeightLayers).toHaveBeenCalled();

    adapter.setRadarVisible(true);
    expect(deps.renderVolume).toHaveBeenCalledTimes(2);
    expect(deps.renderVoxel).toHaveBeenCalledTimes(2);
    expect(deps.loadVoxel).toHaveBeenCalledTimes(1);
    expect(deps.loadClipped).toHaveBeenCalledTimes(1);
    expect(deps.loadHeightLayers).toHaveBeenCalledTimes(1);
  });

  it("does not render stale data after changing tasks", async () => {
    const deps = runtimeDependencies();
    const oldVoxel = deferred<string>();
    deps.loadVoxel.mockImplementation((plan) => (
      plan.taskId === "radar-old" ? oldVoxel.promise : Promise.resolve("new-voxel")
    ));
    const adapter = createRadarLayerAdapter(deps);

    const oldLoad = adapter.showTask(makeLayerTask("radar-old"), []);
    await adapter.showTask(makeLayerTask("radar-new"), []);
    oldVoxel.resolve("old-voxel");
    await oldLoad;

    expect(adapter.activeTaskId).toBe("radar-new");
    expect(deps.renderVoxel).toHaveBeenCalledWith("new-voxel", expect.objectContaining({ taskId: "radar-new" }));
    expect(deps.renderVoxel).not.toHaveBeenCalledWith("old-voxel", expect.anything());
  });

  it("starts a fresh load when the same task is shown after clear", async () => {
    const deps = runtimeDependencies();
    const staleVoxel = deferred<string>();
    const freshVoxel = deferred<string>();
    deps.loadVoxel
      .mockReturnValueOnce(staleVoxel.promise)
      .mockReturnValueOnce(freshVoxel.promise);
    const adapter = createRadarLayerAdapter(deps);

    const staleLoad = adapter.showTask(makeLayerTask(), []);
    adapter.clear();
    const freshLoad = adapter.showTask(makeLayerTask(), []);

    expect(deps.loadVoxel).toHaveBeenCalledTimes(2);
    freshVoxel.resolve("fresh-voxel");
    staleVoxel.resolve("stale-voxel");
    await Promise.all([staleLoad, freshLoad]);

    expect(deps.renderVoxel).toHaveBeenCalledWith(
      "fresh-voxel",
      expect.objectContaining({ taskId: "radar-1" })
    );
    expect(deps.renderVoxel).not.toHaveBeenCalledWith("stale-voxel", expect.anything());
  });

  it("starts a fresh load when switching back before the old task load resolves", async () => {
    const deps = runtimeDependencies();
    const staleVoxel = deferred<string>();
    const freshVoxel = deferred<string>();
    deps.loadVoxel.mockImplementation((plan) => {
      if (plan.taskId !== "radar-a") return Promise.resolve("voxel-b");
      return deps.loadVoxel.mock.calls.filter(([calledPlan]) => calledPlan.taskId === "radar-a").length === 1
        ? staleVoxel.promise
        : freshVoxel.promise;
    });
    const adapter = createRadarLayerAdapter(deps);

    const staleLoad = adapter.showTask(makeLayerTask("radar-a"), []);
    await adapter.showTask(makeLayerTask("radar-b"), []);
    const freshLoad = adapter.showTask(makeLayerTask("radar-a"), []);

    expect(deps.loadVoxel).toHaveBeenCalledTimes(3);
    freshVoxel.resolve("fresh-voxel-a");
    staleVoxel.resolve("stale-voxel-a");
    await Promise.all([staleLoad, freshLoad]);

    expect(deps.renderVoxel).toHaveBeenCalledWith(
      "fresh-voxel-a",
      expect.objectContaining({ taskId: "radar-a" })
    );
    expect(deps.renderVoxel).not.toHaveBeenCalledWith("stale-voxel-a", expect.anything());
  });

  it("does not render duplicate layers when the active task is shown again", async () => {
    const deps = runtimeDependencies();
    const adapter = createRadarLayerAdapter(deps);
    const task = makeLayerTask();

    await adapter.showTask(task, []);
    await adapter.showTask(task, []);

    expect(deps.renderVolume).toHaveBeenCalledTimes(1);
    expect(deps.renderVoxel).toHaveBeenCalledTimes(1);
    expect(deps.renderClipped).toHaveBeenCalledTimes(1);
    expect(deps.renderHeightLayers).toHaveBeenCalledTimes(1);
  });

  it("isolates loader errors without blocking successful layers", async () => {
    const deps = runtimeDependencies();
    const voxelError = new Error("voxel failed");
    deps.loadVoxel.mockRejectedValue(voxelError);
    const adapter = createRadarLayerAdapter(deps);

    await adapter.showTask(makeLayerTask(), []);

    expect(adapter.errors.voxel).toBe(voxelError);
    expect(deps.renderVoxel).not.toHaveBeenCalled();
    expect(deps.renderClipped).toHaveBeenCalledTimes(1);
    expect(deps.renderHeightLayers).toHaveBeenCalledTimes(1);
  });

  it("invalidates pending writes on clear and blocks commands after dispose", async () => {
    const deps = runtimeDependencies();
    const height = deferred<string>();
    deps.loadHeightLayers.mockReturnValue(height.promise);
    const adapter = createRadarLayerAdapter(deps);

    const pending = adapter.showTask(makeLayerTask(), []);
    adapter.clear();
    height.resolve("late-height");
    await pending;
    expect(deps.renderHeightLayers).not.toHaveBeenCalled();
    expect(adapter.activeTaskId).toBeNull();

    adapter.dispose();
    await adapter.showTask(makeLayerTask("after-dispose"), []);
    expect(adapter.activeTaskId).toBeNull();
    expect(deps.loadVoxel).toHaveBeenCalledTimes(1);
  });
});
