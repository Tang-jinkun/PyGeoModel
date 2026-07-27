import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import WorkbenchInspector from "./WorkbenchInspector.vue";

describe("WorkbenchInspector", () => {
  it("shows metrics and files with native result detail controls", () => {
    const wrapper = mount(WorkbenchInspector, { props: { mode: "result", context: finishedContext() } });
    expect(wrapper.find('[data-result-detail]').exists()).toBe(true);
    expect(wrapper.find('[data-tab="layers"]').exists()).toBe(false);
    expect(wrapper.find(".task-result-panel").exists()).toBe(false);
  });

  it("returns to parameters from a failed task", async () => {
    const wrapper = mount(WorkbenchInspector, { props: { mode: "result", context: { ...finishedContext(), task: { ...finishedContext().task, status: "failed" } } } });
    await wrapper.get('[aria-label="Back to model parameters"]').trigger("click");
    expect(wrapper.emitted("show-parameters")).toHaveLength(1);
  });
});

function finishedContext() {
  return { modelId: "radar" as const, task: { task_id: "task-1", status: "finished" as const, result_state: "ready" as const, progress: 100, message: "done", output_files: [], warnings: [], metrics: { visible_area_m2: 2_500_000 } } };
}
