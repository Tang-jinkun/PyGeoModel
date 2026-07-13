import { describe, expect, it } from "vitest";

import {
  createSpatialDraft,
  reduceSpatialDraft,
  spatialDraftToGeoJson,
  type SpatialThreat
} from "./spatialInput";

describe("spatial input", () => {
  it("supports ordered route edits and undo", () => {
    let state = createSpatialDraft("point-or-route");
    state = reduceSpatialDraft(state, { type: "append", coordinate: [79.8, 31.4] });
    state = reduceSpatialDraft(state, { type: "append", coordinate: [79.9, 31.5] });

    expect(spatialDraftToGeoJson(state).features[0]?.geometry.type).toBe("LineString");
    state = reduceSpatialDraft(state, { type: "undo" });

    expect(state.points).toEqual([[79.8, 31.4]]);
  });

  it("supports moving and removing waypoints without mutating prior states", () => {
    const initial = reduceSpatialDraft(
      reduceSpatialDraft(createSpatialDraft("point-or-route"), { type: "append", coordinate: [10, 20] }),
      { type: "append", coordinate: [30, 40] }
    );
    const moved = reduceSpatialDraft(initial, { type: "move", index: 0, coordinate: [11, 21] });
    const removed = reduceSpatialDraft(moved, { type: "remove", index: 1 });

    expect(initial.points).toEqual([[10, 20], [30, 40]]);
    expect(moved.points).toEqual([[11, 21], [30, 40]]);
    expect(removed.points).toEqual([[11, 21]]);
  });

  it("stores a single point and protects it from caller mutation", () => {
    const coordinate: [number, number] = [79.8, 31.4];
    const state = reduceSpatialDraft(createSpatialDraft("point"), { type: "set-point", coordinate });
    coordinate[0] = 0;

    const collection = spatialDraftToGeoJson(state);
    (collection.features[0]?.geometry as GeoJSON.Point).coordinates[0] = 1;

    expect(state.points).toEqual([[79.8, 31.4]]);
  });

  it("serializes start, end, and threats as normalized point features", () => {
    const threat: SpatialThreat = {
      id: "threat-1",
      coordinate: [80, 32],
      properties: { name: "Alpha" }
    };
    let state = createSpatialDraft("start-end-threats");
    state = reduceSpatialDraft(state, { type: "set-start", coordinate: [79.8, 31.4] });
    state = reduceSpatialDraft(state, { type: "set-end", coordinate: [79.9, 31.5] });
    state = reduceSpatialDraft(state, { type: "add-threat", threat });
    threat.coordinate[0] = 0;
    state = reduceSpatialDraft(state, {
      type: "update-threat",
      id: "threat-1",
      coordinate: [80.1, 32.1],
      properties: { name: "Bravo" }
    });

    expect(spatialDraftToGeoJson(state).features).toEqual([
      expect.objectContaining({ properties: expect.objectContaining({ kind: "start" }) }),
      expect.objectContaining({ properties: expect.objectContaining({ kind: "end" }) }),
      expect.objectContaining({
        properties: expect.objectContaining({ kind: "threat", id: "threat-1", name: "Bravo" }),
        geometry: { type: "Point", coordinates: [80.1, 32.1] }
      })
    ]);

    const removed = reduceSpatialDraft(state, { type: "remove-threat", id: "threat-1" });
    expect(removed.threats).toHaveLength(0);
    expect(reduceSpatialDraft(removed, { type: "undo" }).threats).toHaveLength(1);
  });

  it.each([
    ["longitude below minimum", [-180.1, 0]],
    ["longitude above maximum", [180.1, 0]],
    ["latitude below minimum", [0, -90.1]],
    ["latitude above maximum", [0, 90.1]],
    ["non-finite longitude", [Number.NaN, 0]]
  ])("rejects %s", (_label, coordinate) => {
    expect(() => reduceSpatialDraft(createSpatialDraft("point"), {
      type: "set-point",
      coordinate: coordinate as [number, number]
    })).toThrow(RangeError);
  });

  it("clears the active draft and allows undoing the clear", () => {
    const populated = reduceSpatialDraft(createSpatialDraft("start-end"), {
      type: "set-start",
      coordinate: [79.8, 31.4]
    });
    const cleared = reduceSpatialDraft(populated, { type: "clear" });

    expect(cleared.start).toBeNull();
    expect(reduceSpatialDraft(cleared, { type: "undo" }).start).toEqual([79.8, 31.4]);
  });
});
