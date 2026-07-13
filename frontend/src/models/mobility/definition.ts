import type { ModelDefinition, ValidationIssue } from "../shared";
import type { MobilityMetrics, MobilityRequest } from "./types";

export const mobilityDefinition = {
  id: "mobility",
  label: "Mobility Accessibility",
  taskBasePath: "/api/mobility/accessibility",
  spatialInput: "start-end",
  createDefaultRequest: (): MobilityRequest => ({
    dem_id: "",
    start: { lon: 79.80513693057287, lat: 31.4827708959419 }, end: { lon: 79.81513693057287, lat: 31.4927708959419 },
    vehicles: {
      wheeled: { enabled: true, base_speed_kph: 45, max_slope_deg: 18, slope_penalty: 2.2, road_speed_multiplier: 1.5, offroad_speed_multiplier: 0.65 },
      tracked: { enabled: true, base_speed_kph: 35, max_slope_deg: 30, slope_penalty: 1.4, road_speed_multiplier: 1.25, offroad_speed_multiplier: 0.85 }
    },
    road_network: null,
    analysis: { allow_diagonal: true, max_search_radius_m: null, output_simplify_tolerance_m: null }
  }),
  validate: (request: MobilityRequest): ValidationIssue[] => !request.vehicles.wheeled.enabled && !request.vehicles.tracked.enabled ? [{ path: "vehicles", message: "At least one vehicle type must be enabled" }] : [],
  metrics: [
    { key: "winner", label: "Preferred vehicle", format: "text" }, { key: "time_saving_seconds", label: "Time saving", format: "duration" }, { key: "time_saving_ratio", label: "Time saving ratio", format: "percent" }, { key: "wheeled", label: "Wheeled result", format: "text" }, { key: "tracked", label: "Tracked result", format: "text" }
  ],
  outputLayers: [
    { kind: "road_mask_geojson", label: "Road network", color: "#f59e0b", geometry: "fill", defaultOpacity: 0.18 }, { kind: "wheeled_path_geojson", label: "Wheeled route", color: "#2563eb", geometry: "line", defaultOpacity: 0.9, primary: true }, { kind: "tracked_path_geojson", label: "Tracked route", color: "#16a34a", geometry: "line", defaultOpacity: 0.9 }
  ]
} satisfies ModelDefinition<MobilityRequest, MobilityMetrics>;
