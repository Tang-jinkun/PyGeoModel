import { toRaw } from "vue";

export type AssetType = "dem" | "vector" | "table" | "route";

export interface InputSlotDefinition {
  key: string;
  label: string;
  assetTypes: readonly AssetType[];
  required: boolean;
  multiple: boolean;
}

export type ModelInputSelections = Record<string, string[]>;

export const terrainInputSlot: InputSlotDefinition = {
  key: "terrain",
  label: "Terrain DEM",
  assetTypes: ["dem"],
  required: true,
  multiple: false
};

export function createInputSelections(slots: readonly InputSlotDefinition[]): ModelInputSelections {
  return Object.fromEntries(slots.map((slot) => [slot.key, []]));
}

export function applyInputSelections<Request extends { dem_id: string }>(
  request: Request,
  selections: ModelInputSelections
): Request {
  return {
    ...structuredClone(toRaw(request)),
    dem_id: selections.terrain?.[0] ?? ""
  };
}
