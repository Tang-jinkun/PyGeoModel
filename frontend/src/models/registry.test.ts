import { describe, expect, it } from "vitest";
import { MODEL_IDS, MODEL_REGISTRY, getModelDefinition } from "./registry";

describe("model registry", () => {
  it("registers every backend model with a unique task path", () => {
    expect(MODEL_IDS).toEqual([
      "radar", "uav", "watchpost", "artillery", "reconVehicle", "mobility", "airCorridor"
    ]);
    expect(MODEL_IDS.map((id) => MODEL_REGISTRY[id].taskBasePath)).toEqual([
      "/api/radar/coverage",
      "/api/uav/recon",
      "/api/watchpost/detection",
      "/api/artillery/coverage",
      "/api/recon-vehicle/coverage",
      "/api/mobility/accessibility",
      "/api/air-corridor/planning"
    ]);
    expect(new Set(MODEL_IDS.map((id) => getModelDefinition(id).taskBasePath)).size).toBe(7);
  });

  it("provides a new default request and at least one output layer per model", () => {
    for (const id of MODEL_IDS) {
      const first = MODEL_REGISTRY[id].createDefaultRequest();
      const second = MODEL_REGISTRY[id].createDefaultRequest();
      expect(first).not.toBe(second);
      expect(first.dem_id).toBe("");
      expect(MODEL_REGISTRY[id].outputLayers.length).toBeGreaterThan(0);
    }
  });

  it("reports backend cross-field validation issues", () => {
    expect(MODEL_REGISTRY.radar.validate({
      ...MODEL_REGISTRY.radar.createDefaultRequest(),
      advanced: { ...MODEL_REGISTRY.radar.createDefaultRequest().advanced, min_elevation_deg: 40, max_elevation_deg: 20 }
    })).toContainEqual({ path: "advanced.max_elevation_deg", message: "max_elevation_deg must be greater than or equal to min_elevation_deg" });
    expect(MODEL_REGISTRY.uav.validate({
      ...MODEL_REGISTRY.uav.createDefaultRequest(),
      sensor: { ...MODEL_REGISTRY.uav.createDefaultRequest().sensor, min_range_m: 5000, max_range_m: 5000 }
    })).toContainEqual({ path: "sensor.max_range_m", message: "min_range_m must be less than max_range_m" });
    expect(MODEL_REGISTRY.watchpost.validate(MODEL_REGISTRY.watchpost.createDefaultRequest())).toEqual([]);
    expect(MODEL_REGISTRY.artillery.validate({
      ...MODEL_REGISTRY.artillery.createDefaultRequest(),
      weapon: { ...MODEL_REGISTRY.artillery.createDefaultRequest().weapon, min_range_m: 15000, max_range_m: 1000 }
    })).toContainEqual({ path: "weapon.max_range_m", message: "min_range_m must be less than max_range_m" });
    expect(MODEL_REGISTRY.reconVehicle.validate({
      ...MODEL_REGISTRY.reconVehicle.createDefaultRequest(),
      route: { waypoints: [MODEL_REGISTRY.reconVehicle.createDefaultRequest().vehicle], sample_interval_m: 500 }
    })).toContainEqual({ path: "route.waypoints", message: "route.waypoints must contain at least two points when provided" });
    expect(MODEL_REGISTRY.mobility.validate({
      ...MODEL_REGISTRY.mobility.createDefaultRequest(),
      vehicles: {
        wheeled: { ...MODEL_REGISTRY.mobility.createDefaultRequest().vehicles.wheeled, enabled: false },
        tracked: { ...MODEL_REGISTRY.mobility.createDefaultRequest().vehicles.tracked, enabled: false }
      }
    })).toContainEqual({ path: "vehicles", message: "At least one vehicle type must be enabled" });
    expect(MODEL_REGISTRY.airCorridor.validate({
      ...MODEL_REGISTRY.airCorridor.createDefaultRequest(),
      aircraft: { ...MODEL_REGISTRY.airCorridor.createDefaultRequest().aircraft, min_agl_m: 3000, max_agl_m: 100 }
    })).toContainEqual({ path: "aircraft.max_agl_m", message: "min_agl_m must be less than max_agl_m" });
  });
});
