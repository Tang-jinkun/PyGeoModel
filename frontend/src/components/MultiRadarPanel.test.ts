import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

const { createMultiRadarTask } = vi.hoisted(() => ({ createMultiRadarTask: vi.fn() }));
vi.mock("../api/multiRadar", () => ({
  createMultiRadarTask,
  getMultiRadarTask: vi.fn(),
  requestMultiRadarDetail: vi.fn()
}));

import MultiRadarPanel from "./MultiRadarPanel.vue";

describe("MultiRadarPanel", () => {
  it("submits a cooperative 3D batch mode", async () => {
    createMultiRadarTask.mockResolvedValueOnce({
      task_id: "multi-1", dem_id: "dem-1", status: "pending", stations: []
    });
    const wrapper = mount(MultiRadarPanel, {
      props: { demId: "dem-1", detailedStationIds: [] }
    });

    await wrapper.get('[data-presentation-mode="cooperative_3d"]').setValue(true);
    await wrapper.get("textarea").setValue(JSON.stringify([
      { radar_id: "a", radar: { lon: 79, lat: 31.5, height_m: 20 }, coverage: { max_range_m: 1000 } },
      { radar_id: "b", radar: { lon: 79.01, lat: 31.5, height_m: 20 }, coverage: { max_range_m: 1000 } },
      { radar_id: "c", radar: { lon: 79.02, lat: 31.5, height_m: 20 }, coverage: { max_range_m: 1000 } }
    ]));
    await wrapper.get("button").trigger("click");

    expect(createMultiRadarTask).toHaveBeenCalledWith(expect.objectContaining({
      dem_id: "dem-1", presentation_mode: "cooperative_3d"
    }));
  });
});
