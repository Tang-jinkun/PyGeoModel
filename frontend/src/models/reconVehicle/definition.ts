import type { ModelDefinition, ValidationIssue } from "../shared";
import type { ReconVehicleMetrics, ReconVehicleRequest } from "./types";

export const reconVehicleDefinition = {
  id: "reconVehicle",
  label: "Recon Vehicle Coverage",
  taskBasePath: "/api/recon-vehicle/coverage",
  spatialInput: "point-or-route",
  createDefaultRequest: (): ReconVehicleRequest => ({
    dem_id: "",
    vehicle: { lon: 79.80513693057287, lat: 31.4827708959419, heading_deg: 0, mast_height_m: 3 },
    route: null,
    sensor: { sensor_type: "optical", max_range_m: 5000, min_range_m: 0, scan_mode: "sector", view_angle_deg: 120 },
    target: { height_m: 1.7 },
    analysis: { use_terrain_occlusion: true, use_curvature: true, curvature_coeff: 0.75, output_simplify_tolerance_m: null }
  }),
  validate: (request: ReconVehicleRequest): ValidationIssue[] => {
    const issues: ValidationIssue[] = [];
    if (request.sensor.min_range_m >= request.sensor.max_range_m) issues.push({ path: "sensor.max_range_m", message: "min_range_m must be less than max_range_m" });
    if (request.route !== null && request.route.waypoints.length < 2) issues.push({ path: "route.waypoints", message: "route.waypoints must contain at least two points when provided" });
    return issues;
  },
  metrics: [
    { key: "theoretical_area_m2", label: "Theoretical area", format: "area" }, { key: "visible_area_m2", label: "Visible area", format: "area" }, { key: "blocked_area_m2", label: "Blocked area", format: "area" }, { key: "blocked_ratio", label: "Blocked ratio", format: "percent" }, { key: "max_range_m", label: "Maximum range", format: "distance" }, { key: "effective_view_angle_deg", label: "Effective view angle", format: "number" }, { key: "coverage_point_count", label: "Coverage points", format: "number" }, { key: "route_length_m", label: "Route length", format: "distance" }, { key: "average_visible_area_m2", label: "Average visible area", format: "area" }, { key: "overlap_area_m2", label: "Overlap area", format: "area" }, { key: "vehicle_ground_elevation_m", label: "Vehicle ground elevation", format: "distance" }, { key: "sensor_altitude_m", label: "Sensor altitude", format: "distance" }
  ],
  outputLayers: [
    { kind: "footprint_geojson", label: "Sensor footprint", color: "#2563eb", geometry: "fill", defaultOpacity: 0.18 }, { kind: "blocked_geojson", label: "Blocked terrain", color: "#dc2626", geometry: "fill", defaultOpacity: 0.28 }, { kind: "visible_geojson", label: "Visible coverage", color: "#16a34a", geometry: "fill", defaultOpacity: 0.35, primary: true }
  ]
} satisfies ModelDefinition<ReconVehicleRequest, ReconVehicleMetrics>;
