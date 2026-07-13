import { describe, expect, it } from "vitest";

import { normalizeCoverageTaskStatus } from "./radar";


describe("radar task normalization", () => {
  it("normalizes DEM clip metrics and profile", () => {
    const task = normalizeCoverageTaskStatus({
      task_id: "task_a",
      status: "finished",
      progress: 100,
      metrics: {
        requested_theoretical_area_m2: 1200,
        theoretical_area_m2: 1000,
        unknown_area_m2: 200
      },
      model: {
        target_epsg: 32648,
        radar_projected_xy: [0, 0],
        projected_dem_bounds: [0, 0, 10, 10],
        projected_dem_resolution_m: [10, 10],
        max_range_m: 1000,
        scan_mode: "omni",
        azimuth_deg: 0,
        beam_width_deg: 360,
        simplify_tolerance_m: 10,
        beam_clip_profile: { azimuth_step_deg: 2, radius_m: [1000, 900] }
      }
    });

    expect(task.metrics?.requested_theoretical_area_m2).toBe(1200);
    expect(task.metrics?.unknown_area_m2).toBe(200);
    expect(task.model?.beam_clip_profile?.radius_m).toEqual([1000, 900]);
  });

  it("defaults new fields for legacy tasks", () => {
    const task = normalizeCoverageTaskStatus({
      task_id: "task_old",
      status: "finished",
      progress: 100,
      metrics: { theoretical_area_m2: 100 },
      model: {
        target_epsg: 32648,
        radar_projected_xy: [0, 0],
        projected_dem_bounds: [0, 0, 10, 10],
        projected_dem_resolution_m: [10, 10],
        max_range_m: 1000,
        scan_mode: "omni",
        azimuth_deg: 0,
        beam_width_deg: 360,
        simplify_tolerance_m: 10
      }
    });

    expect(task.metrics?.requested_theoretical_area_m2).toBe(100);
    expect(task.metrics?.unknown_area_m2).toBe(0);
    expect(task.model?.beam_clip_profile).toBeNull();
  });
});
