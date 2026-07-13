import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import type { DemMetadata } from "../../api/dem";
import DemSelector from "./DemSelector.vue";

const demA: DemMetadata = {
  dem_id: "dem-a",
  filename: "terrain-a.tif",
  crs: "EPSG:4326",
  bounds: [0, 0, 1, 1],
  resolution: [10, 10],
  width: 100,
  height: 100,
  nodata: null,
  task_count: 3,
  active_task_count: 1
};

describe("DemSelector", () => {
  it("selects a DEM and displays its operational metadata", async () => {
    const wrapper = mount(DemSelector, {
      props: { dems: [demA], modelValue: null, loading: false, uploading: false }
    });

    await wrapper.get('[data-dem-id="dem-a"]').trigger("click");

    expect(wrapper.emitted("update:modelValue")?.[0]).toEqual(["dem-a"]);
    expect(wrapper.text()).toContain(demA.filename);
    expect(wrapper.text()).toContain(demA.crs);
    expect(wrapper.text()).toContain("10 x 10");
    expect(wrapper.text()).toContain("1 active task");
  });

  it("emits upload and refresh commands", async () => {
    const wrapper = mount(DemSelector, {
      props: { dems: [], modelValue: null, loading: false, uploading: false }
    });
    const file = new File(["elevation"], "terrain.tif", { type: "image/tiff" });
    const input = wrapper.get('input[type="file"]');
    Object.defineProperty(input.element, "files", { value: [file] });

    await input.trigger("change");
    await wrapper.get('[data-action="refresh-dems"]').trigger("click");

    expect(wrapper.emitted("upload")?.[0]).toEqual([file]);
    expect(wrapper.emitted("refresh")).toHaveLength(1);
  });
});
