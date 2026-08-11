import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import ModelParameterFields from "./ModelParameterFields.vue";

describe("ModelParameterFields", () => {
  it("updates a radar parameter and asks to pick a coordinate from the map", async () => {
    const wrapper = mount(ModelParameterFields, {
      props: { modelId: "radar", modelValue: radarRequest() }
    });

    await wrapper.get("[data-field='coverage.max_range_m'] input").setValue("150000");
    await wrapper.get("[data-field='radar'] button").trigger("click");

    expect(wrapper.emitted("update:modelValue")?.[0]?.[0]).toMatchObject({ coverage: { max_range_m: 150000 } });
    expect(wrapper.emitted("activate-map-tool")).toEqual([["point"]]);
  });

  it("asks for an artillery target coordinate", async () => {
    const wrapper = mount(ModelParameterFields, {
      props: { modelId: "artillery", modelValue: artilleryRequest() }
    });

    await wrapper.get("[data-field='target'] button").trigger("click");

    expect(wrapper.emitted("activate-map-tool")).toEqual([["target"]]);
  });
});

function radarRequest() {
  return {
    dem_id: "dem-1",
    radar: { lon: 79.8, lat: 31.4, height_m: 12 },
    target: { height_m: 100 },
    coverage: { max_range_m: 120000, scan_mode: "omni", azimuth_deg: 0, beam_width_deg: 360 },
    advanced: { use_curvature: true, curvature_coeff: 1.333, voxel_grid_size: 100, vertical_beam_width_deg: 6, visual_dome_mode: true }
  };
}

function artilleryRequest() {
  return {
    dem_id: "dem-1",
    battery: { lon: 79.8, lat: 31.4, height_m: 12, altitude_mode: "agl" },
    target: { lon: null, lat: null, target_height_m: 100 },
    weapon: { min_range_m: 1000, max_range_m: 15000, azimuth_deg: 0, traverse_deg: 360, muzzle_velocity_mps: 500, elevation_deg: 45 },
    munition: { munition_type: "he", lethal_radius_m: 50, effective_radius_m: 120 },
    analysis: { use_dem_elevation: true, use_terrain_masking: true, sample_resolution_m: null, trajectory_samples: 80, clearance_margin_m: 0, output_simplify_tolerance_m: null }
  };
}
