import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import { terrainInputSlot } from "../../models/inputSlots";
import ModelInputSlots from "./ModelInputSlots.vue";

describe("ModelInputSlots", () => {
  it("renders a terrain selector and emits an explicit selection", async () => {
    const wrapper = mount(ModelInputSlots, {
      props: {
        slots: [terrainInputSlot],
        selections: { terrain: [] },
        assets: [{ dem_id: "dem-1", filename: "terrain.tif" }],
        showValidation: false
      }
    });

    expect(wrapper.get("[data-input-slot='terrain']").text()).toContain("Terrain DEM");
    await wrapper.get("[data-input-slot='terrain'] select").setValue("dem-1");

    expect(wrapper.emitted("update:selections")?.[0]).toEqual([{ terrain: ["dem-1"] }]);
  });

  it("shows a required message only after validation is requested", () => {
    const wrapper = mount(ModelInputSlots, {
      props: { slots: [terrainInputSlot], selections: { terrain: [] }, assets: [], showValidation: true }
    });

    expect(wrapper.get("[data-input-slot='terrain']").text()).toContain("Required");
  });
});
