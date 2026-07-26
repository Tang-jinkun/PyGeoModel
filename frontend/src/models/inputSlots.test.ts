import { describe, expect, it } from "vitest";

import {
  applyInputSelections,
  createInputSelections,
  terrainInputSlot
} from "./inputSlots";

describe("model input slots", () => {
  it("bridges the explicit terrain selection into the existing dem_id field", () => {
    const inputs = createInputSelections([terrainInputSlot]);
    inputs.terrain = ["dem-42"];

    expect(applyInputSelections({ dem_id: "" }, inputs)).toEqual({ dem_id: "dem-42" });
  });

  it("keeps a single-valued terrain slot to its first selected asset", () => {
    const inputs = createInputSelections([terrainInputSlot]);
    inputs.terrain = ["dem-42", "dem-99"];

    expect(applyInputSelections({ dem_id: "" }, inputs)).toEqual({ dem_id: "dem-42" });
  });
});
