import type { TaskSummary } from "../shared";
import type { MultiRadarSceneAsset } from "./types";

export function createMultiRadarSceneTask(
  demId: string,
  asset: MultiRadarSceneAsset,
): TaskSummary {
  return {
    task_id: asset.task_id,
    dem_id: demId,
    status: "finished",
    result_state: "ready",
    progress: 100,
    message: "finished",
    request: { dem_id: demId },
    output_files: [{ ...asset.file, kind: asset.kind }],
    warnings: []
  };
}
