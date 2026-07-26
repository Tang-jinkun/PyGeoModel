import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import type { WorkbenchTaskRow } from "../../workbench/taskPresentation";
import WorkbenchTaskCenter from "./WorkbenchTaskCenter.vue";

describe("WorkbenchTaskCenter", () => {
  it("matches the task-history row structure and selects a completed task", async () => {
    const wrapper = mount(WorkbenchTaskCenter, { props: { rows: [finishedRadarRow()], activeTab: "history" } });

    expect(wrapper.text()).toContain("Visible area 2.50 km2");
    expect(wrapper.text()).not.toContain("Blocked ratio");
    expect(wrapper.get(".task-row .status-chip.ok").text()).toContain("Completed");
    expect(wrapper.find(".task-row .task-act").exists()).toBe(true);

    await wrapper.get('[data-task-key="radar:radar-1"]').trigger("click");
    expect(wrapper.emitted("select-task")?.[0]).toEqual(["radar", "radar-1"]);
  });
});

function finishedRadarRow(): WorkbenchTaskRow {
  return {
    key: "radar:radar-1", modelId: "radar", label: "Radar Coverage", statusLabel: "Completed", primaryMetric: "Visible area 2.50 km2", timestamp: 1,
    task: { task_id: "radar-1", status: "finished", progress: 100, message: "done", output_files: [], warnings: [], metrics: { visible_area_m2: 2_500_000, blocked_ratio: 0.31 } }
  };
}
