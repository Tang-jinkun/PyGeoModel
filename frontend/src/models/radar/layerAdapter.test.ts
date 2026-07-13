import { describe, expect, it } from "vitest";

import { radarDefinition } from "./definition";
import {
  resolveRadarLayerPlan,
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
