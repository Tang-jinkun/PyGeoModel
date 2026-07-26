import type { RadarAdvancedInput, RadarCoverageInput, RadarInput, RadarMetrics, RadarRequest, RadarTargetInput } from "../radar/types";

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

export interface MultiRadarTask {
  task_id: string;
  dem_id: string;
  status: MultiRadarTaskState;
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
  outputs?: {
    visible_union_geojson?: string | null;
    overlap_geojson?: string | null;
    blind_geojson?: string | null;
    coverage_count_geojson?: string | null;
    stations_geojson?: string | null;
    station_summaries_json?: string | null;
    fusion_scene_glb?: string | null;
    cooperative_intersection_glb?: string | null;
  } | null;
  stations: MultiRadarStationSummary[];
  request?: MultiRadarRequest | null;
}

export interface MultiRadarTargetEvaluation {
  task_id: string;
  detected: boolean;
  contributors: Array<{ radar_id: string; detected: boolean }>;
}
