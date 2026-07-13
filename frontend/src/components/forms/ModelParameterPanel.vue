<template>
  <section class="model-parameter-panel" :data-model-id="modelId">
    <div class="model-parameter-panel__body">
      <component
        :is="activeForm"
        :model-value="modelValue"
        @update:model-value="updateModelValue"
        @activate-map-tool="emit('activate-map-tool')"
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
import { computed, ref, type Component } from "vue";
import { artilleryDefinition } from "../../models/artillery/definition";
import type { ArtilleryRequest } from "../../models/artillery/types";
import { radarDefinition } from "../../models/radar/definition";
import type { RadarRequest } from "../../models/radar/types";
import type { ValidationIssue } from "../../models/shared";
import { watchpostDefinition } from "../../models/watchpost/definition";
import type { WatchpostRequest } from "../../models/watchpost/types";
import ArtilleryForm from "./ArtilleryForm.vue";
import RadarForm from "./RadarForm.vue";
import WatchpostForm from "./WatchpostForm.vue";

type PointModelId = "radar" | "watchpost" | "artillery";
type PointModelRequest = RadarRequest | WatchpostRequest | ArtilleryRequest;

const props = withDefaults(defineProps<{ modelId: PointModelId; modelValue: PointModelRequest; submitting?: boolean }>(), { submitting: false });
const emit = defineEmits<{ "update:modelValue": [request: PointModelRequest]; submit: [request: PointModelRequest]; "activate-map-tool": [] }>();
const issues = ref<ValidationIssue[]>([]);
const forms: Record<PointModelId, Component> = { radar: RadarForm, watchpost: WatchpostForm, artillery: ArtilleryForm };
const activeForm = computed(() => forms[props.modelId]);

function updateModelValue(request: PointModelRequest) {
  issues.value = [];
  emit("update:modelValue", request);
}

function submit() {
  issues.value = validateActiveRequest();
  if (issues.value.length === 0) emit("submit", props.modelValue);
}

function validateActiveRequest(): ValidationIssue[] {
  if (props.modelId === "radar") return localizeIssues(radarDefinition.validate(props.modelValue as RadarRequest));
  if (props.modelId === "artillery") return localizeIssues(artilleryDefinition.validate(props.modelValue as ArtilleryRequest));

  const request = props.modelValue as WatchpostRequest;
  const definitionIssues = watchpostDefinition.validate(request);
  const rangeIssues = request.coverage.max_range_m <= 0
    ? [{ path: "coverage.max_range_m", message: "最大探测距离必须大于 0 米" }]
    : [];
  return [...localizeIssues(definitionIssues), ...rangeIssues];
}

function localizeIssues(source: ValidationIssue[]): ValidationIssue[] {
  return source.map((issue) => {
    if (issue.path === "weapon.max_range_m") return { ...issue, message: "最小射程必须小于最大射程" };
    if (issue.path === "advanced.max_elevation_deg") return { ...issue, message: "最大仰角必须大于或等于最小仰角" };
    if (issue.path === "advanced.height_layers_m") return { ...issue, message: "高度分层最多允许 20 个不同值" };
    return issue;
  });
}
</script>

<style scoped>
.model-parameter-panel { display: grid; grid-template-rows: minmax(0, 1fr) auto; height: 100%; min-height: 0; background: #fff; }.model-parameter-panel__body { min-height: 0; overflow-y: auto; }.model-parameter-panel__footer { position: sticky; bottom: 0; z-index: 2; display: grid; gap: 10px; padding: 12px 14px; background: #fff; border-top: 1px solid #dcdfe6; box-shadow: 0 -6px 18px rgba(48, 49, 51, .06); }.model-parameter-panel__footer > .el-button { width: 100%; margin: 0; }.validation-issues { display: grid; gap: 5px; padding: 8px 10px; color: #b42318; background: #fef3f2; border-left: 3px solid #d92d20; font-size: 12px; line-height: 1.45; }.validation-issues strong { font-size: 12px; }.validation-issues ul { display: grid; gap: 3px; margin: 0; padding-left: 18px; }
</style>
