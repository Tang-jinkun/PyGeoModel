export interface ReconVehiclePositionInput { lon: number; lat: number; heading_deg: number; mast_height_m: number }
export interface ReconVehicleRouteInput { waypoints: ReconVehiclePositionInput[]; sample_interval_m: number }
export interface ReconVehicleSensorInput { sensor_type: "optical" | "thermal" | "radar" | "generic"; max_range_m: number; min_range_m: number; scan_mode: "omni" | "sector"; view_angle_deg: number }
export interface ReconVehicleTargetInput { height_m: number }
export interface ReconVehicleAnalysisInput { use_terrain_occlusion: boolean; use_curvature: boolean; curvature_coeff: number; output_simplify_tolerance_m: number | null }
export interface ReconVehicleRequest { dem_id: string; vehicle: ReconVehiclePositionInput; route: ReconVehicleRouteInput | null; sensor: ReconVehicleSensorInput; target: ReconVehicleTargetInput; analysis: ReconVehicleAnalysisInput }
export interface ReconVehicleMetrics { theoretical_area_m2: number; visible_area_m2: number; blocked_area_m2: number; blocked_ratio: number; max_range_m: number; effective_view_angle_deg: number; coverage_point_count: number; route_length_m: number; average_visible_area_m2: number; overlap_area_m2: number; vehicle_ground_elevation_m: number; sensor_altitude_m: number }
