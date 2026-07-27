import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import type { SceneGlbOverlayState } from "../../composables/useMapWorkspace";
import type { OutputFile } from "../../models/shared";
import WorkbenchDock from "./WorkbenchDock.vue";

describe("WorkbenchDock", () => {
  it("filters registered models and controls GLB visibility with native workbench rows", async () => {
    const wrapper = mount(WorkbenchDock, {
      props: {
        modelValue: "radar",
        sceneEntries: [{ kind: "scene_glb", file: sceneFile(), state: readyScene() }]
      }
    });

    await wrapper.get('input[aria-label="Search analysis models"]').setValue("radar");
    expect(wrapper.findAll('[data-model-id]').map((node) => node.attributes("data-model-id"))).toEqual(["radar"]);

    await wrapper.get('[data-dock-tab="layers"]').trigger("click");
    await wrapper.get('[data-layer-kind="scene_glb"] input[type="checkbox"]').setValue(false);

    expect(wrapper.emitted("update-scene-glb")?.[0]).toEqual(["scene_glb", false]);
    expect(wrapper.find(".scene-glb-row").exists()).toBe(false);
  });

  it("emits model selection and renders a supplied real data pane", async () => {
    const wrapper = mount(WorkbenchDock, {
      props: { modelValue: "radar" },
      slots: { data: "active DEM content" }
    });

    await wrapper.get('[data-model-id="mobility"]').trigger("click");
    expect(wrapper.emitted("select-model")?.[0]).toEqual(["mobility"]);

    await wrapper.get('[data-dock-tab="data"]').trigger("click");
    expect(wrapper.text()).toContain("active DEM content");
  });

  it("does not render the deprecated radar-scene folder after an analysis", async () => {
    const wrapper = mount(WorkbenchDock, { props: { modelValue: "radar" } });

    await wrapper.get('[data-dock-tab="layers"]').trigger("click");
    expect(wrapper.text()).not.toContain("雷达场景");
    expect(wrapper.find('[data-layer-kind="volume"]').exists()).toBe(false);
  });
});

function sceneFile(): OutputFile {
  return {
    kind: "scene_glb",
    label: "Radar scene 3D Result GLB",
    filename: "scene.glb",
    media_type: "model/gltf-binary",
    required: false,
    exists: true,
    download_path: "/api/radar/coverage/task-1/outputs/scene_glb"
  };
}

function readyScene(): SceneGlbOverlayState {
  return {
    taskId: "task-1",
    modelId: "radar",
    demId: "dem-1",
    status: "visible",
    visible: true,
    progress: null,
    error: null
  };
}
