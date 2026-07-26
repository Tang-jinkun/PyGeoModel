import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import type { SceneGlbOverlayState } from "../../composables/useMapWorkspace";
import type { OutputFile } from "../../models/shared";
import SceneGlbControl from "../tasks/SceneGlbControl.vue";
import WorkbenchDock from "./WorkbenchDock.vue";

describe("WorkbenchDock", () => {
  it("filters registered models and delegates GLB visibility from the Layers tab", async () => {
    const wrapper = mount(WorkbenchDock, {
      props: {
        modelValue: "radar",
        sceneEntries: [{ kind: "scene_glb", file: sceneFile(), state: readyScene() }]
      }
    });

    await wrapper.get('input[aria-label="Search analysis models"]').setValue("radar");
    expect(wrapper.findAll('[data-model-id]').map((node) => node.attributes("data-model-id"))).toEqual(["radar"]);

    await wrapper.get('[data-dock-tab="layers"]').trigger("click");
    wrapper.getComponent(SceneGlbControl).vm.$emit("visibility", false);
    await wrapper.vm.$nextTick();

    expect(wrapper.emitted("update-scene-glb")?.[0]).toEqual(["scene_glb", false]);
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
});

function sceneFile(): OutputFile {
  return {
    kind: "scene_glb",
    label: "Radar scene 3D Result GLB",
    url: "/scene.glb",
    download_url: "/scene.glb",
    filename: "scene.glb",
    media_type: "model/gltf-binary",
    exists: true
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
