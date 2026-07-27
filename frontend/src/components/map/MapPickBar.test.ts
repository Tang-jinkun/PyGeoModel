import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import MapPickBar from "./MapPickBar.vue";

describe("MapPickBar", () => {
  it("only renders route commands for route selection", async () => {
    const wrapper = mount(MapPickBar, { props: { target: "route" } });

    expect(wrapper.get("[data-action='undo-map-pick']")).toBeTruthy();
    expect(wrapper.get("[data-action='finish-map-pick']")).toBeTruthy();
    await wrapper.get("[data-action='cancel-map-pick']").trigger("click");

    expect(wrapper.emitted("cancel")).toHaveLength(1);
  });

  it("does not render route commands for a point", () => {
    const wrapper = mount(MapPickBar, { props: { target: "point" } });
    expect(wrapper.find("[data-action='undo-map-pick']").exists()).toBe(false);
    expect(wrapper.find("[data-action='finish-map-pick']").exists()).toBe(false);
  });
});
