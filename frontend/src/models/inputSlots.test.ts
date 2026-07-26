import { describe, expect, it } from "vitest";
import { reactive } from "vue";

import {
  applyInputSelections,
  createInputSelections,
  terrainInputSlot
} from "./inputSlots";
import { getModelDefinition } from "./registry";

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

  it("returns a cloneable request when given Vue-reactive model data", () => {
    const request = reactive(getModelDefinition("radar").createDefaultRequest());

    const result = applyInputSelections(request, { terrain: ["dem-42"] });

    expect(() => structuredClone(result)).not.toThrow();
    expect(result.dem_id).toBe("dem-42");
  });
});
