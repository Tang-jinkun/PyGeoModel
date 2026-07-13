export const MODEL_IDS = ["radar", "uav", "watchpost", "artillery", "reconVehicle", "mobility", "airCorridor"] as const;
export type ModelId = (typeof MODEL_IDS)[number];
export type TaskStatus = "pending" | "running" | "finished" | "failed";
export type SpatialInputKind = "point" | "point-or-route" | "start-end" | "start-end-threats";

export interface BaseModelRequest { dem_id: string }
export interface OutputFile {
  kind: string; label: string; url: string; download_url: string; filename: string;
  media_type: string; size_bytes?: number | null; exists: boolean;
}
export interface TaskSummary<Request extends BaseModelRequest = BaseModelRequest, Metrics = Record<string, unknown>> {
  task_id: string; dem_id?: string | null; status: TaskStatus; progress: number; message: string;
  created_at?: string | null; updated_at?: string | null; request?: Request | null;
  metrics?: Metrics | null; outputs?: Record<string, string | null> | null;
  output_files: OutputFile[]; warnings: string[];
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
  createDefaultRequest(): Request; validate(request: Request): ValidationIssue[];
  metrics: MetricDefinition<Metrics>[]; outputLayers: OutputLayerDefinition[];
}
