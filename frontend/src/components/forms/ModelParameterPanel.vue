<template>
  <section class="model-parameter-panel" :data-model-id="modelId">
    <div class="model-parameter-panel__body">
      <component
        :is="activeForm"
        :model-value="modelValue"
        @update:model-value="updateModelValue"
        @activate-map-tool="forwardMapTool"
      />
    </div>

    <footer class="model-parameter-panel__footer">
      <div v-if="issues.length" class="validation-issues" data-validation-issues role="alert">
        <strong>请检查以下参数</strong>
        <ul><li v-for="issue in issues" :key="`${issue.path}:${issue.message}`">{{ issue.message }}</li></ul>
      </div>
      <ElButton type="primary" :icon="VideoPlay" :loading="submitting" data-action="submit" @click="submit">
        运行分析
      </ElButton>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { VideoPlay } from "@element-plus/icons-vue";
import { ElButton } from "element-plus";
import { computed, ref, toRaw, type Component } from "vue";
import { airCorridorDefinition } from "../../models/airCorridor/definition";
import type { AirCorridorRequest } from "../../models/airCorridor/types";
import { artilleryDefinition } from "../../models/artillery/definition";
import type { ArtilleryRequest } from "../../models/artillery/types";
import { mobilityDefinition } from "../../models/mobility/definition";
import type { MobilityRequest } from "../../models/mobility/types";
import { radarDefinition } from "../../models/radar/definition";
import type { RadarRequest } from "../../models/radar/types";
import { reconVehicleDefinition } from "../../models/reconVehicle/definition";
import type { ReconVehicleRequest } from "../../models/reconVehicle/types";
import type { ValidationIssue } from "../../models/shared";
import { uavDefinition } from "../../models/uav/definition";
import type { UavRequest } from "../../models/uav/types";
import { watchpostDefinition } from "../../models/watchpost/definition";
import type { WatchpostRequest } from "../../models/watchpost/types";
import AirCorridorForm from "./AirCorridorForm.vue";
import ArtilleryForm from "./ArtilleryForm.vue";
import MobilityForm from "./MobilityForm.vue";
import RadarForm from "./RadarForm.vue";
import ReconVehicleForm from "./ReconVehicleForm.vue";
import UavForm from "./UavForm.vue";
import WatchpostForm from "./WatchpostForm.vue";

type FormModelId = "radar" | "uav" | "watchpost" | "artillery" | "reconVehicle" | "mobility" | "airCorridor";
type FormModelRequest = RadarRequest | UavRequest | WatchpostRequest | ArtilleryRequest | ReconVehicleRequest | MobilityRequest | AirCorridorRequest;
type MapToolOperation = "point" | "route" | "start" | "end" | "threat";

const props = withDefaults(defineProps<{ modelId: FormModelId; modelValue: FormModelRequest; submitting?: boolean }>(), { submitting: false });
const emit = defineEmits<{ "update:modelValue": [request: FormModelRequest]; submit: [request: FormModelRequest]; "activate-map-tool": [operation?: MapToolOperation] }>();
const issues = ref<ValidationIssue[]>([]);
const forms: Record<FormModelId, Component> = {
  radar: RadarForm,
  uav: UavForm,
  watchpost: WatchpostForm,
  artillery: ArtilleryForm,
  reconVehicle: ReconVehicleForm,
  mobility: MobilityForm,
  airCorridor: AirCorridorForm
};
const activeForm = computed(() => forms[props.modelId]);

function updateModelValue(request: FormModelRequest) {
  issues.value = [];
  emit("update:modelValue", structuredClone(toRaw(request)));
}

function forwardMapTool(operation?: MapToolOperation) {
  emit("activate-map-tool", operation);
}

function submit() {
  issues.value = validateActiveRequest();
  if (issues.value.length === 0) emit("submit", structuredClone(toRaw(props.modelValue)));
}

function validateActiveRequest(): ValidationIssue[] {
  if (props.modelId === "radar") return localizeIssues(radarDefinition.validate(props.modelValue as RadarRequest));
  if (props.modelId === "artillery") return localizeIssues(artilleryDefinition.validate(props.modelValue as ArtilleryRequest));
  if (props.modelId === "watchpost") return localizeIssues(watchpostDefinition.validate(props.modelValue as WatchpostRequest));
  if (props.modelId === "uav") return localizeIssues(uavDefinition.validate(props.modelValue as UavRequest));
  if (props.modelId === "reconVehicle") return localizeIssues(reconVehicleDefinition.validate(props.modelValue as ReconVehicleRequest));
  if (props.modelId === "mobility") return localizeIssues(mobilityDefinition.validate(props.modelValue as MobilityRequest));
  return localizeIssues(airCorridorDefinition.validate(props.modelValue as AirCorridorRequest));
}

function localizeIssues(source: ValidationIssue[]): ValidationIssue[] {
  return source.map((issue) => {
    if (issue.path === "weapon.max_range_m") return { ...issue, message: "最小射程必须小于最大射程" };
    if (issue.path === "advanced.max_elevation_deg") return { ...issue, message: "最大仰角必须大于或等于最小仰角" };
    if (issue.path === "advanced.height_layers_m") return { ...issue, message: "高度分层最多允许 20 个不同值" };
    if (issue.path === "coverage.max_range_m") return { ...issue, message: "最大探测距离必须大于 0 米" };
    if (issue.path === "route.waypoints") return { ...issue, message: "航线至少包含两个航点" };
    if (issue.path === "sensor.max_range_m") return { ...issue, message: "最小探测距离必须小于最大探测距离" };
    if (issue.path === "vehicles") return { ...issue, message: "至少启用一种车辆" };
    if (issue.path === "aircraft.max_agl_m") return { ...issue, message: "最低离地高度必须小于最高离地高度" };
    if (issue.path === "altitude_layers_m") return { ...issue, message: "高度层不能为空、不得重复且必须严格升序排列" };
    if (issue.path.endsWith(".max_range_m")) return { ...issue, message: "威胁最小射程必须小于最大射程" };
    if (issue.path.endsWith(".max_altitude_m")) return { ...issue, message: "威胁最低高度必须小于最高高度" };
    if (issue.path.endsWith(".kill_zone_radius_m")) return { ...issue, message: "杀伤半径不能大于预警半径" };
    return issue;
  });
}
</script>

<style scoped>
.model-parameter-panel { display: grid; grid-template-rows: minmax(0, 1fr) auto; height: 100%; min-height: 0; background: #fff; }.model-parameter-panel__body { min-height: 0; overflow-y: auto; }.model-parameter-panel__footer { position: sticky; bottom: 0; z-index: 2; display: grid; gap: 10px; padding: 12px 14px; background: #fff; border-top: 1px solid #dcdfe6; box-shadow: 0 -6px 18px rgba(48, 49, 51, .06); }.model-parameter-panel__footer > .el-button { width: 100%; margin: 0; }.validation-issues { display: grid; gap: 5px; padding: 8px 10px; color: #b42318; background: #fef3f2; border-left: 3px solid #d92d20; font-size: 12px; line-height: 1.45; }.validation-issues strong { font-size: 12px; }.validation-issues ul { display: grid; gap: 3px; margin: 0; padding-left: 18px; }
</style>
