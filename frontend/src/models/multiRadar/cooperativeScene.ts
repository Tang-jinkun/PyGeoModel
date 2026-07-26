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
  url: string,
): TaskSummary {
  const file: OutputFile = {
    kind: "scene_glb",
    label: "Cooperative common detection",
    url,
    download_url: url,
    filename: "cooperative_intersection.glb",
    media_type: "model/gltf-binary",
    exists: true
  };
  return {
    task_id: `${taskId}--intersection`,
    dem_id: demId,
    status: "finished",
    progress: 100,
    message: "finished",
    request: { dem_id: demId },
    output_files: [file],
    warnings: []
  };
}
