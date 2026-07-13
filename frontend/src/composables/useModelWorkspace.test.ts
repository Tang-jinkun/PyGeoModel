import { describe, expect, expectTypeOf, it } from "vitest";

import { getModelDefinition } from "../models/registry";
import { type ActiveDraft, useModelWorkspace } from "./useModelWorkspace";

describe("useModelWorkspace", () => {
  it("keeps a separate mutable draft for every model", () => {
    const workspace = useModelWorkspace();

    workspace.selectModel("uav");
    workspace.currentDraft.value.request.dem_id = "dem-a";
    workspace.selectModel("radar");

    expect(workspace.currentDraft.value.request.dem_id).toBe("");

    workspace.setDemForAll("dem-b");

    expect(workspace.drafts.uav.dem_id).toBe("dem-b");
    expect(workspace.drafts.radar.dem_id).toBe("dem-b");
  });

  it("pairs the writable current draft with its model and selects an assigned model", () => {
    const workspace = useModelWorkspace();
    const uavRequest = getModelDefinition("uav").createDefaultRequest();
    uavRequest.uav.altitude_m = 750;

    expectTypeOf(workspace.currentDraft.value).toEqualTypeOf<ActiveDraft>();
    workspace.currentDraft.value = { modelId: "uav", request: uavRequest };

    expect(workspace.selectedModel.value).toBe("uav");
    expect(workspace.currentDraft.value.modelId).toBe("uav");
    expect(workspace.drafts.uav).not.toBe(uavRequest);
    expect(workspace.drafts.uav.uav.altitude_m).toBe(750);
  });

  it("deep-clones a restored task request before assigning it to a draft", () => {
    const workspace = useModelWorkspace();
    const restored = getModelDefinition("uav").createDefaultRequest();
    restored.uav.altitude_m = 750;

    workspace.restoreRequest("uav", restored);
    workspace.drafts.uav.uav.altitude_m = 900;

    expect(workspace.drafts.uav).not.toBe(restored);
    expect(workspace.drafts.uav.uav).not.toBe(restored.uav);
    expect(restored.uav.altitude_m).toBe(750);
  });

  it("rejects uncorrelated model and request pairs at compile time", () => {
    const radarRequest = getModelDefinition("radar").createDefaultRequest();

    if (false) {
      // @ts-expect-error A radar request cannot be assigned to the UAV draft variant.
      const invalidDraft: ActiveDraft = { modelId: "uav", request: radarRequest };
      void invalidDraft;
    }

    expect(radarRequest.dem_id).toBe("");
  });
});
