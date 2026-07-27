import type { OutputFile, TaskSummary } from "../shared";

export function createFusionSceneTask(taskId: string, demId: string, file: OutputFile): TaskSummary {
  return {
    task_id: `${taskId}--fusion`,
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
