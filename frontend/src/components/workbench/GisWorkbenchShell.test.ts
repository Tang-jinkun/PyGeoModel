import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import GisWorkbenchShell from "./GisWorkbenchShell.vue";

describe("GisWorkbenchShell", () => {
  it("renders no inspector region and lets the map use its column", async () => {
    const wrapper = mount(GisWorkbenchShell, {
      slots: {
        topbar: "top",
        dock: "dock",
        map: "map",
        tasks: "tasks",
        status: "status"
      }
    });

    expect(wrapper.text()).toContain("top");
    expect(wrapper.findAll("[data-workbench-region]")).toHaveLength(5);
    expect(wrapper.find("[data-workbench-region='inspector']").exists()).toBe(false);

    await wrapper.get('[aria-label="Collapse task center"]').trigger("click");

    expect(wrapper.attributes("data-tasks-collapsed")).toBe("true");
    expect(wrapper.get('[aria-label="Expand task center"]')).toBeTruthy();
  });
});
