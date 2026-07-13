import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import { artilleryDefinition } from "../../models/artillery/definition";
import { radarDefinition } from "../../models/radar/definition";
import { watchpostDefinition } from "../../models/watchpost/definition";
import ArtilleryForm from "./ArtilleryForm.vue";
import ModelParameterPanel from "./ModelParameterPanel.vue";
import RadarForm from "./RadarForm.vue";
import WatchpostForm from "./WatchpostForm.vue";

const radarFields = [
  "dem-id", "longitude", "latitude", "radar-height", "target-height",
  "max-range", "scan-mode", "use-curvature", "curvature-coeff",
  "simplify-tolerance", "voxel-grid-size", "voxel-vertical-levels", "voxel-max-height",
  "min-elevation", "max-elevation", "vertical-beam-width", "visual-dome-mode", "height-layers",
  "frequency", "transmit-power", "antenna-gain", "receiver-sensitivity", "target-rcs",
  "system-loss", "pulse-width", "prf", "noise-figure", "detection-probability",
  "false-alarm-probability"
];

const watchpostFields = [
  "dem-id", "longitude", "latitude", "observer-height", "target-height",
  "max-range", "scan-mode", "azimuth", "view-angle", "use-curvature", "curvature-coeff",
  "simplify-tolerance"
];

const artilleryFields = [
  "dem-id", "longitude", "latitude", "battery-height", "altitude-mode",
  "target-height", "min-range", "max-range", "azimuth", "traverse", "muzzle-velocity",
  "elevation", "munition-type", "lethal-radius", "effective-radius", "use-dem-elevation",
  "use-terrain-masking", "sample-resolution", "trajectory-samples", "clearance-margin",
  "simplify-tolerance"
];

function expectFields(wrapper: ReturnType<typeof mount>, fields: string[]) {
  for (const field of fields) {
    expect(wrapper.find(`[data-field="${field}"]`).exists(), `missing data-field=${field}`).toBe(true);
  }
}

describe("point model parameter forms", () => {
  it("renders every radar request field and only shows sector controls in sector mode", async () => {
    const request = radarDefinition.createDefaultRequest();
    const wrapper = mount(RadarForm, { props: { modelValue: request } });

    expectFields(wrapper, radarFields);
    expect(wrapper.find('[data-field="azimuth"]').exists()).toBe(false);
    expect(wrapper.find('[data-field="beam-width"]').exists()).toBe(false);

    await wrapper.get('[data-field="scan-mode"] input[value="sector"]').setValue(true);
    const update = wrapper.emitted("update:modelValue")?.at(-1)?.[0] as typeof request;
    expect(update).toMatchObject({ coverage: { scan_mode: "sector" } });
    expect(request.coverage.scan_mode).toBe("omni");

    await wrapper.setProps({ modelValue: update });
    expect(wrapper.get('[data-field="azimuth"]').isVisible()).toBe(true);
    expect(wrapper.get('[data-field="beam-width"]').isVisible()).toBe(true);
  });

  it("renders every watchpost field and owns controlled edits and map activation", async () => {
    const request = watchpostDefinition.createDefaultRequest();
    const wrapper = mount(WatchpostForm, { props: { modelValue: request } });

    expectFields(wrapper, watchpostFields);
    await wrapper.get('[data-field="max-range"] input').setValue(7500);
    await wrapper.get('[data-action="activate-map-tool"]').trigger("click");

    expect(wrapper.emitted("update:modelValue")?.at(-1)?.[0]).toMatchObject({ coverage: { max_range_m: 7500 } });
    expect(request.coverage.max_range_m).toBe(5000);
    expect(wrapper.emitted("activate-map-tool")).toHaveLength(1);
    expect(wrapper.find('[data-action="submit"]').exists()).toBe(false);
  });

  it("renders every artillery request field and emits immutable controlled edits", async () => {
    const request = artilleryDefinition.createDefaultRequest();
    const wrapper = mount(ArtilleryForm, { props: { modelValue: request } });

    expectFields(wrapper, artilleryFields);
    await wrapper.get('[data-field="munition-type"] input[value="smoke"]').setValue(true);

    expect(wrapper.emitted("update:modelValue")?.at(-1)?.[0]).toMatchObject({ munition: { munition_type: "smoke" } });
    expect(request.munition.munition_type).toBe("he");
    expect(wrapper.find('[data-action="submit"]').exists()).toBe(false);
  });
});

describe("ModelParameterPanel", () => {
  it("owns one fixed submit footer and forwards map activation", async () => {
    const wrapper = mount(ModelParameterPanel, {
      props: { modelId: "radar", modelValue: radarDefinition.createDefaultRequest() }
    });

    expect(wrapper.findAll('[data-action="submit"]')).toHaveLength(1);
    await wrapper.get('[data-action="activate-map-tool"]').trigger("click");
    expect(wrapper.emitted("activate-map-tool")).toHaveLength(1);
  });

  it("shows the watchpost positive-range issue and blocks submit", async () => {
    const request = watchpostDefinition.createDefaultRequest();
    request.coverage.max_range_m = 0;
    const wrapper = mount(ModelParameterPanel, {
      props: { modelId: "watchpost", modelValue: request }
    });

    await wrapper.get('[data-action="submit"]').trigger("click");

    expect(wrapper.text()).toContain("最大探测距离必须大于 0 米");
    expect(wrapper.emitted("submit")).toBeUndefined();
  });

  it("shows the artillery range-order issue and blocks submit", async () => {
    const request = artilleryDefinition.createDefaultRequest();
    request.weapon.min_range_m = 20_000;
    request.weapon.max_range_m = 15_000;
    const wrapper = mount(ModelParameterPanel, {
      props: { modelId: "artillery", modelValue: request }
    });

    await wrapper.get('[data-action="submit"]').trigger("click");

    expect(wrapper.text()).toContain("最小射程必须小于最大射程");
    expect(wrapper.emitted("submit")).toBeUndefined();
  });

  it("emits submit only after the active definition validates successfully", async () => {
    const request = radarDefinition.createDefaultRequest();
    const wrapper = mount(ModelParameterPanel, {
      props: { modelId: "radar", modelValue: request }
    });

    await wrapper.get('[data-action="submit"]').trigger("click");

    expect(wrapper.emitted("submit")).toEqual([[request]]);
    expect(wrapper.find('[data-validation-issues]').exists()).toBe(false);
  });
});
