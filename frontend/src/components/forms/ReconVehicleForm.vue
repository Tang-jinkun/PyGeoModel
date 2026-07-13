<template>
  <form class="route-form" aria-label="侦察车辆覆盖参数" @submit.prevent>
    <section class="form-section">
      <div class="section-heading"><h3>车辆与航线</h3><div class="map-actions"><ElButton :icon="MapLocation" data-action="activate-point-tool" @click="emit('activate-map-tool', 'point')">地图选点</ElButton><ElButton :icon="Position" data-action="activate-route-tool" @click="emit('activate-map-tool', 'route')">地图绘制航线</ElButton></div></div>
      <label class="field-row"><span>高程模型 ID</span><ElInput data-field="dem-id" :model-value="modelValue.dem_id" @update:model-value="updateDemId" /></label>
      <div data-coordinate="vehicle"><CoordinateEditor label="车辆坐标" :model-value="[modelValue.vehicle.lon, modelValue.vehicle.lat]" @update:model-value="updateVehicleCoordinate" /></div>
      <NumberRow label="车辆航向角" unit="度" field="vehicle-heading" :value="modelValue.vehicle.heading_deg" @update="updateVehicle('heading_deg', $event)" />
      <NumberRow label="桅杆高度" unit="米" field="mast-height" :value="modelValue.vehicle.mast_height_m" @update="updateVehicle('mast_height_m', $event)" />
      <label class="field-row"><span>启用航线</span><ElSwitch data-field="route-enabled" :model-value="modelValue.route !== null" @update:model-value="toggleRoute" /></label>
      <NumberRow label="航线采样间隔" unit="米" field="route-sample-interval" :value="modelValue.route?.sample_interval_m ?? 50" @update="updateRouteSampleInterval" />
      <template v-if="modelValue.route">
        <RouteEditor :model-value="routePoints" @spatial-edit="updateRouteAction" />
        <div v-for="(waypoint, index) in modelValue.route.waypoints" :key="index" class="waypoint-details">
          <strong>航点 {{ index + 1 }}</strong>
          <NumberRow label="车辆航向角" unit="度" :field="`waypoint-heading-${index}`" :value="waypoint.heading_deg" @update="updateWaypoint(index, 'heading_deg', $event)" />
          <NumberRow label="桅杆高度" unit="米" :field="`waypoint-mast-height-${index}`" :value="waypoint.mast_height_m" @update="updateWaypoint(index, 'mast_height_m', $event)" />
        </div>
      </template>
    </section>

    <section class="form-section">
      <h3>传感器与目标</h3>
      <label class="field-row"><span>传感器类型</span><ElSelect data-field="sensor-type" :model-value="modelValue.sensor.sensor_type" @update:model-value="updateSensorType"><ElOption label="光学" value="optical" /><ElOption label="热成像" value="thermal" /><ElOption label="雷达" value="radar" /><ElOption label="通用" value="generic" /></ElSelect></label>
      <NumberRow label="最大探测距离" unit="米" field="sensor-max-range" :value="modelValue.sensor.max_range_m" @update="updateSensor('max_range_m', $event)" />
      <NumberRow label="最小探测距离" unit="米" field="sensor-min-range" :value="modelValue.sensor.min_range_m" @update="updateSensor('min_range_m', $event)" />
      <label class="field-row"><span>扫描模式</span><ElRadioGroup data-field="scan-mode" :model-value="modelValue.sensor.scan_mode" @update:model-value="updateScanMode"><ElRadioButton value="omni">全向</ElRadioButton><ElRadioButton value="sector">扇区</ElRadioButton></ElRadioGroup></label>
      <NumberRow label="视场角" unit="度" field="view-angle" :value="modelValue.sensor.view_angle_deg" @update="updateSensor('view_angle_deg', $event)" />
      <NumberRow label="目标高度" unit="米" field="target-height" :value="modelValue.target.height_m" @update="updateTargetHeight" />
    </section>

    <section class="form-section">
      <h3>分析参数</h3>
      <label class="field-row"><span>启用地形遮蔽</span><ElSwitch data-field="terrain-occlusion" :model-value="modelValue.analysis.use_terrain_occlusion" @update:model-value="updateTerrainOcclusion" /></label>
      <label class="field-row"><span>考虑地球曲率</span><ElSwitch data-field="use-curvature" :model-value="modelValue.analysis.use_curvature" @update:model-value="updateCurvature" /></label>
      <NumberRow label="曲率系数" field="curvature-coeff" :value="modelValue.analysis.curvature_coeff" @update="updateAnalysis('curvature_coeff', $event)" />
      <NumberRow label="轮廓简化容差" unit="米" field="simplify-tolerance" :value="modelValue.analysis.output_simplify_tolerance_m" nullable @update="updateAnalysis('output_simplify_tolerance_m', $event)" />
      <p v-for="issue in localizedIssues" :key="`${issue.path}:${issue.message}`" class="field-error">{{ issue.message }}</p>
    </section>
  </form>
</template>

<script setup lang="ts">
import { MapLocation, Position } from "@element-plus/icons-vue";
import { ElButton, ElInput, ElInputNumber, ElOption, ElRadioButton, ElRadioGroup, ElSelect, ElSwitch } from "element-plus";
import { computed, defineComponent, h, toRaw, type PropType } from "vue";
import type { SpatialCoordinate, SpatialDraftAction } from "../../map/spatialInput";
import { reconVehicleDefinition } from "../../models/reconVehicle/definition";
import type { ReconVehiclePositionInput, ReconVehicleRequest } from "../../models/reconVehicle/types";
import CoordinateEditor from "../map/CoordinateEditor.vue";
import RouteEditor from "../map/RouteEditor.vue";

const props = defineProps<{ modelValue: ReconVehicleRequest }>();
const emit = defineEmits<{ "update:modelValue": [request: ReconVehicleRequest]; "activate-map-tool": [operation: "point" | "route"] }>();
const NumberRow = defineComponent({ props: { label: { type: String, required: true }, unit: { type: String, default: "" }, field: { type: String, required: true }, value: { type: Number as PropType<number | null>, default: null }, nullable: Boolean }, emits: ["update"], setup(componentProps, { emit: componentEmit }) { return () => h("label", { class: "field-row" }, [h("span", componentProps.label), h("div", { class: "input-with-unit" }, [h(ElInputNumber, { "data-field": componentProps.field, modelValue: componentProps.value ?? undefined, controlsPosition: "right", "onUpdate:modelValue": (value: number | undefined) => componentEmit("update", componentProps.nullable ? value ?? null : value ?? 0) }), componentProps.unit ? h("span", { class: "unit" }, componentProps.unit) : null])]); } });

const routePoints = computed<SpatialCoordinate[]>(() => props.modelValue.route?.waypoints.map(({ lon, lat }) => [lon, lat]) ?? []);
const localizedIssues = computed(() => reconVehicleDefinition.validate(props.modelValue).map((issue) => issue.path === "route.waypoints" ? { ...issue, message: "航线至少包含两个航点" } : issue.path === "sensor.max_range_m" ? { ...issue, message: "最小探测距离必须小于最大探测距离" } : issue));

function updateRequest(mutator: (request: ReconVehicleRequest) => void) { const request = structuredClone(toRaw(props.modelValue)); mutator(request); emit("update:modelValue", request); }
function updateDemId(dem_id: string) { updateRequest((request) => { request.dem_id = dem_id; }); }
function updateVehicleCoordinate(coordinate: SpatialCoordinate | null) { if (coordinate) updateRequest((request) => { request.vehicle.lon = coordinate[0]; request.vehicle.lat = coordinate[1]; }); }
function updateVehicle<K extends keyof ReconVehiclePositionInput>(key: K, value: ReconVehiclePositionInput[K]) { updateRequest((request) => { request.vehicle[key] = value; }); }
function toggleRoute(enabled: string | number | boolean) { updateRequest((request) => { request.route = enabled ? { waypoints: [structuredClone(request.vehicle), structuredClone(request.vehicle)], sample_interval_m: 50 } : null; }); }
function updateRouteSampleInterval(value: number) { updateRequest((request) => { if (!request.route) request.route = { waypoints: [structuredClone(request.vehicle), structuredClone(request.vehicle)], sample_interval_m: value }; else request.route.sample_interval_m = value; }); }
function updateRouteAction(action: SpatialDraftAction) { if (action.type !== "move" && action.type !== "remove") return; updateRequest((request) => { if (!request.route) return; if (action.type === "move" && request.route.waypoints[action.index]) { request.route.waypoints[action.index].lon = action.coordinate[0]; request.route.waypoints[action.index].lat = action.coordinate[1]; } else if (action.type === "remove") request.route.waypoints.splice(action.index, 1); }); }
function updateWaypoint<K extends keyof ReconVehiclePositionInput>(index: number, key: K, value: ReconVehiclePositionInput[K]) { updateRequest((request) => { if (request.route?.waypoints[index]) request.route.waypoints[index][key] = value; }); }
function updateSensor<K extends keyof ReconVehicleRequest["sensor"]>(key: K, value: ReconVehicleRequest["sensor"][K]) { updateRequest((request) => { request.sensor[key] = value; }); }
function updateSensorType(value: unknown) { if (value === "optical" || value === "thermal" || value === "radar" || value === "generic") updateSensor("sensor_type", value); }
function updateScanMode(value: unknown) { if (value === "omni" || value === "sector") updateSensor("scan_mode", value); }
function updateTargetHeight(height_m: number) { updateRequest((request) => { request.target.height_m = height_m; }); }
function updateAnalysis<K extends keyof ReconVehicleRequest["analysis"]>(key: K, value: ReconVehicleRequest["analysis"][K]) { updateRequest((request) => { request.analysis[key] = value; }); }
function updateTerrainOcclusion(value: string | number | boolean) { updateAnalysis("use_terrain_occlusion", Boolean(value)); }
function updateCurvature(value: string | number | boolean) { updateAnalysis("use_curvature", Boolean(value)); }
</script>

<style scoped>
.route-form,.form-section,.waypoint-details{display:grid;gap:12px;min-width:0}.route-form{padding:14px 14px 24px}.form-section{padding-bottom:16px;border-bottom:1px solid #ebeef5}.form-section:last-child{border-bottom:0}.form-section h3{margin:0;color:#303133;font-size:14px;letter-spacing:0}.section-heading,.map-actions{display:flex;align-items:center;justify-content:space-between;gap:8px}.map-actions{justify-content:flex-end;flex-wrap:wrap}.field-row{display:grid;grid-template-columns:minmax(110px,.9fr) minmax(0,1.1fr);align-items:center;gap:10px;color:#606266;font-size:12px}.input-with-unit{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:7px;min-width:0}.input-with-unit :deep(.el-input-number),.field-row :deep(.el-input),.field-row :deep(.el-select),.field-row :deep(.el-radio-group){width:100%}.unit{color:#909399;white-space:nowrap}.waypoint-details{padding:10px;border-left:3px solid #dcdfe6}.waypoint-details strong{font-size:12px}.field-error{margin:0;color:#b42318;font-size:12px;line-height:1.45}@media(max-width:600px){.section-heading{align-items:flex-start;flex-direction:column}.field-row{grid-template-columns:1fr}}
</style>
