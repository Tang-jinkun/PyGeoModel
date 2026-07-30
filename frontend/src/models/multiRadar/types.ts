import type { RadarAdvancedInput, RadarCoverageInput, RadarInput, RadarMetrics, RadarRequest, RadarTargetInput } from "../radar/types";
import type { OutputFile, ResultState, TaskExecutionState } from "../shared";

export interface MultiRadarStationInput {
  radar_id: string;
  name?: string | null;
  radar: RadarInput;
  target?: RadarTargetInput;
  coverage: Pick<RadarCoverageInput, "max_range_m"> & Partial<Omit<RadarCoverageInput, "max_range_m">>;
  advanced?: RadarAdvancedInput;
  reserved_radar_params?: RadarRequest["reserved_radar_params"];
}

export type MultiRadarPresentationMode = "aggregate" | "cooperative_3d";

export interface MultiRadarRequest {
  dem_id: string;
  radars: MultiRadarStationInput[];
  presentation_mode?: MultiRadarPresentationMode;
}

export type MultiRadarTaskState = "pending" | "running" | "finished" | "partial" | "failed";

export interface MultiRadarStationSummary {
  radar_id: string;
  name?: string | null;
  status: "pending" | "running" | "finished" | "failed";
  message: string;
  metrics?: RadarMetrics | null;
  scene_task_id?: string | null;
  scene_status?: "pending" | "running" | "finished" | "failed" | null;
  scene_message?: string;
}

export interface MultiRadarSceneAsset {
  asset_id: string;
  task_id: string;
  radar_id?: string | null;
  kind: "scene_glb" | "radar_platform_glb";
  label: string;
  render_tier: "world" | "emphasis" | "equipment";
  file: OutputFile;
}

export interface MultiRadarTask {
  task_id: string;
  dem_id: string;
  status: MultiRadarTaskState;
  result_state: ResultState;
  result_reason_code?: string | null;
  rerun_of?: string | null;
  progress: number;
  message: string;
  created_at?: string | null;
  updated_at?: string | null;
  metrics?: {
    visible_union_area_m2: number;
    overlap_area_m2: number;
    blind_area_m2: number;
    theoretical_union_area_m2: number;
    successful_station_count: number;
    failed_station_count: number;
  } | null;
  output_files: OutputFile[];
  scene_assets?: MultiRadarSceneAsset[];
  stations: MultiRadarStationSummary[];
  request?: MultiRadarRequest | null;
  execution_state?: TaskExecutionState;
  queue_position?: number | null;
  estimated_wait_seconds?: number | null;
  estimated_run_seconds?: number | null;
  cancel_requested?: boolean;
}

export interface MultiRadarTargetEvaluation {
  task_id: string;
  detected: boolean;
  contributors: Array<{ radar_id: string; detected: boolean }>;
}
