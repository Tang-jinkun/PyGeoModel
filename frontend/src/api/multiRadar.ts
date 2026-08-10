import { requestJson } from "./http";
import { evaluateRadarTaskTarget, type CoverageTaskStatus } from "./radar";
import type {
  MultiRadarRequest,
  MultiRadarStationSummary,
  MultiRadarTargetEvaluation,
  MultiRadarTask
} from "../models/multiRadar/types";
import type { OutputFile } from "../models/shared";
import type { TaskExecutionSnapshot } from "./tasks";

export async function createMultiRadarTask(payload: MultiRadarRequest): Promise<MultiRadarTask> {
  return requestJson<MultiRadarTask>("/api/radar/tasks", {
    method: "POST",
    body: JSON.stringify({ task_type: "multi", ...payload })
  });
}

export function listMultiRadarTasks(): Promise<MultiRadarTask[]> {
  return requestJson<MultiRadarTask[]>("/api/radar/tasks?task_type=multi");
}

export function getMultiRadarTask(taskId: string): Promise<MultiRadarTask> {
  return requestJson<MultiRadarTask>(`/api/radar/tasks/${taskId}`);
}

export function rerunMultiRadarTask(taskId: string, idempotencyKey = crypto.randomUUID()): Promise<MultiRadarTask> {
  return requestJson<MultiRadarTask>(`/api/radar/tasks/${taskId}/rerun`, {
    method: "POST", headers: { "Idempotency-Key": idempotencyKey }
  });
}

export function cancelMultiRadarTask(taskId: string): Promise<TaskExecutionSnapshot> {
  return requestJson<TaskExecutionSnapshot>(`/api/radar/tasks/${taskId}/cancel`, { method: "POST" });
}

export function getMultiRadarOutputs(taskId: string): Promise<OutputFile[]> {
  return requestJson<OutputFile[]>(`/api/radar/tasks/${taskId}/outputs`);
}

export function findMultiRadarOutputPath(files: readonly OutputFile[], kind: string): string | null {
  const file = files.find((candidate) => candidate.kind === kind && candidate.exists && candidate.download_path);
  return file?.download_path ?? null;
}

export function getMultiRadarStations(taskId: string): Promise<MultiRadarStationSummary[]> {
  return requestJson<MultiRadarStationSummary[]>(`/api/radar/tasks/${taskId}/radars`);
}

export function requestMultiRadarDetail(taskId: string, radarId: string): Promise<CoverageTaskStatus> {
  return requestJson<CoverageTaskStatus>(`/api/radar/tasks/${taskId}/radars/${radarId}/detail`, {
    method: "POST"
  });
}

export function evaluateMultiRadarTarget(
  taskId: string,
  target: { x: number; y: number; z: number; target_type?: string }
): Promise<MultiRadarTargetEvaluation> {
  return evaluateRadarTaskTarget(taskId, target).then(({ task_id, detected, contributors }) => ({
    task_id,
    detected,
    contributors
  }));
}
