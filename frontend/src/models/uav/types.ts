export interface UavPlatformInput { lon: number; lat: number; altitude_m: number; altitude_mode: "agl" | "amsl"; heading_deg: number; pitch_deg: number; roll_deg: number }
export interface UavRouteInput { waypoints: UavPlatformInput[]; sample_interval_m: number }
export interface UavSensorInput { sensor_type: "camera" | "thermal" | "eo"; h_fov_deg: number; v_fov_deg: number; max_range_m: number; min_range_m: number; ground_resolution_m: number | null }
export interface UavAnalysisInput { target_height_m: number; use_terrain_occlusion: boolean; sample_resolution_m: number | null; output_simplify_tolerance_m: number | null }
export interface UavRequest { dem_id: string; uav: UavPlatformInput; route: UavRouteInput | null; sensor: UavSensorInput; analysis: UavAnalysisInput }
export interface UavMetrics { theoretical_area_m2: number; visible_area_m2: number; blocked_area_m2: number; blocked_ratio: number; max_ground_distance_m: number; coverage_point_count: number; route_length_m: number; average_visible_area_m2: number; overlap_area_m2: number }
