export interface RadarInput { lon: number; lat: number; height_m: number }
export interface RadarTargetInput { height_m: number }
export interface RadarCoverageInput { max_range_m: number; scan_mode: "omni" | "sector"; azimuth_deg: number; beam_width_deg: number }
export interface RadarAdvancedInput {
  use_curvature: boolean; curvature_coeff: number; output_simplify_tolerance_m: number | null;
  voxel_grid_size: number; voxel_vertical_levels: number; voxel_max_height_m: number;
  min_elevation_deg: number; max_elevation_deg: number; vertical_beam_width_deg: number;
  visual_dome_mode: boolean; height_layers_m: number[];
}
export interface ReservedRadarParams {
  frequency_hz: number | null; transmit_power_w: number | null; antenna_gain_db: number | null;
  receiver_sensitivity_dbm: number | null; target_rcs_m2: number | null; system_loss_db: number | null;
  pulse_width_s: number | null; prf_hz: number | null; noise_figure_db: number | null;
  detection_probability: number | null; false_alarm_probability: number | null;
}
export interface RadarRequest {
  dem_id: string; radar: RadarInput; target: RadarTargetInput; coverage: RadarCoverageInput;
  advanced: RadarAdvancedInput; reserved_radar_params?: Partial<ReservedRadarParams>;
}
export interface RadarMetrics {
  requested_theoretical_area_m2: number; theoretical_area_m2: number; unknown_area_m2: number;
  visible_area_m2: number; blocked_area_m2: number; blocked_ratio: number;
  terrain_visible_area_m2: number; beam_eligible_area_m2: number; radar_equation_limited_area_m2: number;
}
export interface BeamClipProfile { azimuth_step_deg: number; radius_m: number[] }
export interface RadarModelMetadata {
  coverage_contract_version: number;
  target_epsg: number;
  radar_projected_xy: number[];
  projected_dem_bounds: number[];
  projected_dem_resolution_m: number[];
  dem_coverage_ratio: number;
  max_range_m: number;
  scan_mode: string;
  azimuth_deg: number;
  beam_width_deg: number;
  simplify_tolerance_m: number;
  gdal_viewshed_command: string[];
  voxel_grid_size: number;
  voxel_vertical_levels: number;
  voxel_max_height_m: number;
  min_elevation_deg: number;
  max_elevation_deg: number;
  vertical_beam_width_deg: number;
  visual_dome_mode: boolean;
  height_layers_m: number[];
  radar_equation_active: boolean;
  radar_equation_max_range_m?: number | null;
  effective_max_range_m: number;
  beam_clip_profile: BeamClipProfile | null;
}
export interface RadarDiagnostics {
  radar_equation_active: boolean;
  radar_equation_max_range_m?: number | null;
  effective_max_range_m: number;
  terrain_blocked_area_m2: number;
  elevation_limited_area_m2: number;
  radar_equation_limited_area_m2: number;
  notes: string[];
}
