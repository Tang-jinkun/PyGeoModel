import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import MultiRadarStationList from "./MultiRadarStationList.vue";

describe("MultiRadarStationList", () => {
  it("filters stations by name", async () => {
    const wrapper = mount(MultiRadarStationList, {
      props: {
        stations: [
          { radar_id: "north", name: "North Ridge", status: "finished", message: "" },
          { radar_id: "south", name: "South Basin", status: "finished", message: "" }
        ],
        detailedStationIds: []
      }
    });

    await wrapper.get('[data-station-search]').setValue("ridge");

    expect(wrapper.text()).toContain("North Ridge");
    expect(wrapper.text()).not.toContain("South Basin");
  });
});
