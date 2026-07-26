import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import GisWorkbenchShell from "./GisWorkbenchShell.vue";

describe("GisWorkbenchShell", () => {
  it("renders the six workbench regions and collapses the task center", async () => {
    const wrapper = mount(GisWorkbenchShell, {
      slots: {
        topbar: "top",
        dock: "dock",
        map: "map",
        inspector: "inspector",
        tasks: "tasks",
        status: "status"
      }
    });

    expect(wrapper.text()).toContain("top");
    expect(wrapper.findAll("[data-workbench-region]")).toHaveLength(6);

    await wrapper.get('[aria-label="Collapse task center"]').trigger("click");

    expect(wrapper.attributes("data-tasks-collapsed")).toBe("true");
    expect(wrapper.get('[aria-label="Expand task center"]')).toBeTruthy();
  });
});
