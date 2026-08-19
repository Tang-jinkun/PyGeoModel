import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import MetricGrid from "./MetricGrid.vue";

describe("MetricGrid", () => {
  it("formats artillery trajectory solution arrays as readable lines", () => {
    const wrapper = mount(MetricGrid, {
      props: {
        definitions: [{ key: "target_trajectory_solutions", label: "Target trajectories", format: "text" }],
        metrics: {
          target_trajectory_solutions: [{
            kind: "low",
            elevation_deg: 14.68,
            reachable: true,
            min_clearance_m: 12.3,
            time_of_flight_s: 5.2
          }]
        }
      }
    });

    expect(wrapper.text()).toContain("low · 14.68° · reachable · 5.2 s · clearance 12.3 m");
  });
});
