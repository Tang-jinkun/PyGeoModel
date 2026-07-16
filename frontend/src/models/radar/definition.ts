import type { ModelDefinition, ValidationIssue } from "../shared";
import type { RadarMetrics, RadarRequest } from "./types";

export const radarDefinition = {
  id: "radar",
  label: "Radar Coverage",
  taskBasePath: "/api/radar/coverage",
  spatialInput: "point",
  createDefaultRequest: (): RadarRequest => ({
    dem_id: "",
    radar: { lon: 79.80513693057287, lat: 31.4827708959419, height_m: 10 },
    target: { height_m: 0 },
    coverage: { max_range_m: 50000, scan_mode: "omni", azimuth_deg: 90, beam_width_deg: 120 },
    advanced: { use_curvature: true, curvature_coeff: 0.75, output_simplify_tolerance_m: 30, voxel_grid_size: 128, voxel_vertical_levels: 16, voxel_max_height_m: 3000, min_elevation_deg: -8, max_elevation_deg: 90, vertical_beam_width_deg: 98, visual_dome_mode: true, height_layers_m: [] },
    reserved_radar_params: { frequency_hz: null, transmit_power_w: null, antenna_gain_db: null, receiver_sensitivity_dbm: null, target_rcs_m2: null, system_loss_db: null, pulse_width_s: null, prf_hz: null, noise_figure_db: null, detection_probability: null, false_alarm_probability: null }
  }),
  validate: (request: RadarRequest): ValidationIssue[] => {
    const issues: ValidationIssue[] = [];
    if (request.advanced.max_elevation_deg < request.advanced.min_elevation_deg) issues.push({ path: "advanced.max_elevation_deg", message: "max_elevation_deg must be greater than or equal to min_elevation_deg" });
    const validLayers = new Set(request.advanced.height_layers_m.filter((height) => Number.isFinite(height) && height >= 0 && height <= request.advanced.voxel_max_height_m));
    if (validLayers.size > 20) issues.push({ path: "advanced.height_layers_m", message: "height_layers_m cannot contain more than 20 values" });
    return issues;
  },
  metrics: [
    { key: "requested_theoretical_area_m2", label: "Requested theoretical area", format: "area" }, { key: "theoretical_area_m2", label: "Analyzed theoretical area", format: "area" }, { key: "unknown_area_m2", label: "Unknown DEM area", format: "area" }, { key: "visible_area_m2", label: "Visible area", format: "area" }, { key: "blocked_area_m2", label: "Blocked area", format: "area" }, { key: "blocked_ratio", label: "Blocked ratio", format: "percent" }, { key: "terrain_visible_area_m2", label: "Terrain visible area", format: "area" }, { key: "beam_eligible_area_m2", label: "Beam eligible area", format: "area" }, { key: "radar_equation_limited_area_m2", label: "Radar equation limited area", format: "area" }
  ],
  outputLayers: [
    { kind: "range_geojson", label: "Detection range", color: "#2563eb", geometry: "fill", defaultOpacity: 0.12 }, { kind: "blocked_geojson", label: "Blocked terrain", color: "#dc2626", geometry: "fill", defaultOpacity: 0.28 }, { kind: "visible_geojson", label: "Visible coverage", color: "#16a34a", geometry: "fill", defaultOpacity: 0.35, primary: true }
  ]
} satisfies ModelDefinition<RadarRequest, RadarMetrics>;
