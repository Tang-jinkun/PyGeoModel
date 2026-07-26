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

  it("switches a radar dialog to the multi-radar station editor", async () => {
    const wrapper = mount(ModelRunDialog, { props: dialogProps({ terrain: ["dem-1"] }) });

    await wrapper.get('[data-radar-mode="multi"]').trigger("click");

    expect(wrapper.find('[data-multi-radar-editor]').exists()).toBe(true);
    expect(wrapper.find('[data-model-parameters]').exists()).toBe(false);
  });

  it("submits multi-radar data without the single-radar request", async () => {
    const wrapper = mount(ModelRunDialog, { props: dialogProps({ terrain: ["dem-1"] }) });

    await wrapper.get('[data-radar-mode="multi"]').trigger("click");
    await wrapper.get("[data-action='run-analysis']").trigger("click");

    const submission = wrapper.emitted("submit")?.[0]?.[0] as Record<string, unknown>;
    expect(submission).toMatchObject({
      inputs: { terrain: ["dem-1"] },
      multiRadar: { presentationMode: "aggregate", stations: [{ radar_id: "R1" }, { radar_id: "R2" }] }
    });
    expect(submission).not.toHaveProperty("request");
  });

  it("includes each station's detailed radar parameters in a multi-radar submission", async () => {
    const wrapper = mount(ModelRunDialog, { props: dialogProps({ terrain: ["dem-1"] }) });

    await wrapper.get('[data-radar-mode="multi"]').trigger("click");
    const stationParameters = wrapper.findAll('[data-station-parameters]');
    expect(stationParameters).toHaveLength(2);
    await stationParameters[0].get('[data-field="coverage.scan_mode"] select').setValue("sector");
    await wrapper.get("[data-action='run-analysis']").trigger("click");

    const submission = wrapper.emitted("submit")?.[0]?.[0] as {
      multiRadar: { stations: Array<{ coverage: { scan_mode?: string } }> };
    };
    expect(submission.multiRadar.stations[0].coverage.scan_mode).toBe("sector");
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
