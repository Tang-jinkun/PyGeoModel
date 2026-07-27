import { describe, expect, it } from "vitest";

import { defaultCoverageRequest, getCoverageProfiles, normalizeCoverageTaskStatus } from "./radar";


describe("radar task normalization", () => {
  it("defaults ground radar scanning below and above the local horizon", () => {
    const request = defaultCoverageRequest();

    expect(request.advanced.min_elevation_deg).toBe(-8);
    expect(request.advanced.max_elevation_deg).toBe(90);
    expect(request.advanced.vertical_beam_width_deg).toBe(98);
  });

  it("normalizes DEM clip metrics and profile", () => {
    const task = normalizeCoverageTaskStatus({
      task_id: "task_a",
      status: "finished",
      progress: 100,
      request: {
        advanced: { output_simplify_tolerance_m: null }
      },
      metrics: {
        requested_theoretical_area_m2: 1200,
        theoretical_area_m2: 1000,
        unknown_area_m2: 200
      },
      model: {
        coverage_contract_version: 2,
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
    expect(task.request?.advanced.output_simplify_tolerance_m).toBeNull();
    expect(task.model?.coverage_contract_version).toBe(2);
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
    expect(task.model?.coverage_contract_version).toBe(1);
    expect(task.model?.beam_clip_profile).toBeNull();
    expect(task.model?.min_elevation_deg).toBe(0);
    expect(task.model?.max_elevation_deg).toBe(90);
  });

  it("normalizes live result state and canonical download descriptors", () => {
    const task = normalizeCoverageTaskStatus({
      task_id: "task_ready",
      status: "finished",
      result_state: "ready",
      result_reason_code: null,
      rerun_of: "task_old",
      output_files: [{
        kind: "visible_geojson",
        label: "Visible",
        filename: "visible.geojson",
        media_type: "application/geo+json",
        required: true,
        exists: true,
        size_bytes: 42,
        download_path: "/api/radar/coverage/task_ready/outputs/visible_geojson",
        url: null,
        download_url: null
      }]
    });

    expect(task).toMatchObject({
      result_state: "ready",
      result_reason_code: null,
      rerun_of: "task_old"
    });
    expect(task.output_files).toEqual([
      expect.objectContaining({
        required: true,
        download_path: "/api/radar/coverage/task_ready/outputs/visible_geojson"
      })
    ]);
  });

  it("does not synthesize output descriptors from legacy outputs", () => {
    const task = normalizeCoverageTaskStatus({
      task_id: "task_legacy_outputs",
      status: "finished",
      result_state: "unavailable",
      outputs: { visible_geojson: "/outputs/task_legacy_outputs/visible.geojson" }
    });

    expect(task.output_files).toEqual([]);
  });
});

describe("radar batch profile client", () => {
  it("posts targets and options to the batch profile endpoint", async () => {
    const originalFetch = globalThis.fetch;
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    globalThis.fetch = (async (url: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(url), init });
      return new Response(
        JSON.stringify({
          task_id: "task_a",
          requested_count: 2,
          succeeded_count: 2,
          failed_count: 0,
          results: [],
          errors: []
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }) as typeof fetch;

    try {
      const result = await getCoverageProfiles(
        "task_a",
        [
          { id: "T001", lon: 105.01, lat: 35 },
          { lon: 105.02, lat: 35.01 }
        ],
        { samples: 80, include_samples: false }
      );

      expect(result.requested_count).toBe(2);
      expect(calls).toHaveLength(1);
      expect(calls[0].url).toBe("/api/radar/coverage/task_a/profiles");
      expect(calls[0].init?.method).toBe("POST");
      expect(JSON.parse(String(calls[0].init?.body))).toEqual({
        targets: [
          { id: "T001", lon: 105.01, lat: 35 },
          { lon: 105.02, lat: 35.01 }
        ],
        samples: 80,
        include_samples: false
      });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
