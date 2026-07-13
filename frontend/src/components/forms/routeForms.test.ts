import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import type { Component } from "vue";

import { airCorridorDefinition } from "../../models/airCorridor/definition";
import { mobilityDefinition } from "../../models/mobility/definition";
import { reconVehicleDefinition } from "../../models/reconVehicle/definition";
import { MODEL_IDS, MODEL_REGISTRY } from "../../models/registry";
import { uavDefinition } from "../../models/uav/definition";
import AirCorridorForm from "./AirCorridorForm.vue";
import ArtilleryForm from "./ArtilleryForm.vue";
import MobilityForm from "./MobilityForm.vue";
import ModelParameterPanel from "./ModelParameterPanel.vue";
import RadarForm from "./RadarForm.vue";
import ReconVehicleForm from "./ReconVehicleForm.vue";
import UavForm from "./UavForm.vue";
import WatchpostForm from "./WatchpostForm.vue";

const uavFields = [
  "dem-id", "uav-altitude", "uav-altitude-mode",
  "uav-heading", "uav-pitch", "uav-roll", "route-enabled", "route-sample-interval",
  "sensor-type", "horizontal-fov", "vertical-fov", "sensor-max-range", "sensor-min-range",
  "ground-resolution", "target-height", "terrain-occlusion", "sample-resolution", "simplify-tolerance"
];

const reconFields = [
  "dem-id", "vehicle-heading", "mast-height",
  "route-enabled", "route-sample-interval", "sensor-type", "sensor-max-range", "sensor-min-range",
  "scan-mode", "view-angle", "target-height", "terrain-occlusion", "use-curvature",
  "curvature-coeff", "simplify-tolerance"
];

const mobilityFields = [
  "dem-id",
  "wheeled-enabled", "wheeled-base-speed", "wheeled-max-slope", "wheeled-slope-penalty",
  "wheeled-road-speed", "wheeled-offroad-speed", "tracked-enabled", "tracked-base-speed",
  "tracked-max-slope", "tracked-slope-penalty", "tracked-road-speed", "tracked-offroad-speed",
  "road-network-enabled", "allow-diagonal", "max-search-radius", "simplify-tolerance"
];

const airCorridorFields = [
  "dem-id", "start-altitude", "start-altitude-mode", "end-altitude", "end-altitude-mode", "cruise-speed",
  "min-agl", "max-agl", "max-climb-rate", "max-descent-rate", "altitude-layers",
  "corridor-width", "horizontal-resolution", "allow-altitude-change", "threat-weight",
  "distance-weight", "altitude-change-weight", "terrain-clearance-weight", "simplify-tolerance"
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
  for (const reference of collectObjectReferences(actual)) expect(sourceReferences.has(reference)).toBe(false);
}

describe("route and multi-point model forms", () => {
  it("binds every UAV field and preserves ordered waypoint metadata on coordinate edits", async () => {
    const request = uavDefinition.createDefaultRequest();
    request.route = {
      sample_interval_m: 75,
      waypoints: [
        { ...request.uav, lon: 80, lat: 30, altitude_m: 600, heading_deg: 15 },
        { ...request.uav, lon: 81, lat: 31, altitude_m: 700, heading_deg: 25 }
      ]
    };
    const original = structuredClone(request);
    const wrapper = mount(UavForm, { props: { modelValue: request } });

    expectFields(wrapper, uavFields);
    expect(wrapper.find('[data-coordinate="uav"] [data-field="longitude"]').exists()).toBe(true);
    expect(wrapper.find('[data-coordinate="uav"] [data-field="latitude"]').exists()).toBe(true);
    expect(wrapper.findAll("[data-waypoint]")).toHaveLength(2);
    await wrapper.get('[data-waypoint="0"] [data-field="longitude"]').setValue("82");
    const update = wrapper.emitted("update:modelValue")?.at(-1)?.[0] as typeof request;

    expect(update.route?.waypoints.map(({ lon }) => lon)).toEqual([82, 81]);
    expect(update.route?.waypoints[0]).toMatchObject({ altitude_m: 600, heading_deg: 15 });
    expect(update.route?.waypoints[1]).toEqual(original.route?.waypoints[1]);
    expectNoSharedReferences(update, request);
    expect(request).toEqual(original);
    expect(wrapper.find('[data-action="submit"]').exists()).toBe(false);
  });

  it("binds every recon field and reports a one-waypoint route through its model validator", () => {
    const request = reconVehicleDefinition.createDefaultRequest();
    request.route = { sample_interval_m: 50, waypoints: [{ ...request.vehicle }] };
    const wrapper = mount(ReconVehicleForm, { props: { modelValue: request } });

    expectFields(wrapper, reconFields);
    expect(wrapper.find('[data-coordinate="vehicle"] [data-field="longitude"]').exists()).toBe(true);
    expect(wrapper.find('[data-coordinate="vehicle"] [data-field="latitude"]').exists()).toBe(true);
    expect(wrapper.text()).toContain("航线至少包含两个航点");
    expect(wrapper.findAll("[data-waypoint]")).toHaveLength(1);
  });

  it("binds mobility inputs, owns start edits, and requires at least one vehicle type", async () => {
    const request = mobilityDefinition.createDefaultRequest();
    const original = structuredClone(request);
    const wrapper = mount(MobilityForm, { props: { modelValue: request } });

    expectFields(wrapper, mobilityFields);
    expect(wrapper.find('[data-coordinate="start"] [data-field="longitude"]').exists()).toBe(true);
    expect(wrapper.find('[data-coordinate="end"] [data-field="longitude"]').exists()).toBe(true);
    await wrapper.get('[data-coordinate="start"] [data-field="longitude"]').setValue("80.25");
    const coordinateUpdate = wrapper.emitted("update:modelValue")?.at(-1)?.[0] as typeof request;
    expect(coordinateUpdate.start).toEqual({ lon: 80.25, lat: request.start.lat });
    expectNoSharedReferences(coordinateUpdate, request);
    expect(request).toEqual(original);

    await wrapper.setProps({ modelValue: coordinateUpdate });
    await wrapper.get('[data-field="wheeled-enabled"]').setValue(false);
    const wheeledDisabled = wrapper.emitted("update:modelValue")?.at(-1)?.[0] as typeof request;
    await wrapper.setProps({ modelValue: wheeledDisabled });
    await wrapper.get('[data-field="tracked-enabled"]').setValue(false);
    const allDisabled = wrapper.emitted("update:modelValue")?.at(-1)?.[0] as typeof request;
    await wrapper.setProps({ modelValue: allDisabled });

    expect(wrapper.text()).toContain("至少启用一种车辆");
  });

  it("binds air-corridor inputs, preserves existing threat IDs, and generates IDs only for additions", async () => {
    const request = airCorridorDefinition.createDefaultRequest();
    request.threats = [{
      id: "existing-threat", name: "一号威胁", lon: 80, lat: 32, min_range_m: 100,
      max_range_m: 1000, min_altitude_m: 50, max_altitude_m: 2000, threat_level: 3,
      kill_zone_radius_m: 400, warning_zone_radius_m: 600
    }];
    const original = structuredClone(request);
    const uuid = vi.spyOn(globalThis.crypto, "randomUUID").mockReturnValue("11111111-1111-4111-8111-111111111111");
    const wrapper = mount(AirCorridorForm, { props: { modelValue: request } });

    expectFields(wrapper, airCorridorFields);
    expectFields(wrapper, [
      "threat-name-existing-threat", "threat-min-range-existing-threat", "threat-max-range-existing-threat",
      "threat-min-altitude-existing-threat", "threat-max-altitude-existing-threat",
      "threat-level-existing-threat", "threat-kill-radius-existing-threat", "threat-warning-radius-existing-threat"
    ]);
    await wrapper.get('[data-threat="existing-threat"] [data-field="longitude"]').setValue("81");
    const coordinateUpdate = wrapper.emitted("update:modelValue")?.at(-1)?.[0] as typeof request;
    expect(coordinateUpdate.threats[0]).toMatchObject({ id: "existing-threat", lon: 81, name: "一号威胁" });
    expectNoSharedReferences(coordinateUpdate, request);
    expect(request).toEqual(original);

    await wrapper.setProps({ modelValue: coordinateUpdate });
    await wrapper.get('[data-action="add-threat"]').trigger("click");
    const added = wrapper.emitted("update:modelValue")?.at(-1)?.[0] as typeof request;
    expect(added.threats.map(({ id }) => id)).toEqual(["existing-threat", "11111111-1111-4111-8111-111111111111"]);
    expect(uuid).toHaveBeenCalledTimes(1);
    uuid.mockRestore();
  });

  it("parses altitude layers from commas, spaces, and Chinese commas", async () => {
    const request = airCorridorDefinition.createDefaultRequest();
    const wrapper = mount(AirCorridorForm, { props: { modelValue: request } });

    await wrapper.get('[data-field="altitude-layers"]').setValue("300, 600，900 1200");

    expect(wrapper.emitted("update:modelValue")?.at(-1)?.[0]).toMatchObject({
      altitude_layers_m: [300, 600, 900, 1200]
    });
  });

  it("reports non-unique, non-ascending altitude layers and invalid threat bounds in Chinese", async () => {
    const request = airCorridorDefinition.createDefaultRequest();
    request.altitude_layers_m = [600, 300, 300];
    request.threats = [{
      id: "t-1", name: null, lon: 80, lat: 32, min_range_m: 1000, max_range_m: 500,
      min_altitude_m: 2000, max_altitude_m: 1000, threat_level: 5,
      kill_zone_radius_m: 700, warning_zone_radius_m: 600
    }];
    const wrapper = mount(AirCorridorForm, { props: { modelValue: request } });

    expect(wrapper.text()).toContain("高度层不能为空、不得重复且必须严格升序排列");
    expect(wrapper.text()).toContain("威胁最小射程必须小于最大射程");
    expect(wrapper.text()).toContain("威胁最低高度必须小于最高高度");
    expect(wrapper.text()).toContain("杀伤半径不能大于预警半径");
  });

  it("emits an explicit operation for each map-tool activation", async () => {
    const mobility = mount(MobilityForm, { props: { modelValue: mobilityDefinition.createDefaultRequest() } });
    await mobility.get('[data-action="activate-start-tool"]').trigger("click");
    await mobility.get('[data-action="activate-end-tool"]').trigger("click");
    expect(mobility.emitted("activate-map-tool")).toEqual([["start"], ["end"]]);

    const uav = mount(UavForm, { props: { modelValue: uavDefinition.createDefaultRequest() } });
    await uav.get('[data-action="activate-point-tool"]').trigger("click");
    await uav.get('[data-action="activate-route-tool"]').trigger("click");
    expect(uav.emitted("activate-map-tool")).toEqual([["point"], ["route"]]);

    const corridor = mount(AirCorridorForm, { props: { modelValue: airCorridorDefinition.createDefaultRequest() } });
    await corridor.get('[data-action="activate-threat-tool"]').trigger("click");
    expect(corridor.emitted("activate-map-tool")).toEqual([["threat"]]);
  });
});

describe("ModelParameterPanel route models", () => {
  it("switches through all registered model IDs and renders the explicit form", async () => {
    const forms: Record<(typeof MODEL_IDS)[number], Component> = {
      radar: RadarForm,
      uav: UavForm,
      watchpost: WatchpostForm,
      artillery: ArtilleryForm,
      reconVehicle: ReconVehicleForm,
      mobility: MobilityForm,
      airCorridor: AirCorridorForm
    };
    const wrapper = mount(ModelParameterPanel, {
      props: { modelId: "radar", modelValue: MODEL_REGISTRY.radar.createDefaultRequest() }
    });

    for (const modelId of MODEL_IDS) {
      await wrapper.setProps({ modelId, modelValue: MODEL_REGISTRY[modelId].createDefaultRequest() });
      expect(wrapper.findComponent(forms[modelId]).exists(), `missing form for ${modelId}`).toBe(true);
    }
  });

  it("registers all route forms, owns one footer, and forwards the intended map operation", async () => {
    const wrapper = mount(ModelParameterPanel, {
      props: { modelId: "mobility", modelValue: mobilityDefinition.createDefaultRequest() }
    });

    expect(wrapper.findComponent(MobilityForm).exists()).toBe(true);
    expect(wrapper.findAll('[data-action="submit"]')).toHaveLength(1);
    expect(wrapper.text()).toContain("运行分析");
    await wrapper.get('[data-action="activate-end-tool"]').trigger("click");
    expect(wrapper.emitted("activate-map-tool")).toEqual([["end"]]);
  });

  it("shows localized panel footer copy for validation summaries", async () => {
    const request = uavDefinition.createDefaultRequest();
    request.route = { sample_interval_m: 50, waypoints: [{ ...request.uav }] };
    const wrapper = mount(ModelParameterPanel, {
      props: { modelId: "uav", modelValue: request }
    });

    await wrapper.get('[data-action="submit"]').trigger("click");

    expect(wrapper.text()).toContain("请检查以下参数");
    expect(wrapper.text()).toContain("航线至少包含两个航点");
  });

  it("uses each active model validator, localizes issues, and blocks invalid submissions", async () => {
    const cases = [
      {
        modelId: "uav" as const,
        request: (() => {
          const value = uavDefinition.createDefaultRequest();
          value.route = { sample_interval_m: 50, waypoints: [{ ...value.uav }] };
          return value;
        })(),
        message: "航线至少包含两个航点"
      },
      {
        modelId: "reconVehicle" as const,
        request: (() => {
          const value = reconVehicleDefinition.createDefaultRequest();
          value.sensor.min_range_m = value.sensor.max_range_m;
          return value;
        })(),
        message: "最小探测距离必须小于最大探测距离"
      },
      {
        modelId: "mobility" as const,
        request: (() => {
          const value = mobilityDefinition.createDefaultRequest();
          value.vehicles.wheeled.enabled = false;
          value.vehicles.tracked.enabled = false;
          return value;
        })(),
        message: "至少启用一种车辆"
      },
      {
        modelId: "airCorridor" as const,
        request: (() => {
          const value = airCorridorDefinition.createDefaultRequest();
          value.aircraft.min_agl_m = value.aircraft.max_agl_m;
          return value;
        })(),
        message: "最低离地高度必须小于最高离地高度"
      }
    ];

    for (const testCase of cases) {
      const wrapper = mount(ModelParameterPanel, {
        props: { modelId: testCase.modelId, modelValue: testCase.request }
      });
      await wrapper.get('[data-action="submit"]').trigger("click");
      expect(wrapper.text()).toContain(testCase.message);
      expect(wrapper.emitted("submit")).toBeUndefined();
    }
  });

  it("blocks malformed altitude layers and submits one deeply isolated full air-corridor request", async () => {
    const invalid = airCorridorDefinition.createDefaultRequest();
    invalid.altitude_layers_m = [900, 600, 600];
    const invalidWrapper = mount(ModelParameterPanel, { props: { modelId: "airCorridor", modelValue: invalid } });
    await invalidWrapper.get('[data-action="submit"]').trigger("click");
    expect(invalidWrapper.text()).toContain("高度层不能为空、不得重复且必须严格升序排列");
    expect(invalidWrapper.emitted("submit")).toBeUndefined();

    const request = airCorridorDefinition.createDefaultRequest();
    request.threats = [{
      id: "stable-id", name: "固定威胁", lon: 80, lat: 32, min_range_m: 100,
      max_range_m: 1000, min_altitude_m: 50, max_altitude_m: 2000, threat_level: 2,
      kill_zone_radius_m: null, warning_zone_radius_m: null
    }];
    const original = structuredClone(request);
    const wrapper = mount(ModelParameterPanel, { props: { modelId: "airCorridor", modelValue: request } });
    await wrapper.get('[data-action="submit"]').trigger("click");
    const submitted = wrapper.emitted("submit")?.[0]?.[0] as typeof request;

    expect(submitted).toEqual(request);
    expectNoSharedReferences(submitted, request);
    submitted.altitude_layers_m.push(5000);
    submitted.threats[0].id = "changed";
    expect(request).toEqual(original);
  });
});
