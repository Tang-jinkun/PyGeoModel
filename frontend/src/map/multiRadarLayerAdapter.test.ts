import { describe, expect, it, vi } from "vitest";

import { createMultiRadarLayerAdapter } from "./multiRadarLayerAdapter";

describe("multi-radar layer adapter", () => {
  it("evicts the oldest detailed station after five selections", () => {
    const removeDetail = vi.fn();
    const adapter = createMultiRadarLayerAdapter({ removeDetail, maxDetailedSelections: 5 });

    ["a", "b", "c", "d", "e", "f"].forEach((id) => adapter.selectStationDetail(id));

    expect(removeDetail).toHaveBeenCalledWith("a");
    expect(adapter.selectedStationIds()).toEqual(["b", "c", "d", "e", "f"]);
  });
});
