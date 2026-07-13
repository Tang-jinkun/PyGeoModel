import type { ModelDefinition, ValidationIssue } from "../shared";
import type { WatchpostMetrics, WatchpostRequest } from "./types";

export const watchpostDefinition = {
  id: "watchpost",
  label: "Watchpost Detection",
  taskBasePath: "/api/watchpost/detection",
  spatialInput: "point",
  createDefaultRequest: (): WatchpostRequest => ({
    dem_id: "",
    observer: { lon: 79.80513693057287, lat: 31.4827708959419, height_m: 2 },
    target: { height_m: 1.7 },
    coverage: { max_range_m: 5000, scan_mode: "omni", azimuth_deg: 0, view_angle_deg: 360 },
    analysis: { use_curvature: true, curvature_coeff: 0.75, output_simplify_tolerance_m: null }
  }),
  validate: (request: WatchpostRequest): ValidationIssue[] => request.coverage.max_range_m <= 0
    ? [{ path: "coverage.max_range_m", message: "max_range_m must be greater than 0" }]
    : [],
  metrics: [
    { key: "theoretical_area_m2", label: "Theoretical area", format: "area" }, { key: "visible_area_m2", label: "Visible area", format: "area" }, { key: "blocked_area_m2", label: "Blocked area", format: "area" }, { key: "blocked_ratio", label: "Blocked ratio", format: "percent" }, { key: "max_range_m", label: "Maximum range", format: "distance" }, { key: "effective_view_angle_deg", label: "Effective view angle", format: "number" }, { key: "observer_ground_elevation_m", label: "Observer ground elevation", format: "distance" }, { key: "observer_altitude_m", label: "Observer altitude", format: "distance" }
  ],
  outputLayers: [
    { kind: "range_geojson", label: "Detection range", color: "#2563eb", geometry: "fill", defaultOpacity: 0.12 }, { kind: "blocked_geojson", label: "Blocked terrain", color: "#dc2626", geometry: "fill", defaultOpacity: 0.28 }, { kind: "visible_geojson", label: "Visible coverage", color: "#16a34a", geometry: "fill", defaultOpacity: 0.35, primary: true }
  ]
} satisfies ModelDefinition<WatchpostRequest, WatchpostMetrics>;
