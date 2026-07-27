import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import WorkbenchInspector from "./WorkbenchInspector.vue";

describe("WorkbenchInspector", () => {
  it("shows live metrics and downloadable outputs with workbench result controls", () => {
    const wrapper = mount(WorkbenchInspector, {
      props: {
        mode: "result",
        context: finishedContext(),
        metrics: { visible_area_m2: 2_500_000 },
        outputFiles: [outputFile()]
      }
    });

    expect(wrapper.find('[data-result-detail]').exists()).toBe(true);
    expect(wrapper.get("[data-result-metrics]").text()).toContain("Visible area");
    expect(wrapper.get("[data-result-metrics]").text()).toContain("2.50 km²");
    expect(wrapper.get("[data-result-files] a").attributes("href"))
      .toBe("/api/radar/coverage/task-1/outputs/visible_geojson");
    expect(wrapper.find('[data-tab="layers"]').exists()).toBe(false);
    expect(wrapper.find(".task-result-panel").exists()).toBe(false);
  });

  it("shows the result reason when artifacts are unavailable", () => {
    const context = finishedContext();
    context.task.result_state = "unavailable";
    context.task.result_reason_code = "ARTIFACT_MANIFEST_MISSING";
    const wrapper = mount(WorkbenchInspector, { props: { mode: "result", context } });

    expect(wrapper.get("[data-result-unavailable]").text()).toContain("ARTIFACT_MANIFEST_MISSING");
    expect(wrapper.find("[data-result-files]").exists()).toBe(false);
  });

  it("shows multi-radar metrics and every available download", () => {
    const wrapper = mount(WorkbenchInspector, {
      props: {
        mode: "result",
        context: multiRadarContext(),
        outputFiles: [
          outputFile(),
          {
            kind: "overlap_geojson",
            filename: "overlap.geojson",
            media_type: "application/geo+json",
            label: "Overlap GeoJSON",
            required: true,
            exists: true,
            download_path: "/api/radar/multi-coverage/multi-1/outputs/overlap_geojson"
          }
        ]
      }
    });

    expect(wrapper.find("[data-result-detail]").text()).toContain("多雷达协同");
    expect(wrapper.get("[data-result-metrics]").text()).toContain("Visible union area");
    expect(wrapper.get("[data-result-files]").text()).toContain("Overlap GeoJSON");
  });

  it("returns to parameters from a failed task", async () => {
    const wrapper = mount(WorkbenchInspector, { props: { mode: "result", context: { ...finishedContext(), task: { ...finishedContext().task, status: "failed" } } } });
    await wrapper.get('[aria-label="Back to model parameters"]').trigger("click");
    expect(wrapper.emitted("show-parameters")).toHaveLength(1);
  });
});

function finishedContext() {
  return { modelId: "radar" as const, task: { task_id: "task-1", status: "finished" as const, result_state: "ready" as "ready" | "unavailable", result_reason_code: null as string | null, progress: 100, message: "done", output_files: [], warnings: [], metrics: { visible_area_m2: 1 } } };
}

function outputFile() {
  return {
    kind: "visible_geojson",
    filename: "visible.geojson",
    media_type: "application/geo+json",
    label: "Visible Area GeoJSON",
    required: true,
    exists: true,
    download_path: "/api/radar/coverage/task-1/outputs/visible_geojson"
  };
}

function multiRadarContext() {
  return {
    kind: "multi-radar" as const,
    task: {
      task_id: "multi-1",
      dem_id: "dem-1",
      status: "finished" as const,
      result_state: "ready" as const,
      progress: 100,
      message: "done",
      metrics: {
        visible_union_area_m2: 2_500_000,
        overlap_area_m2: 500_000,
        blind_area_m2: 1_000_000,
        theoretical_union_area_m2: 3_500_000,
        successful_station_count: 2,
        failed_station_count: 0
      },
      output_files: [],
      stations: []
    }
  };
}
