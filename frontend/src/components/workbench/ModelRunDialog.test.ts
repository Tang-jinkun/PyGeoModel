import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import { terrainInputSlot } from "../../models/inputSlots";
import ModelRunDialog from "./ModelRunDialog.vue";

describe("ModelRunDialog", () => {
  it("does not submit without the required terrain input", async () => {
    const wrapper = mount(ModelRunDialog, { props: dialogProps({ terrain: [] }) });

    await wrapper.get("[data-action='run-analysis']").trigger("click");

    expect(wrapper.emitted("submit")).toBeUndefined();
    expect(wrapper.get("[data-input-slot='terrain']").text()).toContain("Required");
  });

  it("emits a request and explicit input selections on submit", async () => {
    const wrapper = mount(ModelRunDialog, { props: dialogProps({ terrain: ["dem-1"] }) });

    await wrapper.get("[data-action='run-analysis']").trigger("click");

    expect(wrapper.emitted("submit")?.[0]?.[0]).toMatchObject({
      request: { dem_id: "dem-1" },
      inputs: { terrain: ["dem-1"] }
    });
  });
});

function dialogProps(inputs: { terrain: string[] }) {
  return {
    open: true,
    modelId: "radar" as const,
    request: {
      dem_id: inputs.terrain[0] ?? "",
      radar: { lon: 79.8, lat: 31.4, height_m: 12 },
      target: { height_m: 100 },
      coverage: { max_range_m: 120000, scan_mode: "omni", azimuth_deg: 0, beam_width_deg: 360 },
      advanced: { use_curvature: true, curvature_coeff: 1.333, voxel_grid_size: 100, vertical_beam_width_deg: 6, visual_dome_mode: true }
    },
    inputs,
    slots: [terrainInputSlot],
    assets: [{ dem_id: "dem-1", filename: "terrain.tif" }],
    submitting: false
  };
}
