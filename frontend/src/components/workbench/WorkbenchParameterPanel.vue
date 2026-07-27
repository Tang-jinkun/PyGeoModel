<template>
  <section class="workbench-parameter-panel" :data-model-id="modelId">
    <div class="workbench-parameter-panel__body">
      <details v-for="section in schema" :key="section.title" open class="psec">
        <summary>{{ section.title }}</summary>
        <label
          v-for="field in section.fields"
          :key="field.path"
          class="pfield"
          :class="{ 'pfield--coordinate': field.kind === 'coordinate' }"
          :data-field="field.path"
        >
          <span>{{ field.label }}</span>
          <span v-if="field.kind === 'switch'" class="switch">
            <input type="checkbox" :checked="Boolean(valueAt(field.path))" @change="updateBoolean(field.path, $event)">
            <i aria-hidden="true"></i>
          </span>
          <span v-else-if="field.kind === 'coordinate'" class="coordinate">
            <input readonly :value="coordinateAt(field.path)">
            <button type="button" aria-label="在地图取点" @click="emit('activate-map-tool', field.mapTool ?? 'point')">+</button>
          </span>
          <select v-else-if="field.kind === 'select'" :value="String(valueAt(field.path) ?? '')" @change="updateText(field.path, $event)">
            <option v-for="option in field.options" :key="option.value" :value="option.value">{{ option.label }}</option>
          </select>
          <span v-else class="number">
            <input type="number" :value="numericValue(field.path)" @input="updateNumber(field.path, $event)">
            <small v-if="field.unit">{{ field.unit }}</small>
          </span>
        </label>
      </details>
    </div>
    <footer>
      <button type="button" class="draft">保存草稿</button>
      <button type="button" class="run" :disabled="submitting" @click="emit('submit')">{{ submitting ? '运行中' : '运行分析' }}</button>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, toRaw } from "vue";

import type { ModelId } from "../../models/registry";
import type { BaseModelRequest } from "../../models/shared";

type MapTool = "point" | "route" | "start" | "end" | "threat";
type Field = {
  label: string;
  path: string;
  unit?: string;
  kind?: "number" | "switch" | "coordinate" | "select";
  mapTool?: MapTool;
  options?: Array<{ label: string; value: string }>;
};
type Section = { title: string; fields: Field[] };

const props = defineProps<{ modelId: ModelId; modelValue: BaseModelRequest; submitting: boolean }>();
const emit = defineEmits<{
  "update:modelValue": [request: BaseModelRequest];
  submit: [];
  "activate-map-tool": [tool: MapTool];
}>();

const schema = computed(() => SCHEMAS[props.modelId]);

function valueAt(path: string): unknown {
  return path.split(".").reduce<unknown>((value, key) => (
    value && typeof value === "object" ? (value as Record<string, unknown>)[key] : undefined
  ), props.modelValue);
}

function numericValue(path: string) {
  const value = valueAt(path);
  return typeof value === "number" && Number.isFinite(value) ? value : "";
}

function coordinateAt(path: string) {
  const value = valueAt(path) as Record<string, unknown> | undefined;
  return value && typeof value.lon === "number" && typeof value.lat === "number"
    ? `${value.lon.toFixed(6)}, ${value.lat.toFixed(6)}`
    : "在地图中选取";
}

function replace(path: string, value: unknown) {
  const next = structuredClone(toRaw(props.modelValue)) as unknown as Record<string, unknown>;
  const keys = path.split(".");
  let target = next;
  for (const key of keys.slice(0, -1)) target = target[key] as Record<string, unknown>;
  target[keys.at(-1)!] = value;
  emit("update:modelValue", next as unknown as BaseModelRequest);
}

function updateNumber(path: string, event: Event) {
  const value = (event.target as HTMLInputElement).valueAsNumber;
  if (Number.isFinite(value)) replace(path, value);
}

function updateBoolean(path: string, event: Event) {
  replace(path, (event.target as HTMLInputElement).checked);
}

function updateText(path: string, event: Event) {
  replace(path, (event.target as HTMLSelectElement).value);
}

const SCHEMAS: Record<ModelId, Section[]> = {
  radar: [
    { title: "位置与目标", fields: [
      { label: "雷达站坐标", path: "radar", kind: "coordinate" },
      { label: "雷达架高", path: "radar.height_m", unit: "米" },
      { label: "目标高度", path: "target.height_m", unit: "米" }
    ] },
    { title: "覆盖范围", fields: [
      { label: "最大探测距离", path: "coverage.max_range_m", unit: "米" },
      { label: "扫描模式", path: "coverage.scan_mode", kind: "select", options: [{ label: "全向", value: "omni" }, { label: "扇区", value: "sector" }] },
      { label: "中心方位角", path: "coverage.azimuth_deg", unit: "度" },
      { label: "水平波束宽度", path: "coverage.beam_width_deg", unit: "度" }
    ] },
    { title: "高级体积参数", fields: [
      { label: "考虑地球曲率", path: "advanced.use_curvature", kind: "switch" },
      { label: "曲率系数", path: "advanced.curvature_coeff" },
      { label: "体素网格尺寸", path: "advanced.voxel_grid_size", unit: "格" },
      { label: "垂直波束宽度", path: "advanced.vertical_beam_width_deg", unit: "度" },
      { label: "显示探测穹顶", path: "advanced.visual_dome_mode", kind: "switch" }
    ] }
  ],
  uav: [{ title: "无人机位置", fields: [{ label: "无人机坐标", path: "uav", kind: "coordinate" }, { label: "飞行高度", path: "uav.altitude_m", unit: "米" }, { label: "航向", path: "uav.heading_deg", unit: "度" }] }, { title: "传感器", fields: [{ label: "水平视场角", path: "sensor.h_fov_deg", unit: "度" }, { label: "最大探测距离", path: "sensor.max_range_m", unit: "米" }, { label: "地面分辨率", path: "sensor.ground_resolution_m", unit: "米" }] }],
  watchpost: [{ title: "观察哨", fields: [{ label: "观察点坐标", path: "observer", kind: "coordinate" }, { label: "观察架高", path: "observer.height_m", unit: "米" }, { label: "目标高度", path: "target.height_m", unit: "米" }] }, { title: "覆盖范围", fields: [{ label: "最大可视距离", path: "coverage.max_range_m", unit: "米" }, { label: "方位角", path: "coverage.azimuth_deg", unit: "度" }, { label: "视场角", path: "coverage.view_angle_deg", unit: "度" }] }],
  artillery: [{ title: "阵地与目标", fields: [{ label: "火炮阵地", path: "battery", kind: "coordinate" }, { label: "阵地架高", path: "battery.height_m", unit: "米" }, { label: "目标高度", path: "target.target_height_m", unit: "米" }] }, { title: "射击诸元", fields: [{ label: "最小射程", path: "weapon.min_range_m", unit: "米" }, { label: "最大射程", path: "weapon.max_range_m", unit: "米" }, { label: "射向方位角", path: "weapon.azimuth_deg", unit: "度" }, { label: "方向射界", path: "weapon.traverse_deg", unit: "度" }] }],
  reconVehicle: [{ title: "车辆与航向", fields: [{ label: "车辆位置", path: "vehicle", kind: "coordinate" }, { label: "桅杆高度", path: "vehicle.mast_height_m", unit: "米" }, { label: "车辆航向", path: "vehicle.heading_deg", unit: "度" }] }, { title: "侦察传感器", fields: [{ label: "最大探测距离", path: "sensor.max_range_m", unit: "米" }, { label: "最小探测距离", path: "sensor.min_range_m", unit: "米" }, { label: "视场角", path: "sensor.view_angle_deg", unit: "度" }] }],
  mobility: [{ title: "起止点", fields: [{ label: "起点", path: "start", kind: "coordinate", mapTool: "start" }, { label: "终点", path: "end", kind: "coordinate", mapTool: "end" }] }, { title: "分析设置", fields: [{ label: "允许对角移动", path: "analysis.allow_diagonal", kind: "switch" }, { label: "最大搜索半径", path: "analysis.max_search_radius_m", unit: "米" }, { label: "道路缓冲", path: "road_network.road_buffer_m", unit: "米" }] }],
  airCorridor: [{ title: "起止点", fields: [{ label: "起点", path: "start", kind: "coordinate", mapTool: "start" }, { label: "终点", path: "end", kind: "coordinate", mapTool: "end" }] }, { title: "飞行约束", fields: [{ label: "巡航速度", path: "aircraft.cruise_speed_kph", unit: "公里/时" }, { label: "最低离地高度", path: "aircraft.min_agl_m", unit: "米" }, { label: "最高离地高度", path: "aircraft.max_agl_m", unit: "米" }] }]
};
</script>

<style scoped>
.workbench-parameter-panel{display:grid;height:100%;min-height:0;grid-template-rows:minmax(0,1fr) auto}.workbench-parameter-panel__body{min-height:0;overflow:auto;padding:8px 16px 16px}.psec{padding:8px 0;border-bottom:1px solid var(--wb-border-soft)}.psec summary{padding:8px 0;color:var(--wb-fg);font-size:14px;font-weight:600;list-style:none}.psec summary::-webkit-details-marker{display:none}.psec summary::before{content:">";display:inline-block;margin-right:6px;color:var(--wb-meta);transform:rotate(90deg)}.pfield{display:grid;grid-template-columns:minmax(0,1fr) 128px;align-items:center;gap:8px;min-height:40px;padding:5px 0 5px 14px;color:var(--wb-fg-2);font-size:14px}.pfield>input,.pfield>select,.number input,.coordinate input{width:100%;height:30px;padding:0 8px;color:var(--wb-fg);background:#fff;border:1px solid var(--wb-border);border-radius:8px;outline:0}.pfield>input:focus,.pfield>select:focus,.number input:focus,.coordinate input:focus{border-color:var(--wb-accent);box-shadow:0 0 0 4px rgb(0 113 227 / 20%)}.number{position:relative}.number input{padding-right:34px}.number small{position:absolute;right:8px;top:50%;transform:translateY(-50%);color:var(--wb-meta);font-size:12px;pointer-events:none}.switch{position:relative;width:40px;height:24px;justify-self:end}.switch input{position:absolute;inset:0;width:100%;height:100%;margin:0;opacity:0;cursor:pointer}.switch i{position:absolute;inset:0;border-radius:980px;background:var(--wb-border);transition:background 180ms ease}.switch i::after{position:absolute;top:2px;left:2px;width:20px;height:20px;border-radius:50%;background:var(--wb-bg);box-shadow:0 1px 2px rgb(0 0 0 / 18%);content:"";transition:transform 180ms ease}.switch input:checked+i{background:var(--wb-accent)}.switch input:checked+i::after{transform:translateX(16px)}.switch input:focus-visible+i{box-shadow:0 0 0 4px rgb(0 113 227 / 20%)}.coordinate{display:flex;gap:4px}.coordinate input{min-width:0}.coordinate button{width:30px;flex:none;border:1px solid var(--wb-border);border-radius:8px;background:var(--wb-surface);color:var(--wb-fg-2)}footer{display:flex;gap:8px;padding:12px 16px;border-top:1px solid var(--wb-border-soft)}footer button{height:40px;border-radius:980px;font-weight:600}.draft{padding:0 16px;color:var(--wb-fg-2);background:#fff;border:1px solid var(--wb-border)}.run{flex:1;color:#fff;background:var(--wb-accent);border:0}.run:disabled{opacity:.6}
</style>
