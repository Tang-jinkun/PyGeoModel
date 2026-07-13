import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import CoordinateEditor from "./CoordinateEditor.vue";
import RouteEditor from "./RouteEditor.vue";
import ThreatEditor from "./ThreatEditor.vue";

describe("controlled spatial editors", () => {
  it("emits a cloned coordinate without changing its prop", async () => {
    const coordinate: [number, number] = [79.8, 31.4];
    const wrapper = mount(CoordinateEditor, { props: { modelValue: coordinate, editing: true } });

    await wrapper.get('[data-field="longitude"]').setValue("80");

    expect(coordinate).toEqual([79.8, 31.4]);
    expect(wrapper.emitted("update:modelValue")?.[0]).toEqual([[80, 31.4]]);
  });

  it("emits route move and remove actions without changing the waypoint prop", async () => {
    const points: [number, number][] = [[79.8, 31.4], [79.9, 31.5]];
    const wrapper = mount(RouteEditor, { props: { modelValue: points, editing: true } });

    await wrapper.get('[data-waypoint="0"] [data-field="latitude"]').setValue("32");
    await wrapper.get('[data-action="remove-waypoint-1"]').trigger("click");

    expect(points).toEqual([[79.8, 31.4], [79.9, 31.5]]);
    expect(wrapper.emitted("spatial-edit")?.[0]).toEqual([{ type: "move", index: 0, coordinate: [79.8, 32] }]);
    expect(wrapper.emitted("spatial-edit")?.[1]).toEqual([{ type: "remove", index: 1 }]);
  });

  it("emits threat updates and removals without owning threat data", async () => {
    const threats = [{ id: "t1", coordinate: [80, 32] as [number, number], properties: { name: "Alpha" } }];
    const wrapper = mount(ThreatEditor, { props: { modelValue: threats, editing: true } });

    await wrapper.get('[data-threat="t1"] [data-field="longitude"]').setValue("81");
    await wrapper.get('[data-action="remove-threat-t1"]').trigger("click");

    expect(threats[0].coordinate).toEqual([80, 32]);
    expect(wrapper.emitted("spatial-edit")?.[0]).toEqual([{
      type: "update-threat",
      id: "t1",
      coordinate: [81, 32]
    }]);
    expect(wrapper.emitted("spatial-edit")?.[1]).toEqual([{ type: "remove-threat", id: "t1" }]);
  });
});
