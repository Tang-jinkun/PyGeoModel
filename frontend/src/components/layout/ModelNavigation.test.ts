import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import ModelNavigation from "./ModelNavigation.vue";

describe("ModelNavigation", () => {
  it("renders and selects all seven models", async () => {
    const wrapper = mount(ModelNavigation, { props: { modelValue: "radar" } });
    expect(wrapper.findAll("[data-model-id]")).toHaveLength(7);
    await wrapper.get('[data-model-id="mobility"]').trigger("click");
    expect(wrapper.emitted("update:modelValue")?.[0]).toEqual(["mobility"]);
  });
});
