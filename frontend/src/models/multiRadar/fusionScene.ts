import type { OutputFile, TaskSummary } from "../shared";

export function createFusionSceneTask(taskId: string, demId: string, url: string): TaskSummary {
  const file: OutputFile = {
    kind: "scene_glb",
    label: "Multi-radar fusion volume",
    url,
    download_url: url,
    filename: "fusion_scene.glb",
    media_type: "model/gltf-binary",
    exists: true
  };
  return {
    task_id: `${taskId}--fusion`,
    dem_id: demId,
    status: "finished",
    progress: 100,
    message: "finished",
    request: { dem_id: demId },
    output_files: [file],
    warnings: []
  };
}
