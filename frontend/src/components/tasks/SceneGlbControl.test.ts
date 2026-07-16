import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import type { SceneGlbOverlayState } from "../../composables/useMapWorkspace";
import type { OutputFile } from "../../models/shared";
import SceneGlbControl from "./SceneGlbControl.vue";

const file: OutputFile = {
  kind: "scene_glb",
  label: "Air Corridor 3D Result GLB",
  url: "/outputs/air_corridor_result.glb",
  download_url: "/api/air-corridor/task/outputs/scene_glb",
  filename: "air_corridor_result.glb",
  media_type: "model/gltf-binary",
  size_bytes: 1_980_764,
  exists: true
};

const idleState: SceneGlbOverlayState = {
  taskId: "air_corridor_task_20260714_133725_314ec4c4",
  modelId: "airCorridor",
  demId: "dem-a",
  status: "idle",
  visible: false,
  progress: null,
  error: null
};

describe("SceneGlbControl", () => {
  it("starts off and requests a manual load", async () => {
    const wrapper = mount(SceneGlbControl, { props: { file, state: idleState } });

    expect(wrapper.get('[data-scene-glb-toggle] input[role="switch"]')
      .attributes("aria-checked")).toBe("false");
    expect(wrapper.text()).toContain("三维结果 · Air Corridor Planning");
    expect(wrapper.text()).toContain("任务 314ec4c4 · 未加载");
    expect(wrapper.get('[data-scene-glb-row]').attributes("title")).toContain(idleState.taskId);
    await wrapper.get('[data-scene-glb-toggle] input[role="switch"]').trigger("click");
    expect(wrapper.emitted("visibility")?.[0]).toEqual([true]);
  });

  it("shows byte progress and lets a loading request be cancelled", async () => {
    const wrapper = mount(SceneGlbControl, {
      props: {
        file,
        state: {
          ...idleState,
          status: "loading",
          visible: true,
          progress: { loaded: 7_500_000, total: 15_000_000 }
        }
      }
    });

    expect(wrapper.text()).toContain("正在加载 50%");
    expect(wrapper.get('[data-scene-glb-toggle] input[role="switch"]')
      .attributes("aria-checked")).toBe("true");
    await wrapper.get('[data-scene-glb-toggle] input[role="switch"]').trigger("click");
    expect(wrapper.emitted("visibility")?.[0]).toEqual([false]);
  });

  it("enables focus only for a visible result", async () => {
    const wrapper = mount(SceneGlbControl, {
      props: {
        file,
        state: { ...idleState, status: "visible", visible: true }
      }
    });

    expect(wrapper.text()).toContain("已叠加到地形");
    expect(wrapper.get('[data-scene-glb-focus]').attributes("disabled")).toBeUndefined();
    await wrapper.get('[data-scene-glb-focus]').trigger("click");
    expect(wrapper.emitted("focus")).toHaveLength(1);
  });

  it("shows an error and allows retry", async () => {
    const wrapper = mount(SceneGlbControl, {
      props: {
        file,
        state: {
          ...idleState,
          status: "error",
          error: "GLB metadata is invalid"
        }
      }
    });

    expect(wrapper.text()).toContain("GLB metadata is invalid");
    await wrapper.get('[data-scene-glb-toggle] input[role="switch"]').trigger("click");
    expect(wrapper.emitted("visibility")?.[0]).toEqual([true]);
  });

  it("disables previews above 50 MB", () => {
    const wrapper = mount(SceneGlbControl, {
      props: {
        file: { ...file, size_bytes: 50_000_001 },
        state: idleState
      }
    });

    expect(wrapper.text()).toContain("文件超过预览上限");
    expect(wrapper.get('[data-scene-glb-toggle] input[role="switch"]')
      .attributes("disabled")).toBeDefined();
  });
});
