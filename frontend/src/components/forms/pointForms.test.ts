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

function collectObjectReferences(value: unknown, references = new Set<object>()) {
  if (typeof value !== "object" || value === null || references.has(value)) return references;
  references.add(value);
  for (const child of Object.values(value)) collectObjectReferences(child, references);
  return references;
}

function expectNoSharedReferences(actual: object, source: object) {
  const sourceReferences = collectObjectReferences(source);
  for (const reference of collectObjectReferences(actual)) {
    expect(sourceReferences.has(reference)).toBe(false);
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

  it("parses radar height layers from commas, spaces, and Chinese commas", async () => {
    const request = radarDefinition.createDefaultRequest();
    const wrapper = mount(RadarForm, { props: { modelValue: request } });

    await wrapper.get('[data-field="height-layers"]').setValue("100, 500，900 1200");

    expect(wrapper.emitted("update:modelValue")?.at(-1)?.[0]).toMatchObject({
      advanced: expect.objectContaining({ height_layers_m: [100, 500, 900, 1200] })
    });
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

  it("deeply isolates every radar update from its input and sibling branches", async () => {
    const request = radarDefinition.createDefaultRequest();
    const original = structuredClone(request);
    const wrapper = mount(RadarForm, { props: { modelValue: request } });

    await wrapper.get('[data-field="scan-mode"] input[value="sector"]').setValue(true);
    const update = wrapper.emitted("update:modelValue")?.at(-1)?.[0] as typeof request;

    expectNoSharedReferences(update, request);
    update.target.height_m = 250;
    update.advanced.height_layers_m.push(600);
    expect(update.coverage).toEqual({ ...original.coverage, scan_mode: "sector" });
    expect(request).toEqual(original);
  });

  it("deeply isolates every watchpost update from its input and sibling branches", async () => {
    const request = watchpostDefinition.createDefaultRequest();
    const original = structuredClone(request);
    const wrapper = mount(WatchpostForm, { props: { modelValue: request } });

    await wrapper.get('[data-field="max-range"] input').setValue(7500);
    const update = wrapper.emitted("update:modelValue")?.at(-1)?.[0] as typeof request;

    expectNoSharedReferences(update, request);
    update.target.height_m = 40;
    update.analysis.curvature_coeff = 0.5;
    expect(update.observer).toEqual(original.observer);
    expect(request).toEqual(original);
  });

  it("deeply isolates every artillery update from its input and sibling branches", async () => {
    const request = artilleryDefinition.createDefaultRequest();
    const original = structuredClone(request);
    const wrapper = mount(ArtilleryForm, { props: { modelValue: request } });

    await wrapper.get('[data-field="munition-type"] input[value="smoke"]').setValue(true);
    const update = wrapper.emitted("update:modelValue")?.at(-1)?.[0] as typeof request;

    expectNoSharedReferences(update, request);
    update.weapon.max_range_m = 1;
    update.analysis.trajectory_samples = 2;
    expect(update.munition).toEqual({ ...original.munition, munition_type: "smoke" });
    expect(request).toEqual(original);
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

    const submitted = wrapper.emitted("submit")?.[0]?.[0] as typeof request;
    expect(submitted).toEqual(request);
    expectNoSharedReferences(submitted, request);
    submitted.target.height_m = 900;
    submitted.advanced.height_layers_m.push(1200);
    expect(request).toEqual(radarDefinition.createDefaultRequest());
    expect(wrapper.find('[data-validation-issues]').exists()).toBe(false);
  });

  it("deeply isolates child updates before forwarding them", async () => {
    const request = radarDefinition.createDefaultRequest();
    const original = structuredClone(request);
    const wrapper = mount(ModelParameterPanel, { props: { modelId: "radar", modelValue: request } });

    await wrapper.get('[data-field="max-range"] input').setValue(64000);
    const childUpdate = wrapper.findComponent(RadarForm).emitted("update:modelValue")?.at(-1)?.[0] as typeof request;
    const panelUpdate = wrapper.emitted("update:modelValue")?.at(-1)?.[0] as typeof request;

    expectNoSharedReferences(panelUpdate, request);
    expectNoSharedReferences(panelUpdate, childUpdate);
    panelUpdate.target.height_m = 100;
    panelUpdate.advanced.height_layers_m.push(800);
    expect(childUpdate.target).toEqual(original.target);
    expect(childUpdate.advanced.height_layers_m).toEqual(original.advanced.height_layers_m);
    expect(request).toEqual(original);
  });
});
