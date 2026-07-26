import { describe, expect, it } from "vitest";

import { createFusionSceneTask } from "./fusionScene";

describe("multi-radar fusion scene", () => {
  it("creates an independent scene asset for the fusion GLB", () => {
    const task = createFusionSceneTask("multi_task_a", "dem_a", "/outputs/multi_task_a/fusion_scene.glb");

    expect(task.task_id).toBe("multi_task_a--fusion");
    expect(task.output_files[0].kind).toBe("scene_glb");
    expect(task.output_files[0].url).toContain("fusion_scene.glb");
  });
});
