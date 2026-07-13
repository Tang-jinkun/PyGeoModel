import type { ModelDefinition, ValidationIssue } from "../shared";
import type { ArtilleryMetrics, ArtilleryRequest } from "./types";

export const artilleryDefinition = {
  id: "artillery",
  label: "Artillery Coverage",
  taskBasePath: "/api/artillery/coverage",
  spatialInput: "point",
  createDefaultRequest: (): ArtilleryRequest => ({
    dem_id: "",
    battery: { lon: 79.80513693057287, lat: 31.4827708959419, height_m: 0, altitude_mode: "agl" }, target: { target_height_m: 0 },
    weapon: { min_range_m: 1000, max_range_m: 15000, azimuth_deg: 0, traverse_deg: 360, muzzle_velocity_mps: 500, elevation_deg: 45 },
    munition: { munition_type: "he", lethal_radius_m: 50, effective_radius_m: 120 },
    analysis: { use_dem_elevation: true, use_terrain_masking: true, sample_resolution_m: null, trajectory_samples: 80, clearance_margin_m: 0, output_simplify_tolerance_m: null }
  }),
  validate: (request: ArtilleryRequest): ValidationIssue[] => request.weapon.min_range_m >= request.weapon.max_range_m ? [{ path: "weapon.max_range_m", message: "min_range_m must be less than max_range_m" }] : [],
  metrics: [
    { key: "theoretical_area_m2", label: "Theoretical area", format: "area" }, { key: "reachable_area_m2", label: "Reachable area", format: "area" }, { key: "terrain_masked_area_m2", label: "Terrain masked area", format: "area" }, { key: "terrain_masked_ratio", label: "Terrain masked ratio", format: "percent" }, { key: "lethal_area_m2", label: "Lethal area", format: "area" }, { key: "effective_area_m2", label: "Effective area", format: "area" }, { key: "min_range_m", label: "Minimum range", format: "distance" }, { key: "max_range_m", label: "Maximum range", format: "distance" }, { key: "effective_traverse_deg", label: "Effective traverse", format: "number" }, { key: "lethal_radius_m", label: "Lethal radius", format: "distance" }, { key: "effective_radius_m", label: "Effective radius", format: "distance" }, { key: "sample_point_count", label: "Sample points", format: "number" }, { key: "reachable_sample_count", label: "Reachable samples", format: "number" }, { key: "masked_sample_count", label: "Masked samples", format: "number" }, { key: "min_clearance_m", label: "Minimum clearance", format: "distance" }, { key: "mean_clearance_m", label: "Mean clearance", format: "distance" }, { key: "battery_ground_elevation_m", label: "Battery ground elevation", format: "distance" }, { key: "battery_altitude_m", label: "Battery altitude", format: "distance" }
  ],
  outputLayers: [
    { kind: "theoretical_geojson", label: "Theoretical coverage", color: "#2563eb", geometry: "fill", defaultOpacity: 0.12 }, { kind: "terrain_masked_geojson", label: "Terrain masked", color: "#dc2626", geometry: "fill", defaultOpacity: 0.28 }, { kind: "reachable_geojson", label: "Reachable coverage", color: "#16a34a", geometry: "fill", defaultOpacity: 0.35, primary: true }, { kind: "sample_points_geojson", label: "Trajectory samples", color: "#f59e0b", geometry: "circle", defaultOpacity: 0.85 }
  ]
} satisfies ModelDefinition<ArtilleryRequest, ArtilleryMetrics>;
