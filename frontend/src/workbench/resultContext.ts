import { getModelDefinition, type ModelId } from "../models/registry";
import type { MultiRadarTask } from "../models/multiRadar/types";
import type { BaseModelRequest, MetricDefinition, TaskSummary } from "../models/shared";

type ModelTask = TaskSummary<BaseModelRequest, unknown, unknown, unknown>;

export type WorkbenchResultContext =
  | { kind?: "model"; modelId: ModelId; task: ModelTask }
  | { kind: "multi-radar"; task: MultiRadarTask };

export const MULTI_RADAR_METRICS: MetricDefinition<Record<string, unknown>>[] = [
  { key: "visible_union_area_m2", label: "Visible union area", format: "area" },
  { key: "overlap_area_m2", label: "Overlap area", format: "area" },
  { key: "blind_area_m2", label: "Blind area", format: "area" },
  { key: "theoretical_union_area_m2", label: "Theoretical union area", format: "area" },
  { key: "successful_station_count", label: "Successful stations", format: "number" },
  { key: "failed_station_count", label: "Failed stations", format: "number" }
];

export function resultContextLabel(context: WorkbenchResultContext) {
  return context.kind === "multi-radar" ? "多雷达协同" : getModelDefinition(context.modelId).label;
}

export function resultContextMetricDefinitions(context: WorkbenchResultContext) {
  return context.kind === "multi-radar"
    ? MULTI_RADAR_METRICS
    : getModelDefinition(context.modelId).metrics as MetricDefinition<Record<string, unknown>>[];
}

export function resultContextMetrics(context: WorkbenchResultContext) {
  return context.task.metrics as Record<string, unknown> | null | undefined;
}
