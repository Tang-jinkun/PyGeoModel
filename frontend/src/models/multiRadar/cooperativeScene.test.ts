import { describe, expect, it } from "vitest";

import { createCooperativeIntersectionTask, cooperativeStationSceneTaskIds } from "./cooperativeScene";
import type { MultiRadarTask } from "./types";

describe("cooperative radar scene", () => {
  it("uses every finished station scene task and one common-detection artifact", () => {
    const task: Pick<MultiRadarTask, "stations"> & {
      task_id: string;
      dem_id: string;
      request: { dem_id: string; presentation_mode: "cooperative_3d"; radars: [] };
      outputs: { cooperative_intersection_glb: string };
    } = {
      task_id: "multi-1",
      dem_id: "dem-1",
      request: { dem_id: "dem-1", presentation_mode: "cooperative_3d", radars: [] },
      outputs: { cooperative_intersection_glb: "/outputs/multi-1/cooperative_intersection.glb" },
      stations: [
        { radar_id: "a", status: "finished", message: "", scene_task_id: "coverage-a", scene_status: "finished" },
        { radar_id: "b", status: "finished", message: "", scene_task_id: "coverage-b", scene_status: "finished" },
        { radar_id: "c", status: "finished", message: "", scene_task_id: "coverage-c", scene_status: "failed" }
      ]
    };

    expect(cooperativeStationSceneTaskIds(task)).toEqual(["coverage-a", "coverage-b"]);
    expect(createCooperativeIntersectionTask(task.task_id, task.dem_id, task.outputs.cooperative_intersection_glb))
      .toMatchObject({
        task_id: "multi-1--intersection",
        output_files: [expect.objectContaining({ filename: "cooperative_intersection.glb", kind: "scene_glb" })]
      });
  });
});
