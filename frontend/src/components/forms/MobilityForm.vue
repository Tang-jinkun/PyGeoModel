<template>
  <form class="route-form" aria-label="机动通行性参数" @submit.prevent>
    <section class="form-section">
      <div class="section-heading"><h3>起点与终点</h3><div class="map-actions"><ElButton :icon="Location" data-action="activate-start-tool" @click="emit('activate-map-tool', 'start')">地图设置起点</ElButton><ElButton :icon="MapLocation" data-action="activate-end-tool" @click="emit('activate-map-tool', 'end')">地图设置终点</ElButton></div></div>
      <label class="field-row"><span>高程模型 ID</span><ElInput data-field="dem-id" :model-value="modelValue.dem_id" @update:model-value="updateDemId" /></label>
      <div data-coordinate="start"><CoordinateEditor label="起点坐标" :model-value="[modelValue.start.lon, modelValue.start.lat]" @update:model-value="updatePoint('start', $event)" /></div>
      <div data-coordinate="end"><CoordinateEditor label="终点坐标" :model-value="[modelValue.end.lon, modelValue.end.lat]" @update:model-value="updatePoint('end', $event)" /></div>
    </section>

    <VehicleSection title="轮式车辆" prefix="wheeled" :vehicle="modelValue.vehicles.wheeled" @update="updateVehicle('wheeled', $event.key, $event.value)" />
    <VehicleSection title="履带车辆" prefix="tracked" :vehicle="modelValue.vehicles.tracked" @update="updateVehicle('tracked', $event.key, $event.value)" />

    <section class="form-section">
      <h3>道路网络</h3>
      <label class="field-row"><span>启用道路网络</span><ElSwitch data-field="road-network-enabled" :model-value="modelValue.road_network !== null" @update:model-value="toggleRoadNetwork" /></label>
      <template v-if="modelValue.road_network">
        <NumberRow label="道路缓冲距离" unit="米" field="road-buffer" :value="modelValue.road_network.road_buffer_m" @update="updateRoadNetwork('road_buffer_m', $event)" />
        <label class="field-row field-row--stack"><span>道路 GeoJSON</span><ElInput data-field="road-geojson" type="textarea" :rows="3" :model-value="roadGeoJsonText" @change="updateRoadGeoJson" /></label>
        <label class="field-row field-row--stack"><span>道路等级速度</span><ElInput data-field="road-classes" type="textarea" :rows="3" :model-value="roadClassesText" @change="updateRoadClasses" /></label>
      </template>
    </section>

    <section class="form-section">
      <h3>分析参数</h3>
      <label class="field-row"><span>允许对角移动</span><ElSwitch data-field="allow-diagonal" :model-value="modelValue.analysis.allow_diagonal" @update:model-value="updateAllowDiagonal" /></label>
      <NumberRow label="最大搜索半径" unit="米" field="max-search-radius" :value="modelValue.analysis.max_search_radius_m" nullable @update="updateAnalysis('max_search_radius_m', $event)" />
      <NumberRow label="路径简化容差" unit="米" field="simplify-tolerance" :value="modelValue.analysis.output_simplify_tolerance_m" nullable @update="updateAnalysis('output_simplify_tolerance_m', $event)" />
      <p v-for="issue in localizedIssues" :key="`${issue.path}:${issue.message}`" class="field-error">{{ issue.message }}</p>
    </section>
  </form>
</template>

<script setup lang="ts">
import { Location, MapLocation } from "@element-plus/icons-vue";
import { ElButton, ElInput, ElInputNumber, ElSwitch } from "element-plus";
import { computed, defineComponent, h, toRaw, type PropType } from "vue";
import type { SpatialCoordinate } from "../../map/spatialInput";
import { mobilityDefinition } from "../../models/mobility/definition";
import type { MobilityRequest, MobilityVehicleInput } from "../../models/mobility/types";
import CoordinateEditor from "../map/CoordinateEditor.vue";

const props = defineProps<{ modelValue: MobilityRequest }>();
const emit = defineEmits<{ "update:modelValue": [request: MobilityRequest]; "activate-map-tool": [operation: "start" | "end"] }>();
const NumberRow = createNumberRow();
const VehicleSection = defineComponent({
  props: { title: { type: String, required: true }, prefix: { type: String, required: true }, vehicle: { type: Object as PropType<MobilityVehicleInput>, required: true } }, emits: ["update"],
  setup(componentProps, { emit: componentEmit }) {
    const row = (label: string, suffix: string, key: keyof MobilityVehicleInput, unit = "") => h(NumberRow, { label, unit, field: `${componentProps.prefix}-${suffix}`, value: componentProps.vehicle[key] as number, onUpdate: (value: number) => componentEmit("update", { key, value }) });
    return () => h("section", { class: "form-section" }, [h("h3", componentProps.title), h("label", { class: "field-row" }, [h("span", "启用"), h("input", { type: "checkbox", "data-field": `${componentProps.prefix}-enabled`, checked: componentProps.vehicle.enabled, onChange: (event: Event) => componentEmit("update", { key: "enabled", value: (event.target as HTMLInputElement).checked }) })]), row("基础速度", "base-speed", "base_speed_kph", "千米/时"), row("最大坡度", "max-slope", "max_slope_deg", "度"), row("坡度惩罚系数", "slope-penalty", "slope_penalty"), row("道路速度倍率", "road-speed", "road_speed_multiplier"), row("越野速度倍率", "offroad-speed", "offroad_speed_multiplier")]);
  }
});

const localizedIssues = computed(() => mobilityDefinition.validate(props.modelValue).map((issue) => issue.path === "vehicles" ? { ...issue, message: "至少启用一种车辆" } : issue));
const roadGeoJsonText = computed(() => JSON.stringify(props.modelValue.road_network?.geojson ?? null, null, 2));
const roadClassesText = computed(() => JSON.stringify(props.modelValue.road_network?.road_classes ?? {}, null, 2));

function createNumberRow() { return defineComponent({ props: { label: { type: String, required: true }, unit: { type: String, default: "" }, field: { type: String, required: true }, value: { type: Number as PropType<number | null>, default: null }, nullable: Boolean }, emits: ["update"], setup(componentProps, { emit: componentEmit }) { return () => h("label", { class: "field-row" }, [h("span", componentProps.label), h("div", { class: "input-with-unit" }, [h(ElInputNumber, { "data-field": componentProps.field, modelValue: componentProps.value ?? undefined, controlsPosition: "right", "onUpdate:modelValue": (value: number | undefined) => componentEmit("update", componentProps.nullable ? value ?? null : value ?? 0) }), componentProps.unit ? h("span", { class: "unit" }, componentProps.unit) : null])]); } }); }
function updateRequest(mutator: (request: MobilityRequest) => void) { const request = structuredClone(toRaw(props.modelValue)); mutator(request); emit("update:modelValue", request); }
function updateDemId(dem_id: string) { updateRequest((request) => { request.dem_id = dem_id; }); }
function updatePoint(key: "start" | "end", coordinate: SpatialCoordinate | null) { if (coordinate) updateRequest((request) => { request[key].lon = coordinate[0]; request[key].lat = coordinate[1]; }); }
function updateVehicle<T extends keyof MobilityVehicleInput>(kind: "wheeled" | "tracked", key: T, value: MobilityVehicleInput[T]) { updateRequest((request) => { request.vehicles[kind][key] = value; }); }
function toggleRoadNetwork(enabled: string | number | boolean) { updateRequest((request) => { request.road_network = enabled ? { geojson: null, road_buffer_m: 30, road_classes: {} } : null; }); }
function updateRoadNetwork<K extends keyof NonNullable<MobilityRequest["road_network"]>>(key: K, value: NonNullable<MobilityRequest["road_network"]>[K]) { updateRequest((request) => { if (request.road_network) request.road_network[key] = value; }); }
function updateRoadGeoJson(value: string) { const parsed = parseRecordOrNull(value); if (parsed !== undefined) updateRoadNetwork("geojson", parsed); }
function updateRoadClasses(value: string) { try { const parsed = JSON.parse(value); if (parsed && typeof parsed === "object" && !Array.isArray(parsed) && Object.values(parsed).every((item) => typeof item === "number")) updateRoadNetwork("road_classes", parsed as Record<string, number>); } catch { /* Keep the last valid controlled value. */ } }
function parseRecordOrNull(value: string): Record<string, unknown> | null | undefined { try { const parsed = JSON.parse(value); return parsed === null || (typeof parsed === "object" && !Array.isArray(parsed)) ? parsed as Record<string, unknown> | null : undefined; } catch { return undefined; } }
function updateAnalysis<K extends keyof MobilityRequest["analysis"]>(key: K, value: MobilityRequest["analysis"][K]) { updateRequest((request) => { request.analysis[key] = value; }); }
function updateAllowDiagonal(value: string | number | boolean) { updateAnalysis("allow_diagonal", Boolean(value)); }
</script>

<style scoped>
.route-form,.form-section{display:grid;gap:12px;min-width:0}.route-form{padding:14px 14px 24px}.form-section{padding-bottom:16px;border-bottom:1px solid #ebeef5}.form-section:last-child{border-bottom:0}.form-section h3{margin:0;color:#303133;font-size:14px;letter-spacing:0}.section-heading,.map-actions{display:flex;align-items:center;justify-content:space-between;gap:8px}.map-actions{justify-content:flex-end;flex-wrap:wrap}.field-row{display:grid;grid-template-columns:minmax(110px,.9fr) minmax(0,1.1fr);align-items:center;gap:10px;color:#606266;font-size:12px}.field-row--stack{grid-template-columns:1fr}.input-with-unit{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:7px;min-width:0}.input-with-unit :deep(.el-input-number),.field-row :deep(.el-input){width:100%}.unit{color:#909399;white-space:nowrap}.field-error{margin:0;color:#b42318;font-size:12px;line-height:1.45}@media(max-width:600px){.section-heading{align-items:flex-start;flex-direction:column}.field-row{grid-template-columns:1fr}}
</style>
