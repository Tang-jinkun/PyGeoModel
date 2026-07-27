import { describe, expect, it } from "vitest";

import { createMultiRadarSceneTask } from "./sceneAssets";

describe("multi-radar scene assets", () => {
  it("converts a station asset into an independently loadable scene task", () => {
    const task = createMultiRadarSceneTask("dem-a", {
      asset_id: "coverage-r1:scene_glb",
      task_id: "coverage-r1",
      radar_id: "R1",
      kind: "scene_glb",
      label: "R1 - Radar Maximum Detection Domain GLB",
      render_tier: "world",
      file: {
        kind: "scene_glb",
        label: "Radar Maximum Detection Domain GLB",
        filename: "radar_detection_domain.glb",
        media_type: "model/gltf-binary",
        required: false,
        exists: true,
        download_path: "/api/radar/coverage/coverage-r1/outputs/scene_glb"
      }
    });

    expect(task).toMatchObject({
      task_id: "coverage-r1",
      dem_id: "dem-a",
      status: "finished",
      output_files: [expect.objectContaining({ kind: "scene_glb" })]
    });
  });
});
