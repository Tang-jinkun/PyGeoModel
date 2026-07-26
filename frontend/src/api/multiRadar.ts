import { requestJson } from "./http";
import type { CoverageTaskStatus } from "./radar";
import type {
  MultiRadarRequest,
  MultiRadarStationSummary,
  MultiRadarTargetEvaluation,
  MultiRadarTask
} from "../models/multiRadar/types";

export async function createMultiRadarTask(payload: MultiRadarRequest): Promise<MultiRadarTask> {
  return requestJson<MultiRadarTask>("/api/radar/multi-coverage", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function listMultiRadarTasks(): Promise<MultiRadarTask[]> {
  return requestJson<MultiRadarTask[]>("/api/radar/multi-coverage");
}

export function getMultiRadarTask(taskId: string): Promise<MultiRadarTask> {
  return requestJson<MultiRadarTask>(`/api/radar/multi-coverage/${taskId}`);
}

export function getMultiRadarStations(taskId: string): Promise<MultiRadarStationSummary[]> {
  return requestJson<MultiRadarStationSummary[]>(`/api/radar/multi-coverage/${taskId}/radars`);
}

export function requestMultiRadarDetail(taskId: string, radarId: string): Promise<CoverageTaskStatus> {
  return requestJson<CoverageTaskStatus>(`/api/radar/multi-coverage/${taskId}/radars/${radarId}/detail`, {
    method: "POST"
  });
}

export function evaluateMultiRadarTarget(
  taskId: string,
  target: { x: number; y: number; z: number; target_type?: string }
): Promise<MultiRadarTargetEvaluation> {
  return requestJson<MultiRadarTargetEvaluation>(`/api/radar/multi-coverage/${taskId}/evaluate-target`, {
    method: "POST",
    body: JSON.stringify(target)
  });
}
