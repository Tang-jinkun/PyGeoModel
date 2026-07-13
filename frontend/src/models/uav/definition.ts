import type { ModelDefinition, ValidationIssue } from "../shared";
import type { UavMetrics, UavRequest } from "./types";

export const uavDefinition = {
  id: "uav",
  label: "UAV Reconnaissance",
  taskBasePath: "/api/uav/recon",
  spatialInput: "point-or-route",
  createDefaultRequest: (): UavRequest => ({
    dem_id: "",
    uav: { lon: 79.80513693057287, lat: 31.4827708959419, altitude_m: 500, altitude_mode: "agl", heading_deg: 0, pitch_deg: -45, roll_deg: 0 },
    route: null,
    sensor: { sensor_type: "camera", h_fov_deg: 60, v_fov_deg: 40, max_range_m: 5000, min_range_m: 0, ground_resolution_m: null },
    analysis: { target_height_m: 0, use_terrain_occlusion: true, sample_resolution_m: null, output_simplify_tolerance_m: null }
  }),
  validate: (request: UavRequest): ValidationIssue[] => {
    const issues: ValidationIssue[] = [];
    if (request.sensor.min_range_m >= request.sensor.max_range_m) issues.push({ path: "sensor.max_range_m", message: "min_range_m must be less than max_range_m" });
    if (request.route?.waypoints.length === 1) issues.push({ path: "route.waypoints", message: "route.waypoints must contain at least two points when provided" });
    return issues;
  },
  metrics: [
    { key: "theoretical_area_m2", label: "Theoretical area", format: "area" }, { key: "visible_area_m2", label: "Visible area", format: "area" }, { key: "blocked_area_m2", label: "Blocked area", format: "area" }, { key: "blocked_ratio", label: "Blocked ratio", format: "percent" }, { key: "max_ground_distance_m", label: "Maximum ground distance", format: "distance" }, { key: "coverage_point_count", label: "Coverage points", format: "number" }, { key: "route_length_m", label: "Route length", format: "distance" }, { key: "average_visible_area_m2", label: "Average visible area", format: "area" }, { key: "overlap_area_m2", label: "Overlap area", format: "area" }
  ],
  outputLayers: [
    { kind: "footprint_geojson", label: "Sensor footprint", color: "#2563eb", geometry: "fill", defaultOpacity: 0.18 }, { kind: "blocked_geojson", label: "Blocked terrain", color: "#dc2626", geometry: "fill", defaultOpacity: 0.28 }, { kind: "visible_geojson", label: "Visible coverage", color: "#16a34a", geometry: "fill", defaultOpacity: 0.35, primary: true }
  ]
} satisfies ModelDefinition<UavRequest, UavMetrics>;
