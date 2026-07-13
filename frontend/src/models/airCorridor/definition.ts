import type { ModelDefinition, ValidationIssue } from "../shared";
import type { AirCorridorMetrics, AirCorridorRequest, AirDefenseThreatInput } from "./types";

function validateThreat(threat: AirDefenseThreatInput, index: number): ValidationIssue[] {
  const prefix = `threats.${index}`;
  const issues: ValidationIssue[] = [];
  if (threat.min_range_m >= threat.max_range_m) issues.push({ path: `${prefix}.max_range_m`, message: "min_range_m must be less than max_range_m" });
  if (threat.min_altitude_m >= threat.max_altitude_m) issues.push({ path: `${prefix}.max_altitude_m`, message: "min_altitude_m must be less than max_altitude_m" });
  if (threat.kill_zone_radius_m !== null && threat.warning_zone_radius_m !== null && threat.kill_zone_radius_m > threat.warning_zone_radius_m) issues.push({ path: `${prefix}.kill_zone_radius_m`, message: "kill_zone_radius_m must be less than or equal to warning_zone_radius_m" });
  return issues;
}

export const airCorridorDefinition = {
  id: "airCorridor",
  label: "Air Corridor Planning",
  taskBasePath: "/api/air-corridor/planning",
  spatialInput: "start-end-threats",
  createDefaultRequest: (): AirCorridorRequest => ({
    dem_id: "",
    start: { lon: 79.80513693057287, lat: 31.4827708959419, altitude_m: 1200, altitude_mode: "agl" }, end: { lon: 79.81513693057287, lat: 31.4927708959419, altitude_m: 1200, altitude_mode: "agl" },
    aircraft: { cruise_speed_kph: 180, min_agl_m: 100, max_agl_m: 3000, max_climb_rate_mps: 8, max_descent_rate_mps: 10 }, altitude_layers_m: [300, 600, 900, 1200, 1800, 2400], threats: [],
    planning: { corridor_width_m: 500, horizontal_resolution_m: 250, allow_altitude_change: true, threat_weight: 1, distance_weight: 0.25, altitude_change_weight: 0.15, terrain_clearance_weight: 0.4, output_simplify_tolerance_m: null }
  }),
  validate: (request: AirCorridorRequest): ValidationIssue[] => {
    const issues: ValidationIssue[] = [];
    if (request.aircraft.min_agl_m >= request.aircraft.max_agl_m) issues.push({ path: "aircraft.max_agl_m", message: "min_agl_m must be less than max_agl_m" });
    request.threats.forEach((threat, index) => issues.push(...validateThreat(threat, index)));
    return issues;
  },
  metrics: [
    { key: "route_found", label: "Route found", format: "text" }, { key: "failure_reason", label: "Failure reason", format: "text" }, { key: "risk_score", label: "Risk score", format: "number" }, { key: "max_segment_risk", label: "Maximum segment risk", format: "number" }, { key: "mean_segment_risk", label: "Mean segment risk", format: "number" }, { key: "corridor_length_m", label: "Corridor length", format: "distance" }, { key: "estimated_time_seconds", label: "Estimated time", format: "duration" }, { key: "min_terrain_clearance_m", label: "Minimum terrain clearance", format: "distance" }, { key: "mean_terrain_clearance_m", label: "Mean terrain clearance", format: "distance" }, { key: "altitude_change_count", label: "Altitude changes", format: "number" }, { key: "min_altitude_m", label: "Minimum altitude", format: "distance" }, { key: "max_altitude_m", label: "Maximum altitude", format: "distance" }, { key: "threat_intersection_count", label: "Threat intersections", format: "number" }, { key: "nearest_threat_distance_m", label: "Nearest threat distance", format: "distance" }
  ],
  outputLayers: [
    { kind: "threat_zones_geojson", label: "Threat zones", color: "#dc2626", geometry: "fill", defaultOpacity: 0.25 }, { kind: "corridor_buffer_geojson", label: "Corridor buffer", color: "#2563eb", geometry: "fill", defaultOpacity: 0.18 }, { kind: "corridor_path_geojson", label: "Corridor path", color: "#16a34a", geometry: "line", defaultOpacity: 0.95, primary: true }, { kind: "risk_samples_geojson", label: "Risk samples", color: "#f59e0b", geometry: "circle", defaultOpacity: 0.85 }
  ]
} satisfies ModelDefinition<AirCorridorRequest, AirCorridorMetrics>;
