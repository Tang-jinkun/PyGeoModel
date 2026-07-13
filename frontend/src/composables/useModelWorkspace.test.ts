import { describe, expect, it } from "vitest";

import { getModelDefinition } from "../models/registry";
import { useModelWorkspace } from "./useModelWorkspace";

describe("useModelWorkspace", () => {
  it("keeps a separate mutable draft for every model", () => {
    const workspace = useModelWorkspace();

    workspace.selectModel("uav");
    workspace.currentDraft.value.dem_id = "dem-a";
    workspace.selectModel("radar");

    expect(workspace.currentDraft.value.dem_id).toBe("");

    workspace.setDemForAll("dem-b");

    expect(workspace.drafts.uav.dem_id).toBe("dem-b");
    expect(workspace.drafts.radar.dem_id).toBe("dem-b");
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
});
