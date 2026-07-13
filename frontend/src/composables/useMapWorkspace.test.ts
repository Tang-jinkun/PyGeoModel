import { describe, expect, it, vi } from "vitest";

import { useMapWorkspace } from "./useMapWorkspace";

describe("useMapWorkspace", () => {
  it("provides immutable point and waypoint commands with undo and clear", () => {
    const workspace = useMapWorkspace("point-or-route");
    const first: [number, number] = [79.8, 31.4];
    workspace.pickPoint(first);
    first[0] = 0;
    workspace.appendWaypoint([79.9, 31.5]);
    workspace.moveWaypoint(1, [80, 32]);

    expect(workspace.draft.value.points).toEqual([[79.8, 31.4], [80, 32]]);
    workspace.removeWaypoint(0);
    workspace.undo();
    expect(workspace.draft.value.points).toHaveLength(2);
    workspace.clear();
    expect(workspace.draft.value.points).toHaveLength(0);
  });

  it("focuses GeoJSON bounds through the supplied map", () => {
    const workspace = useMapWorkspace("point");
    const fitBounds = vi.fn();
    const focused = workspace.focusBounds({ fitBounds } as never, {
      type: "Point",
      coordinates: [79.8, 31.4]
    });

    expect(focused).toBe(true);
    expect(fitBounds).toHaveBeenCalledOnce();
  });
});
