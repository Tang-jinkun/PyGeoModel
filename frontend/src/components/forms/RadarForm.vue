<template>
  <form class="point-form" aria-label="雷达参数" @submit.prevent>
    <section class="form-section">
      <div class="section-heading">
        <h3>位置与目标</h3>
        <ElButton :icon="MapLocation" data-action="activate-map-tool" @click="emit('activate-map-tool')">
          地图选点
        </ElButton>
      </div>
      <label class="field-row">
        <span>高程模型 ID</span>
        <ElInput data-field="dem-id" :model-value="modelValue.dem_id" @update:model-value="updateDemId" />
      </label>
      <CoordinateEditor
        label="雷达站坐标"
        :model-value="[modelValue.radar.lon, modelValue.radar.lat]"
        @update:model-value="updateCoordinate"
      />
      <NumberField label="雷达架高" unit="米" field="radar-height" :value="modelValue.radar.height_m" @update="updateRadar('height_m', $event)" />
      <NumberField label="目标高度" unit="米" field="target-height" :value="modelValue.target.height_m" @update="updateTargetHeight" />
    </section>

    <section class="form-section">
      <h3>覆盖范围</h3>
      <NumberField label="最大探测距离" unit="米" field="max-range" :value="modelValue.coverage.max_range_m" :min="0" @update="updateCoverage('max_range_m', $event)" />
      <label class="field-row">
        <span>扫描模式</span>
        <ElRadioGroup data-field="scan-mode" :model-value="modelValue.coverage.scan_mode" @update:model-value="updateScanMode">
          <ElRadioButton value="omni">全向</ElRadioButton>
          <ElRadioButton value="sector">扇区</ElRadioButton>
        </ElRadioGroup>
      </label>
      <template v-if="modelValue.coverage.scan_mode === 'sector'">
        <NumberField label="中心方位角" unit="度" field="azimuth" :value="modelValue.coverage.azimuth_deg" @update="updateCoverage('azimuth_deg', $event)" />
        <NumberField label="水平波束宽度" unit="度" field="beam-width" :value="modelValue.coverage.beam_width_deg" :min="0" :max="360" @update="updateCoverage('beam_width_deg', $event)" />
      </template>
    </section>

    <section class="form-section">
      <h3>高级体积参数</h3>
      <SwitchField label="考虑地球曲率" field="use-curvature" :value="modelValue.advanced.use_curvature" @update="updateAdvanced('use_curvature', $event)" />
      <NumberField label="曲率系数" field="curvature-coeff" :value="modelValue.advanced.curvature_coeff" :step="0.05" @update="updateAdvanced('curvature_coeff', $event)" />
      <NullableNumberField label="轮廓简化容差" unit="米" field="simplify-tolerance" :value="modelValue.advanced.output_simplify_tolerance_m" @update="updateAdvanced('output_simplify_tolerance_m', $event)" />
      <NumberField label="体素网格尺寸" unit="格" field="voxel-grid-size" :value="modelValue.advanced.voxel_grid_size" :min="1" :step="1" @update="updateAdvanced('voxel_grid_size', $event)" />
      <NumberField label="垂直层数" unit="层" field="voxel-vertical-levels" :value="modelValue.advanced.voxel_vertical_levels" :min="1" :step="1" @update="updateAdvanced('voxel_vertical_levels', $event)" />
      <NumberField label="体素最大高度" unit="米" field="voxel-max-height" :value="modelValue.advanced.voxel_max_height_m" :min="0" @update="updateAdvanced('voxel_max_height_m', $event)" />
      <NumberField label="最小仰角" unit="度" field="min-elevation" :value="modelValue.advanced.min_elevation_deg" @update="updateAdvanced('min_elevation_deg', $event)" />
      <NumberField label="最大仰角" unit="度" field="max-elevation" :value="modelValue.advanced.max_elevation_deg" @update="updateAdvanced('max_elevation_deg', $event)" />
      <NumberField label="垂直波束宽度" unit="度" field="vertical-beam-width" :value="modelValue.advanced.vertical_beam_width_deg" :min="0" @update="updateAdvanced('vertical_beam_width_deg', $event)" />
      <SwitchField label="显示探测穹顶" field="visual-dome-mode" :value="modelValue.advanced.visual_dome_mode" @update="updateAdvanced('visual_dome_mode', $event)" />
      <label class="field-row">
        <span>高度分层</span>
        <div class="input-with-unit">
          <ElInput data-field="height-layers" :model-value="heightLayersText" placeholder="例如 100, 500, 1000" @update:model-value="updateHeightLayers" />
          <span class="unit">米</span>
        </div>
      </label>
    </section>

    <section class="form-section">
      <h3>雷达方程参数</h3>
      <NullableNumberField label="工作频率" unit="赫兹" field="frequency" :value="reserved.frequency_hz ?? null" @update="updateReserved('frequency_hz', $event)" />
      <NullableNumberField label="发射功率" unit="瓦" field="transmit-power" :value="reserved.transmit_power_w ?? null" @update="updateReserved('transmit_power_w', $event)" />
      <NullableNumberField label="天线增益" unit="分贝" field="antenna-gain" :value="reserved.antenna_gain_db ?? null" @update="updateReserved('antenna_gain_db', $event)" />
      <NullableNumberField label="接收灵敏度" unit="dBm" field="receiver-sensitivity" :value="reserved.receiver_sensitivity_dbm ?? null" @update="updateReserved('receiver_sensitivity_dbm', $event)" />
      <NullableNumberField label="目标雷达截面积" unit="平方米" field="target-rcs" :value="reserved.target_rcs_m2 ?? null" @update="updateReserved('target_rcs_m2', $event)" />
      <NullableNumberField label="系统损耗" unit="分贝" field="system-loss" :value="reserved.system_loss_db ?? null" @update="updateReserved('system_loss_db', $event)" />
      <NullableNumberField label="脉冲宽度" unit="秒" field="pulse-width" :value="reserved.pulse_width_s ?? null" @update="updateReserved('pulse_width_s', $event)" />
      <NullableNumberField label="脉冲重复频率" unit="赫兹" field="prf" :value="reserved.prf_hz ?? null" @update="updateReserved('prf_hz', $event)" />
      <NullableNumberField label="噪声系数" unit="分贝" field="noise-figure" :value="reserved.noise_figure_db ?? null" @update="updateReserved('noise_figure_db', $event)" />
      <NullableNumberField label="检测概率" field="detection-probability" :value="reserved.detection_probability ?? null" :step="0.01" @update="updateReserved('detection_probability', $event)" />
      <NullableNumberField label="虚警概率" field="false-alarm-probability" :value="reserved.false_alarm_probability ?? null" :step="0.000001" @update="updateReserved('false_alarm_probability', $event)" />
    </section>
  </form>
</template>

<script setup lang="ts">
import { MapLocation } from "@element-plus/icons-vue";
import { ElButton, ElInput, ElInputNumber, ElRadioButton, ElRadioGroup, ElSwitch } from "element-plus";
import { computed, defineComponent, h, type PropType } from "vue";

import type { SpatialCoordinate } from "../../map/spatialInput";
import type { RadarRequest, ReservedRadarParams } from "../../models/radar/types";
import CoordinateEditor from "../map/CoordinateEditor.vue";

const props = defineProps<{ modelValue: RadarRequest }>();
const emit = defineEmits<{
  "update:modelValue": [request: RadarRequest];
  "activate-map-tool": [];
}>();

const reserved = computed(() => props.modelValue.reserved_radar_params ?? {});
const heightLayersText = computed(() => props.modelValue.advanced.height_layers_m.join(", "));

const NumberField = createNumberField(false);
const NullableNumberField = createNumberField(true);
const SwitchField = defineComponent({
  props: { label: { type: String, required: true }, field: { type: String, required: true }, value: { type: Boolean, required: true } },
  emits: ["update"],
  setup(componentProps, { emit: componentEmit }) {
    return () => h("label", { class: "field-row" }, [
      h("span", componentProps.label),
      h(ElSwitch, { "data-field": componentProps.field, modelValue: componentProps.value, "onUpdate:modelValue": (value: string | number | boolean) => componentEmit("update", Boolean(value)) })
    ]);
  }
});

function createNumberField(nullable: boolean) {
  return defineComponent({
    props: {
      label: { type: String, required: true }, unit: { type: String, default: "" }, field: { type: String, required: true },
      value: { type: Number as PropType<number | null>, default: null }, min: { type: Number, default: undefined }, max: { type: Number, default: undefined }, step: { type: Number, default: 1 }
    },
    emits: ["update"],
    setup(componentProps, { emit: componentEmit }) {
      return () => h("label", { class: "field-row" }, [
        h("span", componentProps.label),
        h("div", { class: "input-with-unit" }, [
          h(ElInputNumber, {
            "data-field": componentProps.field, modelValue: componentProps.value ?? undefined, min: componentProps.min,
            max: componentProps.max, step: componentProps.step, controlsPosition: "right",
            "onUpdate:modelValue": (value: number | undefined) => componentEmit("update", nullable ? value ?? null : value ?? 0)
          }),
          componentProps.unit ? h("span", { class: "unit" }, componentProps.unit) : null
        ])
      ]);
    }
  });
}

function emitRequest(request: RadarRequest) { emit("update:modelValue", request); }
function updateDemId(dem_id: string) { emitRequest({ ...props.modelValue, dem_id }); }
function updateCoordinate(coordinate: SpatialCoordinate | null) {
  if (!coordinate) return;
  emitRequest({ ...props.modelValue, radar: { ...props.modelValue.radar, lon: coordinate[0], lat: coordinate[1] } });
}
function updateRadar<K extends keyof RadarRequest["radar"]>(key: K, value: RadarRequest["radar"][K]) {
  emitRequest({ ...props.modelValue, radar: { ...props.modelValue.radar, [key]: value } });
}
function updateTargetHeight(height_m: number) { emitRequest({ ...props.modelValue, target: { ...props.modelValue.target, height_m } }); }
function updateCoverage<K extends keyof RadarRequest["coverage"]>(key: K, value: RadarRequest["coverage"][K]) {
  emitRequest({ ...props.modelValue, coverage: { ...props.modelValue.coverage, [key]: value } });
}
function updateScanMode(value: string | number | boolean | undefined) {
  if (value === "omni" || value === "sector") updateCoverage("scan_mode", value);
}
function updateAdvanced<K extends keyof RadarRequest["advanced"]>(key: K, value: RadarRequest["advanced"][K]) {
  emitRequest({ ...props.modelValue, advanced: { ...props.modelValue.advanced, [key]: value } });
}
function updateHeightLayers(value: string) {
  const layers = value.split(/[,，\s]+/).filter(Boolean).map(Number).filter(Number.isFinite);
  updateAdvanced("height_layers_m", layers);
}
function updateReserved<K extends keyof ReservedRadarParams>(key: K, value: ReservedRadarParams[K]) {
  emitRequest({ ...props.modelValue, reserved_radar_params: { ...reserved.value, [key]: value } });
}
</script>

<style scoped>
.point-form, .form-section { display: grid; gap: 12px; min-width: 0; }
.point-form { padding: 14px 14px 24px; }
.form-section { padding-bottom: 16px; border-bottom: 1px solid #ebeef5; }
.form-section:last-child { border-bottom: 0; }
.form-section h3 { margin: 0; color: #303133; font-size: 14px; letter-spacing: 0; }
.section-heading { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.field-row { display: grid; grid-template-columns: minmax(94px, 0.9fr) minmax(0, 1.1fr); align-items: center; gap: 10px; color: #606266; font-size: 12px; }
.input-with-unit { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 7px; min-width: 0; }
.input-with-unit :deep(.el-input-number), .field-row :deep(.el-input), .field-row :deep(.el-radio-group) { width: 100%; }
.unit { color: #909399; white-space: nowrap; }
</style>
