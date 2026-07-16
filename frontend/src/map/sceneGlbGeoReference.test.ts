import { describe, expect, it } from "vitest";
import proj4 from "proj4";

import {
  createSceneGeoReference,
  validateScene3dMetadata
} from "./sceneGlbGeoReference";

const north = {
  schema_version: 1,
  task_id: "air_corridor_task_a",
  model_id: "air_corridor",
  units: "metre",
  source_crs: "EPSG:32644",
  geographic_crs: "EPSG:4326",
  origin: {
    projected_x: 335974.7457902762,
    projected_y: 3486028.840193924,
    longitude: 79.27293573113577,
    latitude: 31.497477067232186,
    altitude_amsl_m: 5000
  },
  axes: { x: "east", y: "up", z: "south" }
};

describe("scene GLB georeference", () => {
  it("validates the exact version-one coordinate contract", () => {
    expect(validateScene3dMetadata(north, {
      taskId: "air_corridor_task_a",
      modelId: "air_corridor"
    })).toEqual(north);
    expect(() => validateScene3dMetadata({ ...north, units: "foot" }))
      .toThrow("metre");
    expect(() => validateScene3dMetadata({
      ...north,
      axes: { x: "east", y: "north", z: "up" }
    })).toThrow("axes");
    expect(() => validateScene3dMetadata({ ...north, source_crs: "EPSG:3857" }))
      .toThrow("UTM");
  });

  it("reconstructs projected and AMSL coordinates with Z pointing south", () => {
    const reference = createSceneGeoReference(validateScene3dMetadata(north));
    const result = reference.project([1000, 250, -2000]);

    expect(result.projected).toEqual([336974.7457902762, 3488028.840193924]);
    expect(result.altitudeAmslM).toBe(5250);
    expect(result.longitude).toBeCloseTo(79.283, 2);
    expect(result.latitude).toBeCloseTo(31.516, 2);
    expect(result.mercator.every(Number.isFinite)).toBe(true);
  });

  it("supports southern-hemisphere WGS84 UTM zones", () => {
    const south = {
      ...north,
      source_crs: "EPSG:32756",
      origin: {
        projected_x: 333491.22992739105,
        projected_y: 6251909.2060468495,
        longitude: 151.2,
        latitude: -33.86,
        altitude_amsl_m: 0
      }
    };
    const result = createSceneGeoReference(validateScene3dMetadata(south))
      .project([0, 100, 0]);

    expect(result.longitude).toBeCloseTo(151.2, 2);
    expect(result.latitude).toBeCloseTo(-33.86, 2);
    expect(result.altitudeAmslM).toBe(100);
  });

  it.each([
    { zone: 60, originLongitude: 179.9, vertexLongitude: -179.9, expected: 180.1 },
    { zone: 1, originLongitude: -179.9, vertexLongitude: 179.9, expected: -180.1 }
  ])(
    "unwraps zone $zone Mercator x and longitude to the anchor world copy",
    ({ zone, originLongitude, vertexLongitude, expected }) => {
      const definition = utmDefinition(zone);
      const forward = proj4("EPSG:4326", definition);
      const [originX, originY] = forward.forward([originLongitude, 10]);
      const [vertexX, vertexY] = forward.forward([vertexLongitude, 10]);
      const reference = createSceneGeoReference(validateScene3dMetadata({
        ...north,
        source_crs: `EPSG:326${String(zone).padStart(2, "0")}`,
        origin: {
          projected_x: originX,
          projected_y: originY,
          longitude: originLongitude,
          latitude: 10,
          altitude_amsl_m: 0
        }
      }));

      const result = reference.project([
        vertexX - originX,
        0,
        -(vertexY - originY)
      ]);

      expect(result.longitude).toBeCloseTo(expected, 6);
      expect(Math.abs(result.mercator[0])).toBeLessThan(0.01);
    }
  );
});

function utmDefinition(zone: number) {
  return `+proj=utm +zone=${zone} +datum=WGS84 +units=m +no_defs`;
}
