import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import GisWorkbenchShell from "./GisWorkbenchShell.vue";
import source from "./GisWorkbenchShell.vue?raw";

describe("GisWorkbenchShell", () => {
  it("defines a consistent three-column workbench grid", () => {
    const gridTemplate = source.match(/grid-template-areas:\s*([\s\S]*?);/)?.[1] ?? "";

    expect(gridTemplate).toContain('"top top top"');
    expect(gridTemplate).toContain('"dock map inspector"');
  });

  it("renders the inspector region and task controls", async () => {
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
    expect(wrapper.get("[data-workbench-region='inspector']").text()).toBe("inspector");

    await wrapper.get('[aria-label="Collapse task center"]').trigger("click");

    expect(wrapper.attributes("data-tasks-collapsed")).toBe("true");
    expect(wrapper.get('[aria-label="Expand task center"]')).toBeTruthy();
  });
});
