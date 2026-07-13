<template>
  <form class="point-form" aria-label="观察哨参数" @submit.prevent>
    <section class="form-section">
      <div class="section-heading">
        <h3>观察位置与目标</h3>
        <ElButton :icon="MapLocation" data-action="activate-map-tool" @click="emit('activate-map-tool')">地图选点</ElButton>
      </div>
      <label class="field-row"><span>高程模型 ID</span><ElInput data-field="dem-id" :model-value="modelValue.dem_id" @update:model-value="updateDemId" /></label>
      <CoordinateEditor label="观察哨坐标" :model-value="[modelValue.observer.lon, modelValue.observer.lat]" @update:model-value="updateCoordinate" />
      <NumberRow label="观察高度" unit="米" field="observer-height" :value="modelValue.observer.height_m" @update="updateObserverHeight" />
      <NumberRow label="目标高度" unit="米" field="target-height" :value="modelValue.target.height_m" @update="updateTargetHeight" />
    </section>

    <section class="form-section">
      <h3>覆盖范围</h3>
      <NumberRow label="最大探测距离" unit="米" field="max-range" :value="modelValue.coverage.max_range_m" @update="updateCoverage('max_range_m', $event)" />
      <label class="field-row">
        <span>扫描模式</span>
        <ElRadioGroup data-field="scan-mode" :model-value="modelValue.coverage.scan_mode" @update:model-value="updateScanMode">
          <ElRadioButton value="omni">全向</ElRadioButton><ElRadioButton value="sector">扇区</ElRadioButton>
        </ElRadioGroup>
      </label>
      <NumberRow label="中心方位角" unit="度" field="azimuth" :value="modelValue.coverage.azimuth_deg" @update="updateCoverage('azimuth_deg', $event)" />
      <NumberRow label="观察角" unit="度" field="view-angle" :value="modelValue.coverage.view_angle_deg" @update="updateCoverage('view_angle_deg', $event)" />
    </section>

    <section class="form-section">
      <h3>分析参数</h3>
      <label class="field-row"><span>考虑地球曲率</span><ElSwitch data-field="use-curvature" :model-value="modelValue.analysis.use_curvature" @update:model-value="updateCurvature" /></label>
      <NumberRow label="曲率系数" field="curvature-coeff" :value="modelValue.analysis.curvature_coeff" :step="0.05" @update="updateAnalysis('curvature_coeff', $event)" />
      <NumberRow label="轮廓简化容差" unit="米" field="simplify-tolerance" :value="modelValue.analysis.output_simplify_tolerance_m" nullable @update="updateAnalysis('output_simplify_tolerance_m', $event)" />
    </section>
  </form>
</template>

<script setup lang="ts">
import { MapLocation } from "@element-plus/icons-vue";
import { ElButton, ElInput, ElInputNumber, ElRadioButton, ElRadioGroup, ElSwitch } from "element-plus";
import { defineComponent, h, toRaw, type PropType } from "vue";
import type { SpatialCoordinate } from "../../map/spatialInput";
import type { WatchpostRequest } from "../../models/watchpost/types";
import CoordinateEditor from "../map/CoordinateEditor.vue";

const props = defineProps<{ modelValue: WatchpostRequest }>();
const emit = defineEmits<{ "update:modelValue": [request: WatchpostRequest]; "activate-map-tool": [] }>();

const NumberRow = defineComponent({
  props: { label: { type: String, required: true }, unit: { type: String, default: "" }, field: { type: String, required: true }, value: { type: Number as PropType<number | null>, default: null }, step: { type: Number, default: 1 }, nullable: Boolean },
  emits: ["update"],
  setup(componentProps, { emit: componentEmit }) {
    return () => h("label", { class: "field-row" }, [h("span", componentProps.label), h("div", { class: "input-with-unit" }, [
      h(ElInputNumber, { "data-field": componentProps.field, modelValue: componentProps.value ?? undefined, step: componentProps.step, controlsPosition: "right", "onUpdate:modelValue": (value: number | undefined) => componentEmit("update", componentProps.nullable ? value ?? null : value ?? 0) }),
      componentProps.unit ? h("span", { class: "unit" }, componentProps.unit) : null
    ])]);
  }
});

function updateRequest(mutator: (request: WatchpostRequest) => void) {
  const request = structuredClone(toRaw(props.modelValue));
  mutator(request);
  emit("update:modelValue", request);
}
function updateDemId(dem_id: string) { updateRequest((request) => { request.dem_id = dem_id; }); }
function updateCoordinate(coordinate: SpatialCoordinate | null) {
  if (!coordinate) return;
  updateRequest((request) => {
    request.observer.lon = coordinate[0];
    request.observer.lat = coordinate[1];
  });
}
function updateObserverHeight(height_m: number) { updateRequest((request) => { request.observer.height_m = height_m; }); }
function updateTargetHeight(height_m: number) { updateRequest((request) => { request.target.height_m = height_m; }); }
function updateCoverage<K extends keyof WatchpostRequest["coverage"]>(key: K, value: WatchpostRequest["coverage"][K]) { updateRequest((request) => { request.coverage[key] = value; }); }
function updateScanMode(value: string | number | boolean | undefined) { if (value === "omni" || value === "sector") updateCoverage("scan_mode", value); }
function updateCurvature(value: string | number | boolean) { updateAnalysis("use_curvature", Boolean(value)); }
function updateAnalysis<K extends keyof WatchpostRequest["analysis"]>(key: K, value: WatchpostRequest["analysis"][K]) { updateRequest((request) => { request.analysis[key] = value; }); }
</script>

<style scoped>
.point-form, .form-section { display: grid; gap: 12px; min-width: 0; }.point-form { padding: 14px 14px 24px; }.form-section { padding-bottom: 16px; border-bottom: 1px solid #ebeef5; }.form-section:last-child { border-bottom: 0; }.form-section h3 { margin: 0; color: #303133; font-size: 14px; letter-spacing: 0; }.section-heading { display: flex; align-items: center; justify-content: space-between; gap: 8px; }.field-row { display: grid; grid-template-columns: minmax(94px, .9fr) minmax(0, 1.1fr); align-items: center; gap: 10px; color: #606266; font-size: 12px; }.input-with-unit { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 7px; min-width: 0; }.input-with-unit :deep(.el-input-number), .field-row :deep(.el-input), .field-row :deep(.el-radio-group) { width: 100%; }.unit { color: #909399; white-space: nowrap; }
</style>
