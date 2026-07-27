import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import WorkbenchTopbar from "./WorkbenchTopbar.vue";

describe("WorkbenchTopbar", () => {
  it("emits the static topbar search query", async () => {
    const wrapper = mount(WorkbenchTopbar, {
      props: { demLabel: "terrain.tif", connected: true, search: "" }
    });

    await wrapper.get('input[aria-label="Global search"]').setValue("radar");

    expect(wrapper.emitted("update:search")?.[0]).toEqual(["radar"]);
    expect(wrapper.text()).toContain("terrain.tif");
  });
});
