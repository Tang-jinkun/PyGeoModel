import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import WorkbenchDataPane from "./WorkbenchDataPane.vue";

describe("WorkbenchDataPane", () => {
  it("selects a DEM with native workbench rows", async () => {
    const wrapper = mount(WorkbenchDataPane, { props: { dems: [{ dem_id: "dem-1", filename: "terrain.tif" }], modelValue: null, loading: false, uploading: false } });
    await wrapper.get('[data-dem-id="dem-1"]').trigger("click");
    expect(wrapper.find(".el-select").exists()).toBe(false);
    expect(wrapper.emitted("update:modelValue")?.[0]).toEqual(["dem-1"]);
  });

  it("emits every selected TIF as one DEM batch", async () => {
    const wrapper = mount(WorkbenchDataPane, { props: { dems: [], modelValue: null, loading: false, uploading: false } });
    const first = new File(["one"], "tile-a.tif", { type: "image/tiff" });
    const second = new File(["two"], "tile-b.tif", { type: "image/tiff" });
    const input = wrapper.get('input[type="file"]');
    Object.defineProperty(input.element, "files", { value: [first, second] });

    await input.trigger("change");

    expect(wrapper.emitted("upload")?.[0]).toEqual([[first, second]]);
  });
});
