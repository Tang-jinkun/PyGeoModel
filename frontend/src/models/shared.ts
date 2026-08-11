export const MODEL_IDS = ["radar", "uav", "watchpost", "artillery", "reconVehicle", "mobility", "airCorridor"] as const;
export type ModelId = (typeof MODEL_IDS)[number];
export type TaskStatus = "pending" | "running" | "finished" | "failed";
export type TaskExecutionState = "unknown" | "queued" | "running" | "cancelling" | "cancelled" | "finished" | "failed";
export type ResultState = "pending" | "ready" | "unavailable";
export type SpatialInputKind = "point" | "point-target" | "point-or-route" | "start-end" | "start-end-threats";

export interface BaseModelRequest { dem_id: string }
export interface OutputFile {
  kind: string; label: string; filename: string; media_type: string; required: boolean;
  size_bytes?: number | null; exists: boolean; download_path?: string | null;
  url?: string | null; download_url?: string | null;
}
export interface TaskSummary<
  Request extends BaseModelRequest = BaseModelRequest,
  Metrics = Record<string, unknown>,
  Model = Record<string, unknown>,
  Diagnostics = Record<string, unknown>
> {
  task_id: string; dem_id?: string | null; status: TaskStatus; result_state: ResultState;
  result_reason_code?: string | null; rerun_of?: string | null; progress: number; message: string;
  created_at?: string | null; updated_at?: string | null; request?: Request | null;
  metrics?: Metrics | null; outputs?: Record<string, string | null> | null;
  model?: Model | null; diagnostics?: Diagnostics | null;
  output_files: OutputFile[]; warnings: string[];
  execution_state?: TaskExecutionState; queue_position?: number | null;
  estimated_wait_seconds?: number | null; estimated_run_seconds?: number | null;
  cancel_requested?: boolean;
}
export interface MetricDefinition<Metrics> {
  key: keyof Metrics & string; label: string; format: "area" | "distance" | "duration" | "percent" | "number" | "text";
}
export interface OutputLayerDefinition {
  kind: string; label: string; color: string; geometry: "fill" | "line" | "circle";
  defaultOpacity: number; primary?: boolean;
}
export interface ValidationIssue { path: string; message: string }
export interface ModelDefinition<Request extends BaseModelRequest, Metrics> {
  id: ModelId; label: string; taskBasePath: string; spatialInput: SpatialInputKind;
  inputSlots: readonly InputSlotDefinition[];
  createDefaultRequest(): Request; validate(request: Request): ValidationIssue[];
  metrics: MetricDefinition<Metrics>[]; outputLayers: OutputLayerDefinition[];
}
import type { InputSlotDefinition } from "./inputSlots";
