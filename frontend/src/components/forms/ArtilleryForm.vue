<template>
  <form class="point-form" aria-label="火炮参数" @submit.prevent>
    <section class="form-section">
      <div class="section-heading"><h3>阵地与目标</h3><ElButton :icon="MapLocation" data-action="activate-map-tool" @click="emit('activate-map-tool')">地图选点</ElButton></div>
      <label class="field-row"><span>高程模型 ID</span><ElInput data-field="dem-id" :model-value="modelValue.dem_id" @update:model-value="updateDemId" /></label>
      <CoordinateEditor label="火炮阵地坐标" :model-value="[modelValue.battery.lon, modelValue.battery.lat]" @update:model-value="updateCoordinate" />
      <NumberRow label="阵地高度" unit="米" field="battery-height" :value="modelValue.battery.height_m" @update="updateBattery('height_m', $event)" />
      <label class="field-row"><span>高度模式</span><ElRadioGroup data-field="altitude-mode" :model-value="modelValue.battery.altitude_mode" @update:model-value="updateAltitudeMode"><ElRadioButton value="agl">离地高度</ElRadioButton><ElRadioButton value="amsl">海拔高度</ElRadioButton></ElRadioGroup></label>
      <NumberRow label="目标高度" unit="米" field="target-height" :value="modelValue.target.target_height_m" @update="updateTargetHeight" />
    </section>

    <section class="form-section">
      <h3>武器参数</h3>
      <NumberRow label="最小射程" unit="米" field="min-range" :value="modelValue.weapon.min_range_m" @update="updateWeapon('min_range_m', $event)" />
      <NumberRow label="最大射程" unit="米" field="max-range" :value="modelValue.weapon.max_range_m" @update="updateWeapon('max_range_m', $event)" />
      <NumberRow label="射向方位角" unit="度" field="azimuth" :value="modelValue.weapon.azimuth_deg" @update="updateWeapon('azimuth_deg', $event)" />
      <NumberRow label="方向射界" unit="度" field="traverse" :value="modelValue.weapon.traverse_deg" @update="updateWeapon('traverse_deg', $event)" />
      <NumberRow label="初速" unit="米/秒" field="muzzle-velocity" :value="modelValue.weapon.muzzle_velocity_mps" @update="updateWeapon('muzzle_velocity_mps', $event)" />
      <NumberRow label="射角" unit="度" field="elevation" :value="modelValue.weapon.elevation_deg" @update="updateWeapon('elevation_deg', $event)" />
    </section>

    <section class="form-section">
      <h3>弹药参数</h3>
      <label class="field-row field-row--stack"><span>弹药类型</span><ElRadioGroup data-field="munition-type" :model-value="modelValue.munition.munition_type" @update:model-value="updateMunitionType"><ElRadioButton value="he">高爆弹</ElRadioButton><ElRadioButton value="smoke">烟幕弹</ElRadioButton><ElRadioButton value="illumination">照明弹</ElRadioButton><ElRadioButton value="generic">通用</ElRadioButton></ElRadioGroup></label>
      <NumberRow label="致命半径" unit="米" field="lethal-radius" :value="modelValue.munition.lethal_radius_m" @update="updateMunition('lethal_radius_m', $event)" />
      <NumberRow label="有效半径" unit="米" field="effective-radius" :value="modelValue.munition.effective_radius_m" @update="updateMunition('effective_radius_m', $event)" />
    </section>

    <section class="form-section">
      <h3>分析参数</h3>
      <label class="field-row"><span>使用 DEM 高程</span><ElSwitch data-field="use-dem-elevation" :model-value="modelValue.analysis.use_dem_elevation" @update:model-value="updateDemElevation" /></label>
      <label class="field-row"><span>启用地形遮蔽</span><ElSwitch data-field="use-terrain-masking" :model-value="modelValue.analysis.use_terrain_masking" @update:model-value="updateTerrainMasking" /></label>
      <NumberRow label="采样分辨率" unit="米" field="sample-resolution" :value="modelValue.analysis.sample_resolution_m" nullable @update="updateAnalysis('sample_resolution_m', $event)" />
      <NumberRow label="弹道采样数" unit="点" field="trajectory-samples" :value="modelValue.analysis.trajectory_samples" :step="1" @update="updateAnalysis('trajectory_samples', $event)" />
      <NumberRow label="净空余量" unit="米" field="clearance-margin" :value="modelValue.analysis.clearance_margin_m" @update="updateAnalysis('clearance_margin_m', $event)" />
      <NumberRow label="轮廓简化容差" unit="米" field="simplify-tolerance" :value="modelValue.analysis.output_simplify_tolerance_m" nullable @update="updateAnalysis('output_simplify_tolerance_m', $event)" />
    </section>
  </form>
</template>

<script setup lang="ts">
import { MapLocation } from "@element-plus/icons-vue";
import { ElButton, ElInput, ElInputNumber, ElRadioButton, ElRadioGroup, ElSwitch } from "element-plus";
import { defineComponent, h, toRaw, type PropType } from "vue";
import type { SpatialCoordinate } from "../../map/spatialInput";
import type { ArtilleryRequest } from "../../models/artillery/types";
import CoordinateEditor from "../map/CoordinateEditor.vue";

const props = defineProps<{ modelValue: ArtilleryRequest }>();
const emit = defineEmits<{ "update:modelValue": [request: ArtilleryRequest]; "activate-map-tool": [] }>();
const NumberRow = defineComponent({
  props: { label: { type: String, required: true }, unit: { type: String, default: "" }, field: { type: String, required: true }, value: { type: Number as PropType<number | null>, default: null }, step: { type: Number, default: 1 }, nullable: Boolean }, emits: ["update"],
  setup(componentProps, { emit: componentEmit }) { return () => h("label", { class: "field-row" }, [h("span", componentProps.label), h("div", { class: "input-with-unit" }, [h(ElInputNumber, { "data-field": componentProps.field, modelValue: componentProps.value ?? undefined, step: componentProps.step, controlsPosition: "right", "onUpdate:modelValue": (value: number | undefined) => componentEmit("update", componentProps.nullable ? value ?? null : value ?? 0) }), componentProps.unit ? h("span", { class: "unit" }, componentProps.unit) : null])]); }
});

function updateRequest(mutator: (request: ArtilleryRequest) => void) {
  const request = structuredClone(toRaw(props.modelValue));
  mutator(request);
  emit("update:modelValue", request);
}
function updateDemId(dem_id: string) { updateRequest((request) => { request.dem_id = dem_id; }); }
function updateCoordinate(coordinate: SpatialCoordinate | null) {
  if (!coordinate) return;
  updateRequest((request) => {
    request.battery.lon = coordinate[0];
    request.battery.lat = coordinate[1];
  });
}
function updateBattery<K extends keyof ArtilleryRequest["battery"]>(key: K, value: ArtilleryRequest["battery"][K]) { updateRequest((request) => { request.battery[key] = value; }); }
function updateAltitudeMode(value: string | number | boolean | undefined) { if (value === "agl" || value === "amsl") updateBattery("altitude_mode", value); }
function updateTargetHeight(target_height_m: number) { updateRequest((request) => { request.target.target_height_m = target_height_m; }); }
function updateWeapon<K extends keyof ArtilleryRequest["weapon"]>(key: K, value: ArtilleryRequest["weapon"][K]) { updateRequest((request) => { request.weapon[key] = value; }); }
function updateMunition<K extends keyof ArtilleryRequest["munition"]>(key: K, value: ArtilleryRequest["munition"][K]) { updateRequest((request) => { request.munition[key] = value; }); }
function updateMunitionType(value: string | number | boolean | undefined) { if (value === "he" || value === "smoke" || value === "illumination" || value === "generic") updateMunition("munition_type", value); }
function updateDemElevation(value: string | number | boolean) { updateAnalysis("use_dem_elevation", Boolean(value)); }
function updateTerrainMasking(value: string | number | boolean) { updateAnalysis("use_terrain_masking", Boolean(value)); }
function updateAnalysis<K extends keyof ArtilleryRequest["analysis"]>(key: K, value: ArtilleryRequest["analysis"][K]) { updateRequest((request) => { request.analysis[key] = value; }); }
</script>

<style scoped>
.point-form, .form-section { display: grid; gap: 12px; min-width: 0; }.point-form { padding: 14px 14px 24px; }.form-section { padding-bottom: 16px; border-bottom: 1px solid #ebeef5; }.form-section:last-child { border-bottom: 0; }.form-section h3 { margin: 0; color: #303133; font-size: 14px; letter-spacing: 0; }.section-heading { display: flex; align-items: center; justify-content: space-between; gap: 8px; }.field-row { display: grid; grid-template-columns: minmax(94px, .9fr) minmax(0, 1.1fr); align-items: center; gap: 10px; color: #606266; font-size: 12px; }.field-row--stack { grid-template-columns: 1fr; }.input-with-unit { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 7px; min-width: 0; }.input-with-unit :deep(.el-input-number), .field-row :deep(.el-input), .field-row :deep(.el-radio-group) { width: 100%; }.field-row--stack :deep(.el-radio-group) { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }.field-row--stack :deep(.el-radio-button__inner) { width: 100%; }.unit { color: #909399; white-space: nowrap; }
</style>
