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
          <button type="button" :aria-label="`在地图上选择${field.label}`" @click="emit('activate-map-tool', field.mapTool ?? 'point')"><ElIcon><Location /></ElIcon></button>
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

const props = withDefaults(defineProps<{ modelId: ModelId; modelValue: BaseModelRequest; hideCoordinateFields?: boolean }>(), {
  hideCoordinateFields: false
});
const emit = defineEmits<{ "update:modelValue": [request: BaseModelRequest]; "activate-map-tool": [tool: MapTool] }>();
const schema = computed(() => props.hideCoordinateFields
  ? SCHEMAS[props.modelId].map((section) => ({
    ...section,
    fields: section.fields.filter((field) => field.kind !== "coordinate")
  })).filter((section) => section.fields.length)
  : SCHEMAS[props.modelId]);

function valueAt(path: string): unknown {
  return path.split(".").reduce<unknown>((value, key) => value && typeof value === "object" ? (value as Record<string, unknown>)[key] : undefined, props.modelValue);
}
function numericValue(path: string) { const value = valueAt(path); return typeof value === "number" && Number.isFinite(value) ? value : ""; }
function coordinateAt(path: string) {
  const value = valueAt(path) as Record<string, unknown> | undefined;
  return value && typeof value.lon === "number" && typeof value.lat === "number" ? `${value.lon.toFixed(6)}, ${value.lat.toFixed(6)}` : "请在地图上选择";
}
function replace(path: string, value: unknown) {
  const next = structuredClone(toRaw(props.modelValue)) as unknown as Record<string, unknown>;
  const keys = path.split("."); let target = next;
  for (const key of keys.slice(0, -1)) target = target[key] as Record<string, unknown>;
  target[keys.at(-1)!] = value;
  emit("update:modelValue", next as unknown as BaseModelRequest);
}
function updateNumber(path: string, event: Event) { const value = (event.target as HTMLInputElement).valueAsNumber; if (Number.isFinite(value)) replace(path, value); }
function updateBoolean(path: string, event: Event) { replace(path, (event.target as HTMLInputElement).checked); }
function updateText(path: string, event: Event) { replace(path, (event.target as HTMLSelectElement).value); }

const SCHEMAS: Record<ModelId, Section[]> = {
  radar: [
    { title: "位置与目标", fields: [{ label: "雷达位置", path: "radar", kind: "coordinate" }, { label: "雷达高度", path: "radar.height_m", unit: "m" }, { label: "目标高度", path: "target.height_m", unit: "m" }] },
    { title: "覆盖范围", fields: [{ label: "最大距离", path: "coverage.max_range_m", unit: "m" }, { label: "扫描模式", path: "coverage.scan_mode", kind: "select", options: [{ label: "全向", value: "omni" }, { label: "扇形", value: "sector" }] }, { label: "方位角", path: "coverage.azimuth_deg", unit: "度" }, { label: "波束宽度", path: "coverage.beam_width_deg", unit: "度" }] },
    { title: "高级参数", fields: [{ label: "考虑地球曲率", path: "advanced.use_curvature", kind: "switch" }, { label: "曲率系数", path: "advanced.curvature_coeff" }, { label: "体素网格尺寸", path: "advanced.voxel_grid_size" }, { label: "垂直波束宽度", path: "advanced.vertical_beam_width_deg", unit: "度" }, { label: "显示探测半球", path: "advanced.visual_dome_mode", kind: "switch" }] }
  ],
  uav: [{ title: "无人机", fields: [{ label: "无人机位置", path: "uav", kind: "coordinate" }, { label: "飞行高度", path: "uav.altitude_m", unit: "m" }, { label: "航向角", path: "uav.heading_deg", unit: "度" }] }, { title: "传感器", fields: [{ label: "水平视场角", path: "sensor.h_fov_deg", unit: "度" }, { label: "最大距离", path: "sensor.max_range_m", unit: "m" }, { label: "地面分辨率", path: "sensor.ground_resolution_m", unit: "m" }] }],
  watchpost: [{ title: "观察", fields: [{ label: "观察点位置", path: "observer", kind: "coordinate" }, { label: "观察点高度", path: "observer.height_m", unit: "m" }, { label: "目标高度", path: "target.height_m", unit: "m" }] }, { title: "覆盖范围", fields: [{ label: "最大距离", path: "coverage.max_range_m", unit: "m" }, { label: "方位角", path: "coverage.azimuth_deg", unit: "度" }, { label: "视角", path: "coverage.view_angle_deg", unit: "度" }] }],
  artillery: [{ title: "炮兵阵地", fields: [{ label: "阵地位置", path: "battery", kind: "coordinate" }, { label: "阵地高度", path: "battery.height_m", unit: "m" }, { label: "目标高度", path: "target.target_height_m", unit: "m" }] }, { title: "武器参数", fields: [{ label: "最小射程", path: "weapon.min_range_m", unit: "m" }, { label: "最大射程", path: "weapon.max_range_m", unit: "m" }, { label: "方位角", path: "weapon.azimuth_deg", unit: "度" }, { label: "水平射界", path: "weapon.traverse_deg", unit: "度" }] }],
  reconVehicle: [{ title: "侦察车辆", fields: [{ label: "车辆位置", path: "vehicle", kind: "coordinate" }, { label: "桅杆高度", path: "vehicle.mast_height_m", unit: "m" }, { label: "航向角", path: "vehicle.heading_deg", unit: "度" }] }, { title: "传感器", fields: [{ label: "最大距离", path: "sensor.max_range_m", unit: "m" }, { label: "最小距离", path: "sensor.min_range_m", unit: "m" }, { label: "视角", path: "sensor.view_angle_deg", unit: "度" }] }],
  mobility: [{ title: "起终点", fields: [{ label: "起点", path: "start", kind: "coordinate", mapTool: "start" }, { label: "终点", path: "end", kind: "coordinate", mapTool: "end" }] }, { title: "分析参数", fields: [{ label: "允许斜向移动", path: "analysis.allow_diagonal", kind: "switch" }, { label: "搜索半径", path: "analysis.max_search_radius_m", unit: "m" }, { label: "道路缓冲区", path: "road_network.road_buffer_m", unit: "m" }] }],
  airCorridor: [{ title: "起终点", fields: [{ label: "起点", path: "start", kind: "coordinate", mapTool: "start" }, { label: "终点", path: "end", kind: "coordinate", mapTool: "end" }] }, { title: "飞行参数", fields: [{ label: "巡航速度", path: "aircraft.cruise_speed_kph", unit: "千米/时" }, { label: "最小离地高度", path: "aircraft.min_agl_m", unit: "m" }, { label: "最大离地高度", path: "aircraft.max_agl_m", unit: "m" }] }]
};
</script>

<style scoped>
.model-parameter-fields{display:grid;gap:8px}.parameter-section{padding:8px 0;border-bottom:1px solid var(--wb-border-soft)}.parameter-section summary{padding:5px 0;color:var(--wb-fg);font-size:14px;font-weight:600;list-style:none}.parameter-section summary::before{display:inline-block;margin-right:6px;color:var(--wb-meta);content:">";transform:rotate(90deg);transition:transform 160ms ease}.parameter-section:not([open]) summary::before{transform:rotate(0)}.parameter-field{display:grid;grid-template-columns:minmax(0,1fr) 150px;align-items:center;gap:10px;min-height:40px;padding:4px 0 4px 12px;color:var(--wb-fg-2);font-size:13px}.parameter-field>select,.number-field input,.coordinate-field input{width:100%;height:32px;padding:0 8px;border:1px solid var(--wb-border);border-radius:6px;background:#fff;color:var(--wb-fg);font:inherit}.number-field,.coordinate-field{position:relative}.number-field input{padding-right:34px}.number-field small{position:absolute;top:50%;right:8px;color:var(--wb-meta);font-size:11px;transform:translateY(-50%)}.coordinate-field{display:flex;gap:4px}.coordinate-field input{min-width:0}.coordinate-field button{display:grid;width:32px;place-items:center;border:1px solid var(--wb-border);border-radius:6px;background:var(--wb-surface);color:var(--wb-fg-2);cursor:pointer}.parameter-switch{position:relative;justify-self:end;width:40px;height:24px}.parameter-switch input{position:absolute;inset:0;z-index:1;margin:0;opacity:0;cursor:pointer}.parameter-switch i{position:absolute;inset:0;border-radius:20px;background:var(--wb-border)}.parameter-switch i::after{position:absolute;top:2px;left:2px;width:20px;height:20px;border-radius:50%;background:#fff;content:"";transition:transform 160ms ease}.parameter-switch input:checked+i{background:var(--wb-accent)}.parameter-switch input:checked+i::after{transform:translateX(16px)}
</style>
