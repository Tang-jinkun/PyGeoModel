<template>
  <section class="model-parameter-fields">
    <details v-for="section in schema" :key="section.title" open class="parameter-section">
      <summary>{{ section.title }}</summary>
      <label v-for="field in section.fields" :key="field.path" class="parameter-field" :data-field="field.path">
        <span>{{ field.label }}</span>
        <span v-if="field.kind === 'switch'" class="parameter-switch">
          <input type="checkbox" :checked="Boolean(valueAt(field.path))" @change="updateBoolean(field.path, $event)">
          <i aria-hidden="true"></i>
        </span>
        <span v-else-if="field.kind === 'coordinate'" class="coordinate-field">
          <input readonly :value="coordinateAt(field.path)">
          <button type="button" :aria-label="`Pick ${field.label} on map`" @click="emit('activate-map-tool', field.mapTool ?? 'point')"><ElIcon><Location /></ElIcon></button>
        </span>
        <select v-else-if="field.kind === 'select'" :value="String(valueAt(field.path) ?? '')" @change="updateText(field.path, $event)">
          <option v-for="option in field.options" :key="option.value" :value="option.value">{{ option.label }}</option>
        </select>
        <span v-else class="number-field">
          <input type="number" :value="numericValue(field.path)" @input="updateNumber(field.path, $event)">
          <small v-if="field.unit">{{ field.unit }}</small>
        </span>
      </label>
    </details>
  </section>
</template>

<script setup lang="ts">
import { Location } from "@element-plus/icons-vue";
import { ElIcon } from "element-plus";
import { computed, toRaw } from "vue";

import type { ModelId } from "../../models/registry";
import type { BaseModelRequest } from "../../models/shared";

type MapTool = "point" | "route" | "start" | "end" | "threat";
type Field = { label: string; path: string; unit?: string; kind?: "number" | "switch" | "coordinate" | "select"; mapTool?: MapTool; options?: Array<{ label: string; value: string }> };
type Section = { title: string; fields: Field[] };

const props = defineProps<{ modelId: ModelId; modelValue: BaseModelRequest }>();
const emit = defineEmits<{ "update:modelValue": [request: BaseModelRequest]; "activate-map-tool": [tool: MapTool] }>();
const schema = computed(() => SCHEMAS[props.modelId]);

function valueAt(path: string): unknown {
  return path.split(".").reduce<unknown>((value, key) => value && typeof value === "object" ? (value as Record<string, unknown>)[key] : undefined, props.modelValue);
}
function numericValue(path: string) { const value = valueAt(path); return typeof value === "number" && Number.isFinite(value) ? value : ""; }
function coordinateAt(path: string) {
  const value = valueAt(path) as Record<string, unknown> | undefined;
  return value && typeof value.lon === "number" && typeof value.lat === "number" ? `${value.lon.toFixed(6)}, ${value.lat.toFixed(6)}` : "Pick on map";
}
function replace(path: string, value: unknown) {
  const next = structuredClone(toRaw(props.modelValue)) as Record<string, unknown>;
  const keys = path.split("."); let target = next;
  for (const key of keys.slice(0, -1)) target = target[key] as Record<string, unknown>;
  target[keys.at(-1)!] = value;
  emit("update:modelValue", next as BaseModelRequest);
}
function updateNumber(path: string, event: Event) { const value = (event.target as HTMLInputElement).valueAsNumber; if (Number.isFinite(value)) replace(path, value); }
function updateBoolean(path: string, event: Event) { replace(path, (event.target as HTMLInputElement).checked); }
function updateText(path: string, event: Event) { replace(path, (event.target as HTMLSelectElement).value); }

const SCHEMAS: Record<ModelId, Section[]> = {
  radar: [
    { title: "Position and target", fields: [{ label: "Radar location", path: "radar", kind: "coordinate" }, { label: "Radar height", path: "radar.height_m", unit: "m" }, { label: "Target height", path: "target.height_m", unit: "m" }] },
    { title: "Coverage", fields: [{ label: "Maximum range", path: "coverage.max_range_m", unit: "m" }, { label: "Scan mode", path: "coverage.scan_mode", kind: "select", options: [{ label: "Omnidirectional", value: "omni" }, { label: "Sector", value: "sector" }] }, { label: "Azimuth", path: "coverage.azimuth_deg", unit: "deg" }, { label: "Beam width", path: "coverage.beam_width_deg", unit: "deg" }] },
    { title: "Advanced", fields: [{ label: "Use earth curvature", path: "advanced.use_curvature", kind: "switch" }, { label: "Curvature coefficient", path: "advanced.curvature_coeff" }, { label: "Voxel grid size", path: "advanced.voxel_grid_size" }, { label: "Vertical beam width", path: "advanced.vertical_beam_width_deg", unit: "deg" }, { label: "Show detection dome", path: "advanced.visual_dome_mode", kind: "switch" }] }
  ],
  uav: [{ title: "UAV", fields: [{ label: "UAV location", path: "uav", kind: "coordinate" }, { label: "Altitude", path: "uav.altitude_m", unit: "m" }, { label: "Heading", path: "uav.heading_deg", unit: "deg" }] }, { title: "Sensor", fields: [{ label: "Horizontal FOV", path: "sensor.h_fov_deg", unit: "deg" }, { label: "Maximum range", path: "sensor.max_range_m", unit: "m" }, { label: "Ground resolution", path: "sensor.ground_resolution_m", unit: "m" }] }],
  watchpost: [{ title: "Observation", fields: [{ label: "Observer location", path: "observer", kind: "coordinate" }, { label: "Observer height", path: "observer.height_m", unit: "m" }, { label: "Target height", path: "target.height_m", unit: "m" }] }, { title: "Coverage", fields: [{ label: "Maximum range", path: "coverage.max_range_m", unit: "m" }, { label: "Azimuth", path: "coverage.azimuth_deg", unit: "deg" }, { label: "View angle", path: "coverage.view_angle_deg", unit: "deg" }] }],
  artillery: [{ title: "Battery", fields: [{ label: "Battery location", path: "battery", kind: "coordinate" }, { label: "Battery height", path: "battery.height_m", unit: "m" }, { label: "Target height", path: "target.target_height_m", unit: "m" }] }, { title: "Weapon", fields: [{ label: "Minimum range", path: "weapon.min_range_m", unit: "m" }, { label: "Maximum range", path: "weapon.max_range_m", unit: "m" }, { label: "Azimuth", path: "weapon.azimuth_deg", unit: "deg" }, { label: "Traverse", path: "weapon.traverse_deg", unit: "deg" }] }],
  reconVehicle: [{ title: "Vehicle", fields: [{ label: "Vehicle location", path: "vehicle", kind: "coordinate" }, { label: "Mast height", path: "vehicle.mast_height_m", unit: "m" }, { label: "Heading", path: "vehicle.heading_deg", unit: "deg" }] }, { title: "Sensor", fields: [{ label: "Maximum range", path: "sensor.max_range_m", unit: "m" }, { label: "Minimum range", path: "sensor.min_range_m", unit: "m" }, { label: "View angle", path: "sensor.view_angle_deg", unit: "deg" }] }],
  mobility: [{ title: "Locations", fields: [{ label: "Start", path: "start", kind: "coordinate", mapTool: "start" }, { label: "End", path: "end", kind: "coordinate", mapTool: "end" }] }, { title: "Analysis", fields: [{ label: "Allow diagonal movement", path: "analysis.allow_diagonal", kind: "switch" }, { label: "Search radius", path: "analysis.max_search_radius_m", unit: "m" }, { label: "Road buffer", path: "road_network.road_buffer_m", unit: "m" }] }],
  airCorridor: [{ title: "Locations", fields: [{ label: "Start", path: "start", kind: "coordinate", mapTool: "start" }, { label: "End", path: "end", kind: "coordinate", mapTool: "end" }] }, { title: "Flight", fields: [{ label: "Cruise speed", path: "aircraft.cruise_speed_kph", unit: "kph" }, { label: "Minimum AGL", path: "aircraft.min_agl_m", unit: "m" }, { label: "Maximum AGL", path: "aircraft.max_agl_m", unit: "m" }] }]
};
</script>

<style scoped>
.model-parameter-fields{display:grid;gap:8px}.parameter-section{padding:8px 0;border-bottom:1px solid var(--wb-border-soft)}.parameter-section summary{padding:5px 0;color:var(--wb-fg);font-size:14px;font-weight:600;list-style:none}.parameter-section summary::before{display:inline-block;margin-right:6px;color:var(--wb-meta);content:">";transform:rotate(90deg)}.parameter-field{display:grid;grid-template-columns:minmax(0,1fr) 150px;align-items:center;gap:10px;min-height:40px;padding:4px 0 4px 12px;color:var(--wb-fg-2);font-size:13px}.parameter-field>select,.number-field input,.coordinate-field input{width:100%;height:32px;padding:0 8px;border:1px solid var(--wb-border);border-radius:6px;background:#fff;color:var(--wb-fg);font:inherit}.number-field,.coordinate-field{position:relative}.number-field input{padding-right:34px}.number-field small{position:absolute;top:50%;right:8px;color:var(--wb-meta);font-size:11px;transform:translateY(-50%)}.coordinate-field{display:flex;gap:4px}.coordinate-field input{min-width:0}.coordinate-field button{display:grid;width:32px;place-items:center;border:1px solid var(--wb-border);border-radius:6px;background:var(--wb-surface);color:var(--wb-fg-2);cursor:pointer}.parameter-switch{position:relative;justify-self:end;width:40px;height:24px}.parameter-switch input{position:absolute;inset:0;z-index:1;margin:0;opacity:0;cursor:pointer}.parameter-switch i{position:absolute;inset:0;border-radius:20px;background:var(--wb-border)}.parameter-switch i::after{position:absolute;top:2px;left:2px;width:20px;height:20px;border-radius:50%;background:#fff;content:"";transition:transform 160ms ease}.parameter-switch input:checked+i{background:var(--wb-accent)}.parameter-switch input:checked+i::after{transform:translateX(16px)}
</style>
