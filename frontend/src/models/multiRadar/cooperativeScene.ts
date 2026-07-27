import type { OutputFile, TaskSummary } from "../shared";
import type { MultiRadarTask } from "./types";

export function cooperativeStationSceneTaskIds(task: Pick<MultiRadarTask, "stations">): string[] {
  return task.stations.flatMap((station) => (
    station.scene_status === "finished" && station.scene_task_id
      ? [station.scene_task_id]
      : []
  ));
}

export function createCooperativeIntersectionTask(
  taskId: string,
  demId: string,
  file: OutputFile,
): TaskSummary {
  return {
    task_id: `${taskId}--intersection`,
    dem_id: demId,
    status: "finished",
    result_state: "ready",
    progress: 100,
    message: "finished",
    request: { dem_id: demId },
    output_files: [{ ...file, kind: "scene_glb" }],
    warnings: []
  };
}
