import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import RadarLayerControls from "./RadarLayerControls.vue";

describe("RadarLayerControls", () => {
  it("emits visibility, opacity, and height selection commands", async () => {
    const wrapper = mount(RadarLayerControls, {
      props: {
        layers: [
          { kind: "volume", label: "Radar volume", color: "#16a34a", visible: true, opacity: 0.6, available: true },
          { kind: "boundary", label: "Request boundary", color: "#94a3b8", visible: false, opacity: 0.45, available: true },
          { kind: "voxel", label: "Voxel cloud", color: "#06b6d4", visible: false, opacity: 0.8, available: true }
        ],
        heightOptions: [
          { heightM: 100, label: "100 m" },
          { heightM: 300, label: "300 m" }
        ],
        selectedHeightM: 100
      }
    });

    await wrapper.get('[data-layer-visible="voxel"]').setValue(true);
    await wrapper.get('[data-layer-visible="boundary"]').setValue(true);
    await wrapper.get('[data-layer-opacity="volume"]').setValue("0.35");
    await wrapper.get('[data-height-select]').setValue("300");

    expect(wrapper.emitted("update-layer")?.[0]).toEqual(["voxel", { visible: true }]);
    expect(wrapper.emitted("update-layer")?.[1]).toEqual(["boundary", { visible: true }]);
    expect(wrapper.emitted("update-layer")?.[2]).toEqual(["volume", { opacity: 0.35 }]);
    expect(wrapper.emitted("select-height")?.[0]).toEqual([300]);
  });
});
