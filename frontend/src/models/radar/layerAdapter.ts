import { clipProfileFromBounds, resolveBeamRenderRange } from "../../map/beamClipProfile";
import type { TaskSummary } from "../shared";
import type {
  BeamClipProfile,
  RadarDiagnostics,
  RadarMetrics,
  RadarModelMetadata,
  RadarRequest
} from "./types";

export type RadarTask = TaskSummary<
  RadarRequest,
  RadarMetrics,
  RadarModelMetadata,
  RadarDiagnostics
>;

export interface RadarLayerPlan {
  taskId: string;
  request: RadarRequest;
  clipProfile: BeamClipProfile | null;
  coverageContractVersion: number;
  outputUrls: Record<string, string>;
}

export function resolveRadarLayerPlan(
  task: RadarTask,
  demBounds: number[]
): RadarLayerPlan | null {
  if (task.status !== "finished" || !task.request) return null;

  const renderRangeM = resolveBeamRenderRange(
    task.request.coverage.max_range_m,
    task.model?.effective_max_range_m
  );
  const request = cloneRadarRequest(task.request, renderRangeM);
  const clipProfile = task.model?.beam_clip_profile
    ?? clipProfileFromBounds(demBounds, request.radar, renderRangeM);

  return {
    taskId: task.task_id,
    request,
    clipProfile,
    coverageContractVersion: task.model?.coverage_contract_version ?? 1,
    outputUrls: resolveOutputUrls(task)
  };
}

function cloneRadarRequest(source: RadarRequest, maxRangeM: number): RadarRequest {
  return {
    dem_id: source.dem_id,
    radar: { ...source.radar },
    target: { ...source.target },
    coverage: { ...source.coverage, max_range_m: maxRangeM },
    advanced: {
      ...source.advanced,
      height_layers_m: [...source.advanced.height_layers_m]
    },
    reserved_radar_params: source.reserved_radar_params
      ? { ...source.reserved_radar_params }
      : undefined
  };
}

function resolveOutputUrls(task: RadarTask): Record<string, string> {
  return Object.fromEntries(
    task.output_files
      .filter((file) => file.exists && (file.download_url || file.url))
      .map((file) => [file.kind, file.download_url || file.url])
  );
}
