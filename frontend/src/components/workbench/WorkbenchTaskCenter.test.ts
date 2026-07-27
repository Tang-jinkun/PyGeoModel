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

  it("shows an active multi-radar task in the running tab", () => {
    const wrapper = mount(WorkbenchTaskCenter, {
      props: {
        rows: [],
        activeTab: "running",
        multiRadarTasks: [multiRadarTask("running")]
      }
    });

    expect(wrapper.get("[data-multi-radar-task]").text()).toContain("多雷达协同");
    expect(wrapper.get("[data-multi-radar-task]").text()).toContain("48%");
  });

  it("keeps completed multi-radar tasks in history and emits their selection", async () => {
    const wrapper = mount(WorkbenchTaskCenter, {
      props: { rows: [], activeTab: "history", multiRadarTasks: [multiRadarTask("finished")] }
    });

    await wrapper.get("[data-multi-radar-task]").trigger("click");
    expect(wrapper.get("[data-multi-radar-task]").text()).toContain("已完成");
    expect(wrapper.emitted("select-multi-radar-task")?.[0]).toEqual(["multi-1"]);
  });
});

function multiRadarTask(status: "running" | "finished") {
  return {
    task_id: "multi-1",
    dem_id: "dem-1",
    status,
    progress: status === "running" ? 48 : 100,
    message: status === "running" ? "Computing 2 of 3 stations." : "finished",
    output_files: [],
    stations: []
  };
}

function finishedRadarRow(): WorkbenchTaskRow {
  return {
    key: "radar:radar-1", modelId: "radar", label: "Radar Coverage", statusLabel: "Completed", primaryMetric: "Visible area 2.50 km2", timestamp: 1,
    task: { task_id: "radar-1", status: "finished", result_state: "ready", progress: 100, message: "done", output_files: [], warnings: [], metrics: { visible_area_m2: 2_500_000, blocked_ratio: 0.31 } }
  };
}
