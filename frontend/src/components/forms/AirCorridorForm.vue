<template>
  <form class="route-form" aria-label="空中走廊规划参数" @submit.prevent>
    <section class="form-section">
      <div class="section-heading"><h3>起点与终点</h3><div class="map-actions"><ElButton :icon="Location" data-action="activate-start-tool" @click="emit('activate-map-tool', 'start')">地图设置起点</ElButton><ElButton :icon="MapLocation" data-action="activate-end-tool" @click="emit('activate-map-tool', 'end')">地图设置终点</ElButton></div></div>
      <label class="field-row"><span>高程模型 ID</span><ElInput data-field="dem-id" :model-value="modelValue.dem_id" @update:model-value="updateDemId" /></label>
      <div data-coordinate="start"><CoordinateEditor label="起点坐标" :model-value="[modelValue.start.lon, modelValue.start.lat]" @update:model-value="updatePointCoordinate('start', $event)" /></div>
      <NumberRow label="起点高度" unit="米" field="start-altitude" :value="modelValue.start.altitude_m" @update="updatePoint('start', 'altitude_m', $event)" />
      <AltitudeModeRow label="起点高度模式" field="start-altitude-mode" :value="modelValue.start.altitude_mode" @update="updatePoint('start', 'altitude_mode', $event)" />
      <div data-coordinate="end"><CoordinateEditor label="终点坐标" :model-value="[modelValue.end.lon, modelValue.end.lat]" @update:model-value="updatePointCoordinate('end', $event)" /></div>
      <NumberRow label="终点高度" unit="米" field="end-altitude" :value="modelValue.end.altitude_m" @update="updatePoint('end', 'altitude_m', $event)" />
      <AltitudeModeRow label="终点高度模式" field="end-altitude-mode" :value="modelValue.end.altitude_mode" @update="updatePoint('end', 'altitude_mode', $event)" />
    </section>

    <section class="form-section">
      <h3>飞行器</h3>
      <NumberRow label="巡航速度" unit="千米/时" field="cruise-speed" :value="modelValue.aircraft.cruise_speed_kph" @update="updateAircraft('cruise_speed_kph', $event)" />
      <NumberRow label="最低离地高度" unit="米" field="min-agl" :value="modelValue.aircraft.min_agl_m" @update="updateAircraft('min_agl_m', $event)" />
      <NumberRow label="最高离地高度" unit="米" field="max-agl" :value="modelValue.aircraft.max_agl_m" @update="updateAircraft('max_agl_m', $event)" />
      <NumberRow label="最大爬升率" unit="米/秒" field="max-climb-rate" :value="modelValue.aircraft.max_climb_rate_mps" @update="updateAircraft('max_climb_rate_mps', $event)" />
      <NumberRow label="最大下降率" unit="米/秒" field="max-descent-rate" :value="modelValue.aircraft.max_descent_rate_mps" @update="updateAircraft('max_descent_rate_mps', $event)" />
      <label class="field-row"><span>高度层</span><div class="input-with-unit"><ElInput data-field="altitude-layers" :model-value="altitudeLayersText" placeholder="例如 300, 600, 900" @update:model-value="updateAltitudeLayers" /><span class="unit">米</span></div></label>
    </section>

    <section class="form-section">
      <div class="section-heading"><h3>防空威胁</h3><div class="map-actions"><ElButton :icon="Aim" data-action="activate-threat-tool" @click="emit('activate-map-tool', 'threat')">地图添加威胁</ElButton><ElButton :icon="Plus" data-action="add-threat" @click="addThreat">添加威胁</ElButton></div></div>
      <ThreatEditor :model-value="spatialThreats" @spatial-edit="updateThreatAction" />
      <div v-for="threat in modelValue.threats" :key="threat.id" class="threat-details" :data-threat-details="threat.id">
        <strong>{{ threat.name || threat.id }}</strong>
        <label class="field-row"><span>名称</span><ElInput :data-field="`threat-name-${threat.id}`" :model-value="threat.name ?? ''" @update:model-value="updateThreatName(threat.id, $event)" /></label>
        <NumberRow label="最小射程" unit="米" :field="`threat-min-range-${threat.id}`" :value="threat.min_range_m" @update="updateThreat(threat.id, 'min_range_m', $event)" />
        <NumberRow label="最大射程" unit="米" :field="`threat-max-range-${threat.id}`" :value="threat.max_range_m" @update="updateThreat(threat.id, 'max_range_m', $event)" />
        <NumberRow label="最低高度" unit="米" :field="`threat-min-altitude-${threat.id}`" :value="threat.min_altitude_m" @update="updateThreat(threat.id, 'min_altitude_m', $event)" />
        <NumberRow label="最高高度" unit="米" :field="`threat-max-altitude-${threat.id}`" :value="threat.max_altitude_m" @update="updateThreat(threat.id, 'max_altitude_m', $event)" />
        <NumberRow label="威胁等级" :field="`threat-level-${threat.id}`" :value="threat.threat_level" @update="updateThreat(threat.id, 'threat_level', $event)" />
        <NumberRow label="杀伤半径" unit="米" :field="`threat-kill-radius-${threat.id}`" :value="threat.kill_zone_radius_m" nullable @update="updateThreat(threat.id, 'kill_zone_radius_m', $event)" />
        <NumberRow label="预警半径" unit="米" :field="`threat-warning-radius-${threat.id}`" :value="threat.warning_zone_radius_m" nullable @update="updateThreat(threat.id, 'warning_zone_radius_m', $event)" />
      </div>
    </section>

    <section class="form-section">
      <h3>规划权重</h3>
      <NumberRow label="走廊宽度" unit="米" field="corridor-width" :value="modelValue.planning.corridor_width_m" @update="updatePlanning('corridor_width_m', $event)" />
      <NumberRow label="水平分辨率" unit="米" field="horizontal-resolution" :value="modelValue.planning.horizontal_resolution_m" @update="updatePlanning('horizontal_resolution_m', $event)" />
      <label class="field-row"><span>允许改变高度</span><ElSwitch data-field="allow-altitude-change" :model-value="modelValue.planning.allow_altitude_change" @update:model-value="updateAllowAltitudeChange" /></label>
      <NumberRow label="威胁权重" field="threat-weight" :value="modelValue.planning.threat_weight" @update="updatePlanning('threat_weight', $event)" />
      <NumberRow label="距离权重" field="distance-weight" :value="modelValue.planning.distance_weight" @update="updatePlanning('distance_weight', $event)" />
      <NumberRow label="高度变化权重" field="altitude-change-weight" :value="modelValue.planning.altitude_change_weight" @update="updatePlanning('altitude_change_weight', $event)" />
      <NumberRow label="地形净空权重" field="terrain-clearance-weight" :value="modelValue.planning.terrain_clearance_weight" @update="updatePlanning('terrain_clearance_weight', $event)" />
      <NumberRow label="路径简化容差" unit="米" field="simplify-tolerance" :value="modelValue.planning.output_simplify_tolerance_m" nullable @update="updatePlanning('output_simplify_tolerance_m', $event)" />
      <p v-for="issue in localizedIssues" :key="`${issue.path}:${issue.message}`" class="field-error">{{ issue.message }}</p>
    </section>
  </form>
</template>

<script setup lang="ts">
import { Aim, Location, MapLocation, Plus } from "@element-plus/icons-vue";
import { ElButton, ElInput, ElInputNumber, ElRadioButton, ElRadioGroup, ElSwitch } from "element-plus";
import { computed, defineComponent, h, toRaw, type PropType } from "vue";
import type { SpatialCoordinate, SpatialDraftAction, SpatialThreat } from "../../map/spatialInput";
import { airCorridorDefinition } from "../../models/airCorridor/definition";
import type { AirCorridorPointInput, AirCorridorRequest, AirDefenseThreatInput } from "../../models/airCorridor/types";
import CoordinateEditor from "../map/CoordinateEditor.vue";
import ThreatEditor from "../map/ThreatEditor.vue";

const props = defineProps<{ modelValue: AirCorridorRequest }>();
const emit = defineEmits<{ "update:modelValue": [request: AirCorridorRequest]; "activate-map-tool": [operation: "start" | "end" | "threat"] }>();
const NumberRow = defineComponent({ props: { label: { type: String, required: true }, unit: { type: String, default: "" }, field: { type: String, required: true }, value: { type: Number as PropType<number | null>, default: null }, nullable: Boolean }, emits: ["update"], setup(componentProps, { emit: componentEmit }) { return () => h("label", { class: "field-row" }, [h("span", componentProps.label), h("div", { class: "input-with-unit" }, [h(ElInputNumber, { "data-field": componentProps.field, modelValue: componentProps.value ?? undefined, controlsPosition: "right", "onUpdate:modelValue": (value: number | undefined) => componentEmit("update", componentProps.nullable ? value ?? null : value ?? 0) }), componentProps.unit ? h("span", { class: "unit" }, componentProps.unit) : null])]); } });
const AltitudeModeRow = defineComponent({ props: { label: { type: String, required: true }, field: { type: String, required: true }, value: { type: String as PropType<"agl" | "amsl">, required: true } }, emits: ["update"], setup(componentProps, { emit: componentEmit }) { return () => h("label", { class: "field-row" }, [h("span", componentProps.label), h(ElRadioGroup, { "data-field": componentProps.field, modelValue: componentProps.value, "onUpdate:modelValue": (value: unknown) => { if (value === "agl" || value === "amsl") componentEmit("update", value); } }, () => [h(ElRadioButton, { value: "agl" }, () => "离地高度"), h(ElRadioButton, { value: "amsl" }, () => "海拔高度")])]); } });

const altitudeLayersText = computed(() => props.modelValue.altitude_layers_m.join(", "));
const spatialThreats = computed<SpatialThreat[]>(() => props.modelValue.threats.map((threat) => ({ id: threat.id, coordinate: [threat.lon, threat.lat], properties: { name: threat.name } })));
const localizedIssues = computed(() => airCorridorDefinition.validate(props.modelValue).map(localizeIssue));

function updateRequest(mutator: (request: AirCorridorRequest) => void) { const request = structuredClone(toRaw(props.modelValue)); mutator(request); emit("update:modelValue", request); }
function updateDemId(dem_id: string) { updateRequest((request) => { request.dem_id = dem_id; }); }
function updatePointCoordinate(key: "start" | "end", coordinate: SpatialCoordinate | null) { if (coordinate) updateRequest((request) => { request[key].lon = coordinate[0]; request[key].lat = coordinate[1]; }); }
function updatePoint<K extends keyof AirCorridorPointInput>(point: "start" | "end", key: K, value: AirCorridorPointInput[K]) { updateRequest((request) => { request[point][key] = value; }); }
function updateAircraft<K extends keyof AirCorridorRequest["aircraft"]>(key: K, value: AirCorridorRequest["aircraft"][K]) { updateRequest((request) => { request.aircraft[key] = value; }); }
function updateAltitudeLayers(value: string) { updateRequest((request) => { request.altitude_layers_m = value.split(/[,，\s]+/).filter(Boolean).map(Number).filter(Number.isFinite); }); }
function updateThreatAction(action: SpatialDraftAction) { if (action.type !== "update-threat" && action.type !== "remove-threat") return; updateRequest((request) => { if (action.type === "remove-threat") { request.threats = request.threats.filter(({ id }) => id !== action.id); return; } const threat = request.threats.find(({ id }) => id === action.id); if (threat && action.coordinate) { threat.lon = action.coordinate[0]; threat.lat = action.coordinate[1]; } }); }
function addThreat() { updateRequest((request) => { request.threats.push({ id: crypto.randomUUID(), name: null, lon: (request.start.lon + request.end.lon) / 2, lat: (request.start.lat + request.end.lat) / 2, min_range_m: 0, max_range_m: 5000, min_altitude_m: 0, max_altitude_m: 3000, threat_level: 1, kill_zone_radius_m: null, warning_zone_radius_m: null }); }); }
function updateThreat<K extends keyof AirDefenseThreatInput>(id: string, key: K, value: AirDefenseThreatInput[K]) { updateRequest((request) => { const threat = request.threats.find((candidate) => candidate.id === id); if (threat) threat[key] = value; }); }
function updateThreatName(id: string, value: string) { updateThreat(id, "name", value.trim() === "" ? null : value); }
function updatePlanning<K extends keyof AirCorridorRequest["planning"]>(key: K, value: AirCorridorRequest["planning"][K]) { updateRequest((request) => { request.planning[key] = value; }); }
function updateAllowAltitudeChange(value: string | number | boolean) { updatePlanning("allow_altitude_change", Boolean(value)); }
function localizeIssue(issue: { path: string; message: string }) { if (issue.path === "aircraft.max_agl_m") return { ...issue, message: "最低离地高度必须小于最高离地高度" }; if (issue.path === "altitude_layers_m") return { ...issue, message: "高度层不能为空、不得重复且必须严格升序排列" }; if (issue.path.endsWith(".max_range_m")) return { ...issue, message: "威胁最小射程必须小于最大射程" }; if (issue.path.endsWith(".max_altitude_m")) return { ...issue, message: "威胁最低高度必须小于最高高度" }; if (issue.path.endsWith(".kill_zone_radius_m")) return { ...issue, message: "杀伤半径不能大于预警半径" }; return issue; }
</script>

<style scoped>
.route-form,.form-section,.threat-details{display:grid;gap:12px;min-width:0}.route-form{padding:14px 14px 24px}.form-section{padding-bottom:16px;border-bottom:1px solid #ebeef5}.form-section:last-child{border-bottom:0}.form-section h3{margin:0;color:#303133;font-size:14px;letter-spacing:0}.section-heading,.map-actions{display:flex;align-items:center;justify-content:space-between;gap:8px}.map-actions{justify-content:flex-end;flex-wrap:wrap}.field-row{display:grid;grid-template-columns:minmax(110px,.9fr) minmax(0,1.1fr);align-items:center;gap:10px;color:#606266;font-size:12px}.input-with-unit{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:7px;min-width:0}.input-with-unit :deep(.el-input-number),.field-row :deep(.el-input),.field-row :deep(.el-radio-group){width:100%}.unit{color:#909399;white-space:nowrap}.threat-details{padding:10px;border-left:3px solid #dcdfe6}.threat-details strong{overflow-wrap:anywhere;font-size:12px}.field-error{margin:0;color:#b42318;font-size:12px;line-height:1.45}@media(max-width:600px){.section-heading{align-items:flex-start;flex-direction:column}.field-row{grid-template-columns:1fr}}
</style>
