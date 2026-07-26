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
