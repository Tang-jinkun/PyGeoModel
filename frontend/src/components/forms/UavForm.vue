<template>
  <form class="route-form" aria-label="无人机侦察参数" @submit.prevent>
    <section class="form-section">
      <div class="section-heading">
        <h3>平台与航线</h3>
        <div class="map-actions">
          <ElButton :icon="MapLocation" data-action="activate-point-tool" @click="emit('activate-map-tool', 'point')">地图选点</ElButton>
          <ElButton :icon="Position" data-action="activate-route-tool" @click="emit('activate-map-tool', 'route')">地图绘制航线</ElButton>
        </div>
      </div>
      <label class="field-row"><span>高程模型 ID</span><ElInput data-field="dem-id" :model-value="modelValue.dem_id" @update:model-value="updateDemId" /></label>
      <div data-coordinate="uav"><CoordinateEditor label="无人机坐标" :model-value="[modelValue.uav.lon, modelValue.uav.lat]" @update:model-value="updateUavCoordinate" /></div>
      <NumberRow label="飞行高度" unit="米" field="uav-altitude" :value="modelValue.uav.altitude_m" @update="updateUav('altitude_m', $event)" />
      <label class="field-row"><span>高度模式</span><ElRadioGroup data-field="uav-altitude-mode" :model-value="modelValue.uav.altitude_mode" @update:model-value="updateAltitudeMode"><ElRadioButton value="agl">离地高度</ElRadioButton><ElRadioButton value="amsl">海拔高度</ElRadioButton></ElRadioGroup></label>
      <NumberRow label="航向角" unit="度" field="uav-heading" :value="modelValue.uav.heading_deg" @update="updateUav('heading_deg', $event)" />
      <NumberRow label="俯仰角" unit="度" field="uav-pitch" :value="modelValue.uav.pitch_deg" @update="updateUav('pitch_deg', $event)" />
      <NumberRow label="横滚角" unit="度" field="uav-roll" :value="modelValue.uav.roll_deg" @update="updateUav('roll_deg', $event)" />
      <label class="field-row"><span>启用航线</span><ElSwitch data-field="route-enabled" :model-value="modelValue.route !== null" @update:model-value="toggleRoute" /></label>
      <NumberRow label="航线采样间隔" unit="米" field="route-sample-interval" :value="modelValue.route?.sample_interval_m ?? 50" @update="updateRouteSampleInterval" />
      <template v-if="modelValue.route">
        <RouteEditor :model-value="routePoints" @spatial-edit="updateRouteAction" />
        <div v-for="(waypoint, index) in modelValue.route.waypoints" :key="index" class="waypoint-details">
          <strong>航点 {{ index + 1 }}</strong>
          <NumberRow label="飞行高度" unit="米" :field="`waypoint-altitude-${index}`" :value="waypoint.altitude_m" @update="updateWaypoint(index, 'altitude_m', $event)" />
          <label class="field-row"><span>高度模式</span><ElRadioGroup :data-field="`waypoint-altitude-mode-${index}`" :model-value="waypoint.altitude_mode" @update:model-value="updateWaypointAltitudeMode(index, $event)"><ElRadioButton value="agl">离地高度</ElRadioButton><ElRadioButton value="amsl">海拔高度</ElRadioButton></ElRadioGroup></label>
          <NumberRow label="航向角" unit="度" :field="`waypoint-heading-${index}`" :value="waypoint.heading_deg" @update="updateWaypoint(index, 'heading_deg', $event)" />
          <NumberRow label="俯仰角" unit="度" :field="`waypoint-pitch-${index}`" :value="waypoint.pitch_deg" @update="updateWaypoint(index, 'pitch_deg', $event)" />
          <NumberRow label="横滚角" unit="度" :field="`waypoint-roll-${index}`" :value="waypoint.roll_deg" @update="updateWaypoint(index, 'roll_deg', $event)" />
        </div>
      </template>
    </section>

    <section class="form-section">
      <h3>传感器</h3>
      <label class="field-row"><span>传感器类型</span><ElSelect data-field="sensor-type" :model-value="modelValue.sensor.sensor_type" @update:model-value="updateSensorType"><ElOption label="可见光相机" value="camera" /><ElOption label="热成像" value="thermal" /><ElOption label="光电" value="eo" /></ElSelect></label>
      <NumberRow label="水平视场角" unit="度" field="horizontal-fov" :value="modelValue.sensor.h_fov_deg" @update="updateSensor('h_fov_deg', $event)" />
      <NumberRow label="垂直视场角" unit="度" field="vertical-fov" :value="modelValue.sensor.v_fov_deg" @update="updateSensor('v_fov_deg', $event)" />
      <NumberRow label="最大探测距离" unit="米" field="sensor-max-range" :value="modelValue.sensor.max_range_m" @update="updateSensor('max_range_m', $event)" />
      <NumberRow label="最小探测距离" unit="米" field="sensor-min-range" :value="modelValue.sensor.min_range_m" @update="updateSensor('min_range_m', $event)" />
      <NumberRow label="地面分辨率" unit="米" field="ground-resolution" :value="modelValue.sensor.ground_resolution_m" nullable @update="updateSensor('ground_resolution_m', $event)" />
    </section>

    <section class="form-section">
      <h3>分析参数</h3>
      <NumberRow label="目标高度" unit="米" field="target-height" :value="modelValue.analysis.target_height_m" @update="updateAnalysis('target_height_m', $event)" />
      <label class="field-row"><span>启用地形遮蔽</span><ElSwitch data-field="terrain-occlusion" :model-value="modelValue.analysis.use_terrain_occlusion" @update:model-value="updateTerrainOcclusion" /></label>
      <NumberRow label="采样分辨率" unit="米" field="sample-resolution" :value="modelValue.analysis.sample_resolution_m" nullable @update="updateAnalysis('sample_resolution_m', $event)" />
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
import { uavDefinition } from "../../models/uav/definition";
import type { UavPlatformInput, UavRequest } from "../../models/uav/types";
import CoordinateEditor from "../map/CoordinateEditor.vue";
import RouteEditor from "../map/RouteEditor.vue";

const props = defineProps<{ modelValue: UavRequest }>();
const emit = defineEmits<{ "update:modelValue": [request: UavRequest]; "activate-map-tool": [operation: "point" | "route"] }>();
const NumberRow = defineComponent({
  props: { label: { type: String, required: true }, unit: { type: String, default: "" }, field: { type: String, required: true }, value: { type: Number as PropType<number | null>, default: null }, nullable: Boolean }, emits: ["update"],
  setup(componentProps, { emit: componentEmit }) { return () => h("label", { class: "field-row" }, [h("span", componentProps.label), h("div", { class: "input-with-unit" }, [h(ElInputNumber, { "data-field": componentProps.field, modelValue: componentProps.value ?? undefined, controlsPosition: "right", "onUpdate:modelValue": (value: number | undefined) => componentEmit("update", componentProps.nullable ? value ?? null : value ?? 0) }), componentProps.unit ? h("span", { class: "unit" }, componentProps.unit) : null])]); }
});

const routePoints = computed<SpatialCoordinate[]>(() => props.modelValue.route?.waypoints.map(({ lon, lat }) => [lon, lat]) ?? []);
const localizedIssues = computed(() => uavDefinition.validate(props.modelValue).map((issue) => issue.path === "route.waypoints" ? { ...issue, message: "航线至少包含两个航点" } : issue.path === "sensor.max_range_m" ? { ...issue, message: "最小探测距离必须小于最大探测距离" } : issue));

function updateRequest(mutator: (request: UavRequest) => void) { const request = structuredClone(toRaw(props.modelValue)); mutator(request); emit("update:modelValue", request); }
function updateDemId(dem_id: string) { updateRequest((request) => { request.dem_id = dem_id; }); }
function updateUavCoordinate(coordinate: SpatialCoordinate | null) { if (coordinate) updateRequest((request) => { request.uav.lon = coordinate[0]; request.uav.lat = coordinate[1]; }); }
function updateUav<K extends keyof UavPlatformInput>(key: K, value: UavPlatformInput[K]) { updateRequest((request) => { request.uav[key] = value; }); }
function updateAltitudeMode(value: unknown) { if (value === "agl" || value === "amsl") updateUav("altitude_mode", value); }
function toggleRoute(enabled: string | number | boolean) { updateRequest((request) => { request.route = enabled ? { waypoints: [structuredClone(request.uav), structuredClone(request.uav)], sample_interval_m: 50 } : null; }); }
function updateRouteSampleInterval(value: number) { updateRequest((request) => { if (!request.route) request.route = { waypoints: [structuredClone(request.uav), structuredClone(request.uav)], sample_interval_m: value }; else request.route.sample_interval_m = value; }); }
function updateRouteAction(action: SpatialDraftAction) { if (action.type !== "move" && action.type !== "remove") return; updateRequest((request) => { if (!request.route) return; if (action.type === "move" && request.route.waypoints[action.index]) { request.route.waypoints[action.index].lon = action.coordinate[0]; request.route.waypoints[action.index].lat = action.coordinate[1]; } else if (action.type === "remove") request.route.waypoints.splice(action.index, 1); }); }
function updateWaypoint<K extends keyof UavPlatformInput>(index: number, key: K, value: UavPlatformInput[K]) { updateRequest((request) => { if (request.route?.waypoints[index]) request.route.waypoints[index][key] = value; }); }
function updateWaypointAltitudeMode(index: number, value: unknown) { if (value === "agl" || value === "amsl") updateWaypoint(index, "altitude_mode", value); }
function updateSensor<K extends keyof UavRequest["sensor"]>(key: K, value: UavRequest["sensor"][K]) { updateRequest((request) => { request.sensor[key] = value; }); }
function updateSensorType(value: unknown) { if (value === "camera" || value === "thermal" || value === "eo") updateSensor("sensor_type", value); }
function updateAnalysis<K extends keyof UavRequest["analysis"]>(key: K, value: UavRequest["analysis"][K]) { updateRequest((request) => { request.analysis[key] = value; }); }
function updateTerrainOcclusion(value: string | number | boolean) { updateAnalysis("use_terrain_occlusion", Boolean(value)); }
</script>

<style scoped>
.route-form,.form-section,.waypoint-details{display:grid;gap:12px;min-width:0}.route-form{padding:14px 14px 24px}.form-section{padding-bottom:16px;border-bottom:1px solid #ebeef5}.form-section:last-child{border-bottom:0}.form-section h3{margin:0;color:#303133;font-size:14px;letter-spacing:0}.section-heading,.map-actions{display:flex;align-items:center;justify-content:space-between;gap:8px}.map-actions{justify-content:flex-end;flex-wrap:wrap}.field-row{display:grid;grid-template-columns:minmax(110px,.9fr) minmax(0,1.1fr);align-items:center;gap:10px;color:#606266;font-size:12px}.input-with-unit{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:7px;min-width:0}.input-with-unit :deep(.el-input-number),.field-row :deep(.el-input),.field-row :deep(.el-select),.field-row :deep(.el-radio-group){width:100%}.unit{color:#909399;white-space:nowrap}.waypoint-details{padding:10px;border-left:3px solid #dcdfe6}.waypoint-details strong{font-size:12px}.field-error{margin:0;color:#b42318;font-size:12px;line-height:1.45}@media(max-width:600px){.section-heading{align-items:flex-start;flex-direction:column}.field-row{grid-template-columns:1fr}}
</style>
