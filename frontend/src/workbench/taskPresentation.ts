import { MODEL_IDS, MODEL_REGISTRY, type ModelId } from "../models/registry";
import type { BaseModelRequest, TaskStatus, TaskSummary } from "../models/shared";

type GenericTask = TaskSummary<BaseModelRequest, Record<string, unknown>>;

export interface WorkbenchTaskRow {
  key: string;
  modelId: ModelId;
  task: GenericTask;
  label: string;
  statusLabel: string;
  primaryMetric: string | null;
  timestamp: number;
}

const STATUS_LABELS: Record<TaskStatus, string> = {
  pending: "Waiting",
  running: "Running",
  finished: "Completed",
  failed: "Failed"
};

export function buildWorkbenchTaskRows(
  tasksByModel: Partial<Record<ModelId, readonly GenericTask[]>>
): WorkbenchTaskRow[] {
  return MODEL_IDS.flatMap((modelId) => (tasksByModel[modelId] ?? []).map((task) => ({
    key: `${modelId}:${task.task_id}`,
    modelId,
    task,
    label: MODEL_REGISTRY[modelId].label,
    statusLabel: task.execution_state === "cancelled" ? "Cancelled" : task.execution_state === "cancelling" ? "Cancelling" : STATUS_LABELS[task.status],
    primaryMetric: task.status === "finished" ? formatFirstMetric(modelId, task.metrics) : null,
    timestamp: taskTimestamp(task)
  }))).sort((left, right) => right.timestamp - left.timestamp);
}

export function isActiveTask(task: GenericTask) {
  return (task.status === "pending" || task.status === "running") && task.execution_state !== "cancelled";
}

function formatFirstMetric(modelId: ModelId, metrics: Record<string, unknown> | null | undefined) {
  if (!metrics) return null;
  const definition = MODEL_REGISTRY[modelId].metrics.find(({ key }) => hasMetric(metrics[key]));
  if (!definition) return null;
  return `${definition.label} ${formatMetric(metrics[definition.key], definition.format)}`;
}

function hasMetric(value: unknown) {
  return value !== null && value !== undefined && value !== "";
}

function formatMetric(value: unknown, format: "area" | "distance" | "duration" | "percent" | "number" | "text") {
  if (format === "text") return String(value);
  if (typeof value !== "number" || !Number.isFinite(value)) return String(value);
  if (format === "area") return value > 1_000_000
    ? `${formatDecimal(value / 1_000_000, 2, 2)} km2`
    : `${formatDecimal(value, 0, 2)} m2`;
  if (format === "distance") return value > 1_000
    ? `${formatDecimal(value / 1_000, 2, 2)} km`
    : `${formatDecimal(value, 0, 2)} m`;
  if (format === "duration") {
    const totalSeconds = Math.max(0, Math.round(value));
    const hours = Math.floor(totalSeconds / 3_600);
    const minutes = Math.floor((totalSeconds % 3_600) / 60);
    const seconds = totalSeconds % 60;
    return `${hours} h ${minutes} m ${seconds} s`;
  }
  if (format === "percent") return `${formatDecimal(value * 100, 0, 2)}%`;
  return formatDecimal(value, 0, 2);
}

function formatDecimal(value: number, minimumFractionDigits: number, maximumFractionDigits: number) {
  return value.toLocaleString("zh-CN", { minimumFractionDigits, maximumFractionDigits });
}

function taskTimestamp(task: GenericTask) {
  const value = task.updated_at ?? task.created_at;
  if (!value) return 0;
  const timestamp = new Date(value).getTime();
  return Number.isNaN(timestamp) ? 0 : timestamp;
}
