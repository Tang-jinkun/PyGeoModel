import { describe, expect, it } from "vitest";

import { buildWorkbenchTaskRows } from "./taskPresentation";
import type { BaseModelRequest, TaskSummary } from "../models/shared";

type GenericTask = TaskSummary<BaseModelRequest, Record<string, unknown>>;

describe("buildWorkbenchTaskRows", () => {
  it("uses the first available registered metric as the only completed-task summary", () => {
    const rows = buildWorkbenchTaskRows({
      radar: [task("radar-1", "finished", "2026-07-26T10:00:00Z", {
        visible_area_m2: 2_500_000,
        blocked_ratio: 0.31
      })]
    });

    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      key: "radar:radar-1",
      label: "Radar Coverage",
      primaryMetric: "Visible area 2.50 km2"
    });
  });

  it("keeps active and failed tasks metric-free and sorts newest first", () => {
    const rows = buildWorkbenchTaskRows({
      radar: [
        task("old", "running", "2026-07-01T00:00:00Z", { visible_area_m2: 1_000 }),
        task("new", "failed", "2026-07-02T00:00:00Z", { visible_area_m2: 2_000 })
      ]
    });

    expect(rows.map(({ task }) => task.task_id)).toEqual(["new", "old"]);
    expect(rows.every(({ primaryMetric }) => primaryMetric === null)).toBe(true);
  });
});

function task(
  taskId: string,
  status: GenericTask["status"],
  updatedAt: string,
  metrics: Record<string, unknown>
): GenericTask {
  return {
    task_id: taskId,
    status,
    progress: status === "finished" ? 100 : 50,
    message: "Task message",
    updated_at: updatedAt,
    output_files: [],
    warnings: [],
    metrics
  };
}
