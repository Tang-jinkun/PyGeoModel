export interface MobilityPointInput { lon: number; lat: number }
export interface MobilityVehicleInput { enabled: boolean; base_speed_kph: number; max_slope_deg: number; slope_penalty: number; road_speed_multiplier: number; offroad_speed_multiplier: number }
export interface MobilityVehiclesInput { wheeled: MobilityVehicleInput; tracked: MobilityVehicleInput }
export interface MobilityRoadNetworkInput { geojson: Record<string, unknown> | null; road_buffer_m: number; road_classes: Record<string, number> }
export interface MobilityAnalysisInput { allow_diagonal: boolean; max_search_radius_m: number | null; output_simplify_tolerance_m: number | null }
export interface MobilityRequest { dem_id: string; start: MobilityPointInput; end: MobilityPointInput; vehicles: MobilityVehiclesInput; road_network: MobilityRoadNetworkInput | null; analysis: MobilityAnalysisInput }
export interface MobilityVehicleMetrics { reachable: boolean; travel_time_seconds: number | null; travel_distance_m: number; average_speed_kph: number; road_distance_m: number; offroad_distance_m: number; max_slope_deg: number | null; mean_slope_deg: number | null; failure_reason: string | null }
export interface MobilityMetrics { winner: "wheeled" | "tracked" | "tie" | "none"; time_saving_seconds: number | null; time_saving_ratio: number | null; wheeled: MobilityVehicleMetrics; tracked: MobilityVehicleMetrics }
