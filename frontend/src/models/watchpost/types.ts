export interface WatchpostObserverInput { lon: number; lat: number; height_m: number }
export interface WatchpostTargetInput { height_m: number }
export interface WatchpostCoverageInput { max_range_m: number; scan_mode: "omni" | "sector"; azimuth_deg: number; view_angle_deg: number }
export interface WatchpostAnalysisInput { use_curvature: boolean; curvature_coeff: number; output_simplify_tolerance_m: number | null }
export interface WatchpostRequest { dem_id: string; observer: WatchpostObserverInput; target: WatchpostTargetInput; coverage: WatchpostCoverageInput; analysis: WatchpostAnalysisInput }
export interface WatchpostMetrics { theoretical_area_m2: number; visible_area_m2: number; blocked_area_m2: number; blocked_ratio: number; max_range_m: number; effective_view_angle_deg: number; observer_ground_elevation_m: number; observer_altitude_m: number }
