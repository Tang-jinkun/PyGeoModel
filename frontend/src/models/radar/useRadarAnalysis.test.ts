import { afterEach, describe, expect, it, vi } from "vitest";

import type { CoverageProfileResult, FusionResult } from "../../api/radar";
import type { TaskSummary } from "../shared";
import type {
  RadarDiagnostics,
  RadarMetrics,
  RadarModelMetadata,
  RadarRequest
} from "./types";
import { useRadarAnalysis, type RadarAnalysisTask } from "./useRadarAnalysis";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

function createTask(
  overrides: Partial<RadarAnalysisTask> = {}
): RadarAnalysisTask {
  const request: RadarRequest = {
    dem_id: "dem-1",
    radar: { lon: 120.123456789, lat: 30.987654321, height_m: 18 },
    target: { height_m: 4 },
    coverage: {
      max_range_m: 5000,
      scan_mode: "omni",
      azimuth_deg: 90,
      beam_width_deg: 360
    },
    advanced: {
      use_curvature: true,
      curvature_coeff: 0.75,
      output_simplify_tolerance_m: 10,
      voxel_grid_size: 32,
      voxel_vertical_levels: 8,
      voxel_max_height_m: 300,
      min_elevation_deg: 0,
      max_elevation_deg: 30,
      vertical_beam_width_deg: 30,
      visual_dome_mode: true,
      height_layers_m: []
    },
    reserved_radar_params: {}
  };

  const task: TaskSummary<RadarRequest, RadarMetrics, RadarModelMetadata, RadarDiagnostics> = {
    task_id: "radar-1",
    dem_id: "dem-1",
    status: "finished",
    progress: 100,
    message: "",
    request,
    metrics: null,
    outputs: null,
    model: {
      coverage_contract_version: 1,
      target_epsg: 4326,
      radar_projected_xy: [0, 0],
      projected_dem_bounds: [0, 0, 1, 1],
      projected_dem_resolution_m: [1, 1],
      dem_coverage_ratio: 1,
      max_range_m: 5000,
      scan_mode: "omni",
      azimuth_deg: 90,
      beam_width_deg: 360,
      simplify_tolerance_m: 10,
      gdal_viewshed_command: [],
      voxel_grid_size: 32,
      voxel_vertical_levels: 8,
      voxel_max_height_m: 300,
      min_elevation_deg: 0,
      max_elevation_deg: 30,
      vertical_beam_width_deg: 30,
      visual_dome_mode: true,
      height_layers_m: [],
      radar_equation_active: false,
      radar_equation_max_range_m: null,
      effective_max_range_m: 5000,
      beam_clip_profile: null
    },
    diagnostics: null,
    output_files: [],
    warnings: []
  };

  return { ...task, ...overrides };
}

function createProfileResult(overrides: Partial<CoverageProfileResult> = {}): CoverageProfileResult {
  return {
    task_id: "radar-1",
    target_lon: 120.000000123456,
    target_lat: 31.000000654321,
    distance_m: 1234,
    azimuth_deg: 45,
    elevation_deg: 2,
    radar_ground_m: 10,
    target_ground_m: 12,
    radar_altitude_m: 28,
    target_altitude_m: 16,
    blocked: false,
    obstruction_distance_m: null,
    obstruction_lon: null,
    obstruction_lat: null,
    obstruction_clearance_m: null,
    min_required_target_height_m: 4,
    required_height_delta_m: 0,
    reason: "clear",
    samples: [],
    ...overrides
  };
}

function createFusionResult(overrides: Partial<FusionResult> = {}): FusionResult {
  return {
    task_ids: ["radar-1", "radar-2"],
    metrics: {
      task_count: 2,
      union_visible_area_m2: 10,
      overlap_visible_area_m2: 5,
      union_theoretical_area_m2: 12,
      blind_area_m2: 2,
      overlap_ratio: 0.5,
      blind_ratio: 0.2
    },
    visible_union_geojson: { type: "FeatureCollection", features: [] },
    overlap_geojson: { type: "FeatureCollection", features: [] },
    blind_geojson: { type: "FeatureCollection", features: [] },
    warnings: [],
    ...overrides
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useRadarAnalysis", () => {
  it("runs profile for one finished task with exact selected target coordinates and target fields", async () => {
    const result = createProfileResult({
      target_lon: 120.000000123456,
      target_lat: 31.000000654321
    });
    const getProfile = vi.fn().mockResolvedValue(result);
    const analysis = useRadarAnalysis({ getProfile, createFusion: vi.fn() });
    const task = createTask();

    const promise = analysis.runProfile(task, {
      lon: 120.000000123456,
      lat: 31.000000654321
    });

    expect(analysis.profileLoading.value).toBe(true);
    await expect(promise).resolves.toBe(result);
    expect(getProfile).toHaveBeenCalledWith("radar-1", 120.000000123456, 31.000000654321);
    expect(analysis.profile.value).toEqual({
      task,
      target: {
        lon: 120.000000123456,
        lat: 31.000000654321,
        height_m: 4
      },
      result
    });
    expect(analysis.profileLoading.value).toBe(false);
    expect(analysis.profileError.value).toBeNull();
    analysis.dispose();
  });

  it("rejects profile for a non-finished task before calling the API", async () => {
    const errorTask = createTask({ status: "running", progress: 10 });
    const getProfile = vi.fn();
    const analysis = useRadarAnalysis({ getProfile, createFusion: vi.fn() });

    await expect(
      analysis.runProfile(errorTask, { lon: 120.1, lat: 31.2 })
    ).rejects.toThrow("Profile analysis requires a finished radar task.");

    expect(getProfile).not.toHaveBeenCalled();
    expect(analysis.profile.value).toBeNull();
    expect(analysis.profileLoading.value).toBe(false);
    expect(analysis.profileError.value).toBeInstanceOf(Error);
    analysis.dispose();
  });

  it("keeps only the newest profile request result", async () => {
    const first = deferred<CoverageProfileResult>();
    const second = deferred<CoverageProfileResult>();
    const getProfile = vi.fn()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const analysis = useRadarAnalysis({ getProfile, createFusion: vi.fn() });
    const firstTask = createTask({ task_id: "radar-1" });
    const secondTask = createTask({ task_id: "radar-2" });

    const firstRun = analysis.runProfile(firstTask, { lon: 120.1, lat: 31.1 });
    const secondRun = analysis.runProfile(secondTask, { lon: 120.2, lat: 31.2 });
    second.resolve(createProfileResult({ task_id: "radar-2", target_lon: 120.2, target_lat: 31.2 }));
    await secondRun;
    first.resolve(createProfileResult({ task_id: "radar-1", target_lon: 120.1, target_lat: 31.1 }));
    await firstRun;

    expect(analysis.profile.value?.task.task_id).toBe("radar-2");
    expect(analysis.profile.value?.result.task_id).toBe("radar-2");
    analysis.dispose();
  });

  it("preserves real profile API errors and clear blocks stale writes", async () => {
    const pending = deferred<CoverageProfileResult>();
    const realError = new Error("profile offline");
    const getProfile = vi.fn()
      .mockReturnValueOnce(Promise.reject(realError))
      .mockReturnValueOnce(pending.promise);
    const analysis = useRadarAnalysis({ getProfile, createFusion: vi.fn() });
    const task = createTask();

    await expect(analysis.runProfile(task, { lon: 120.1, lat: 31.2 })).rejects.toBe(realError);
    expect(analysis.profileError.value).toBe(realError);

    const stale = analysis.runProfile(task, { lon: 120.3, lat: 31.4 });
    analysis.clearProfile();
    pending.resolve(createProfileResult({ target_lon: 120.3, target_lat: 31.4 }));
    await stale;

    expect(analysis.profile.value).toBeNull();
    expect(analysis.profileLoading.value).toBe(false);
    expect(analysis.profileError.value).toBeNull();
    analysis.dispose();
  });

  it("runs fusion only for at least two distinct finished tasks", async () => {
    const createFusion = vi.fn().mockResolvedValue(createFusionResult());
    const analysis = useRadarAnalysis({ getProfile: vi.fn(), createFusion });
    const task1 = createTask({ task_id: "radar-1" });
    const duplicateTask1 = createTask({ task_id: "radar-1" });
    const task2 = createTask({ task_id: "radar-2" });

    await expect(analysis.runFusion([task1, duplicateTask1])).rejects.toThrow(
      "Fusion analysis requires at least two distinct finished radar tasks."
    );

    const result = await analysis.runFusion([task1, duplicateTask1, task2]);

    expect(createFusion).toHaveBeenCalledWith(["radar-1", "radar-2"]);
    expect(result.task_ids).toEqual(["radar-1", "radar-2"]);
    expect(analysis.fusion.value?.tasks.map(({ task_id }) => task_id)).toEqual(["radar-1", "radar-2"]);
    expect(analysis.fusionLoading.value).toBe(false);
    expect(analysis.fusionError.value).toBeNull();
    analysis.dispose();
  });

  it("rejects fusion for unfinished tasks or mixed coverage contract versions before the API call", async () => {
    const createFusion = vi.fn();
    const analysis = useRadarAnalysis({ getProfile: vi.fn(), createFusion });
    const finishedV1 = createTask({ task_id: "radar-1" });
    const unfinished = createTask({ task_id: "radar-2", status: "running", progress: 20 });
    const finishedV2 = createTask({
      task_id: "radar-3",
      model: { ...createTask().model!, coverage_contract_version: 2 }
    });

    await expect(analysis.runFusion([finishedV1, unfinished])).rejects.toThrow(
      "Fusion analysis requires finished radar tasks only."
    );
    await expect(analysis.runFusion([finishedV1, finishedV2])).rejects.toThrow(
      "Fusion analysis requires matching coverage contract versions."
    );

    expect(createFusion).not.toHaveBeenCalled();
    expect(analysis.fusion.value).toBeNull();
    expect(analysis.fusionLoading.value).toBe(false);
    expect(analysis.fusionError.value).toBeInstanceOf(Error);
    analysis.dispose();
  });

  it("preserves real fusion API errors and dispose blocks stale writes without cancelling profile tokens", async () => {
    const profilePending = deferred<CoverageProfileResult>();
    const fusionPending = deferred<FusionResult>();
    const realError = new Error("fusion offline");
    const getProfile = vi.fn().mockReturnValue(profilePending.promise);
    const createFusion = vi.fn()
      .mockReturnValueOnce(Promise.reject(realError))
      .mockReturnValueOnce(fusionPending.promise);
    const analysis = useRadarAnalysis({ getProfile, createFusion });
    const task1 = createTask({ task_id: "radar-1" });
    const task2 = createTask({ task_id: "radar-2" });

    await expect(analysis.runFusion([task1, task2])).rejects.toBe(realError);
    expect(analysis.fusionError.value).toBe(realError);

    const profileRun = analysis.runProfile(task1, { lon: 120.5, lat: 31.5 });
    const fusionRun = analysis.runFusion([task1, task2]);
    analysis.clearProfile();
    expect(analysis.fusionLoading.value).toBe(true);
    analysis.dispose();

    profilePending.resolve(createProfileResult({ target_lon: 120.5, target_lat: 31.5 }));
    fusionPending.resolve(createFusionResult());
    await Promise.all([profileRun, fusionRun]);

    expect(analysis.profile.value).toBeNull();
    expect(analysis.fusion.value).toBeNull();
    expect(analysis.profileLoading.value).toBe(false);
    expect(analysis.fusionLoading.value).toBe(false);
  });
});
