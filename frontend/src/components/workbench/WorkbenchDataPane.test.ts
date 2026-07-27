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
});
