import { shallowMount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import type { MultiRadarStationInput } from "../../models/multiRadar/types";
import MultiRadarStationEditor from "./MultiRadarStationEditor.vue";

const stations: MultiRadarStationInput[] = [
  { radar_id: "R1", radar: { lon: 79, lat: 31.5, height_m: 20 }, coverage: { max_range_m: 1000 } },
  { radar_id: "R2", radar: { lon: 79.01, lat: 31.5, height_m: 20 }, coverage: { max_range_m: 1000 } }
];

describe("MultiRadarStationEditor", () => {
  it("accepts two stations in cooperative 3D mode", () => {
    const wrapper = shallowMount(MultiRadarStationEditor, {
      props: { stations, presentationMode: "cooperative_3d", showValidation: true }
    });

    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  });
});
