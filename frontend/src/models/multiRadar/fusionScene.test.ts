import { describe, expect, it } from "vitest";

import { createFusionSceneTask } from "./fusionScene";

describe("multi-radar fusion scene", () => {
  it("uses the live fusion descriptor without constructing a raw output URL", () => {
    const file = {
      kind: "fusion_scene_glb",
      label: "Fusion scene",
      filename: "fusion_scene.glb",
      media_type: "model/gltf-binary",
      required: false,
      exists: true,
      download_path: "/api/radar/multi-coverage/multi_task_a/outputs/fusion_scene_glb"
    };
    const task = createFusionSceneTask("multi_task_a", "dem_a", file);

    expect(task.task_id).toBe("multi_task_a--fusion");
    expect(task.output_files[0].kind).toBe("scene_glb");
    expect(task.output_files[0].download_path).toBe(file.download_path);
  });
});
