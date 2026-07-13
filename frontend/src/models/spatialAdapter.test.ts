import { describe, expect, it } from "vitest";

import { reduceSpatialDraft } from "../map/spatialInput";
import { getModelDefinition, type ModelId } from "./registry";
import { applySpatialDraftToRequest, spatialDraftFromRequest } from "./spatialAdapter";

describe("spatialAdapter", () => {
  it.each([
    ["radar", "radar"],
    ["watchpost", "observer"],
    ["artillery", "battery"]
  ] as const)("writes a picked point into the %s request", (modelId, field) => {
    const request = getModelDefinition(modelId).createDefaultRequest();
    const draft = reduceSpatialDraft(spatialDraftFromRequest(modelId, request), {
      type: "set-point",
      coordinate: [88.1, 32.2]
    });

    const updated = applySpatialDraftToRequest(modelId, request, draft) as unknown as Record<
      string,
      { lon: number; lat: number }
    >;
    expect(updated[field]).toMatchObject({ lon: 88.1, lat: 32.2 });
  });

  it.each(["uav", "reconVehicle"] as const)("preserves platform fields while writing a %s route", (modelId) => {
    const request = getModelDefinition(modelId).createDefaultRequest();
    let draft = spatialDraftFromRequest(modelId, request);
    const origin = draft.points[0];
    draft = reduceSpatialDraft(draft, { type: "append", coordinate: [80, 31] });
    draft = reduceSpatialDraft(draft, { type: "append", coordinate: [81, 32] });

    const updated = applySpatialDraftToRequest(modelId, request, draft) as unknown as {
      route: { waypoints: Array<{ lon: number; lat: number }> };
    };
    expect(updated.route.waypoints.map(({ lon, lat }) => [lon, lat])).toEqual([
      origin,
      [80, 31],
      [81, 32]
    ]);
  });

  it("writes mobility start and end points", () => {
    const request = getModelDefinition("mobility").createDefaultRequest();
    let draft = spatialDraftFromRequest("mobility", request);
    draft = reduceSpatialDraft(draft, { type: "set-start", coordinate: [78, 30] });
    draft = reduceSpatialDraft(draft, { type: "set-end", coordinate: [82, 34] });

    const updated = applySpatialDraftToRequest("mobility", request, draft);
    expect(updated.start).toEqual({ lon: 78, lat: 30 });
    expect(updated.end).toEqual({ lon: 82, lat: 34 });
  });

  it("preserves air threat identity and parameters while moving it", () => {
    const request = getModelDefinition("airCorridor").createDefaultRequest();
    request.threats = [{
      id: "threat-1",
      name: "SAM",
      lon: 79,
      lat: 31,
      min_range_m: 1000,
      max_range_m: 20_000,
      min_altitude_m: 100,
      max_altitude_m: 8000,
      threat_level: 4,
      kill_zone_radius_m: 5000,
      warning_zone_radius_m: 8000
    }];
    let draft = spatialDraftFromRequest("airCorridor", request);
    draft = reduceSpatialDraft(draft, {
      type: "update-threat",
      id: "threat-1",
      coordinate: [80, 32]
    });

    const updated = applySpatialDraftToRequest("airCorridor", request, draft);
    expect(updated.threats[0]).toEqual({ ...request.threats[0], lon: 80, lat: 32 });
  });

  it("clears optional routes and threats while preserving required anchors", () => {
    const uavRequest = getModelDefinition("uav").createDefaultRequest();
    uavRequest.route = {
      sample_interval_m: 100,
      waypoints: [
        { ...uavRequest.uav },
        { ...uavRequest.uav, lon: uavRequest.uav.lon + 1 }
      ]
    };
    const clearedUav = applySpatialDraftToRequest(
      "uav",
      uavRequest,
      reduceSpatialDraft(spatialDraftFromRequest("uav", uavRequest), { type: "clear" })
    );
    expect(clearedUav.route).toBeNull();
    expect([clearedUav.uav.lon, clearedUav.uav.lat]).toEqual([uavRequest.uav.lon, uavRequest.uav.lat]);

    const corridorRequest = getModelDefinition("airCorridor").createDefaultRequest();
    corridorRequest.threats = [{
      id: "threat-1", name: null, lon: 79, lat: 31, min_range_m: 0, max_range_m: 5000,
      min_altitude_m: 0, max_altitude_m: 3000, threat_level: 1,
      kill_zone_radius_m: null, warning_zone_radius_m: null
    }];
    const clearedCorridor = applySpatialDraftToRequest(
      "airCorridor",
      corridorRequest,
      reduceSpatialDraft(spatialDraftFromRequest("airCorridor", corridorRequest), { type: "clear" })
    );
    expect(clearedCorridor.threats).toEqual([]);
    expect(clearedCorridor.start).toEqual(corridorRequest.start);
    expect(clearedCorridor.end).toEqual(corridorRequest.end);
  });

  it("creates the registered spatial kind for every model", () => {
    const modelIds: ModelId[] = ["radar", "uav", "watchpost", "artillery", "reconVehicle", "mobility", "airCorridor"];
    for (const modelId of modelIds) {
      expect(spatialDraftFromRequest(modelId, getModelDefinition(modelId).createDefaultRequest()).kind)
        .toBe(getModelDefinition(modelId).spatialInput);
    }
  });
});
