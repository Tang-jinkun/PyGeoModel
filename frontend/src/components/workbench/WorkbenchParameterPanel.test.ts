import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import WorkbenchParameterPanel from "./WorkbenchParameterPanel.vue";

describe("WorkbenchParameterPanel", () => {
  it("renders the native workbench controls and emits an updated radar request", async () => {
    const wrapper = mount(WorkbenchParameterPanel, {
      props: { modelId: "radar", modelValue: radarRequest(), submitting: false }
    });

    expect(wrapper.find(".el-input").exists()).toBe(false);
    expect(wrapper.find("[data-field='advanced.use_curvature'] .switch i").exists()).toBe(true);
    expect((wrapper.get("[data-field='coverage.max_range_m'] input").element as HTMLInputElement).value).toBe("120000");

    await wrapper.get("[data-field='coverage.max_range_m'] input").setValue("150000");
    expect(wrapper.emitted("update:modelValue")?.[0]?.[0]).toMatchObject({ coverage: { max_range_m: 150000 } });
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
