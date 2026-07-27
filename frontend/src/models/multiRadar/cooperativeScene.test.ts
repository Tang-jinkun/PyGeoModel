import { describe, expect, it } from "vitest";

import { createCooperativeIntersectionTask, cooperativeStationSceneTaskIds } from "./cooperativeScene";
import type { MultiRadarTask } from "./types";

describe("cooperative radar scene", () => {
  it("uses every finished station scene task and a live common-detection descriptor", () => {
    const task: Pick<MultiRadarTask, "stations"> & {
      task_id: string;
      dem_id: string;
      request: { dem_id: string; presentation_mode: "cooperative_3d"; radars: [] };
      output_files: [{ kind: string; label: string; filename: string; media_type: string; required: boolean; exists: boolean; download_path: string }];
    } = {
      task_id: "multi-1",
      dem_id: "dem-1",
      request: { dem_id: "dem-1", presentation_mode: "cooperative_3d", radars: [] },
      output_files: [{ kind: "cooperative_intersection_glb", label: "Intersection", filename: "cooperative_intersection.glb", media_type: "model/gltf-binary", required: false, exists: true, download_path: "/api/radar/multi-coverage/multi-1/outputs/cooperative_intersection_glb" }],
      stations: [
        { radar_id: "a", status: "finished", message: "", scene_task_id: "coverage-a", scene_status: "finished" },
        { radar_id: "b", status: "finished", message: "", scene_task_id: "coverage-b", scene_status: "finished" },
        { radar_id: "c", status: "finished", message: "", scene_task_id: "coverage-c", scene_status: "failed" }
      ]
    };

    expect(cooperativeStationSceneTaskIds(task)).toEqual(["coverage-a", "coverage-b"]);
    expect(createCooperativeIntersectionTask(task.task_id, task.dem_id, task.output_files[0]))
      .toMatchObject({
        task_id: "multi-1--intersection",
        output_files: [expect.objectContaining({ filename: "cooperative_intersection.glb", kind: "scene_glb" })]
      });
  });
});
