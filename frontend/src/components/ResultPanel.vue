<template>
  <section class="result-panel">
    <div>
      <strong>任务</strong>
      <span>{{ task?.task_id ?? "未开始" }}</span>
    </div>
    <div>
      <strong>状态</strong>
      <span>{{ task?.status ?? "-" }}</span>
    </div>
    <div>
      <strong>进度</strong>
      <span>{{ task?.progress ?? 0 }}%</span>
    </div>
    <div>
      <strong>理论面积</strong>
      <span>{{ formatArea(task?.metrics?.theoretical_area_m2) }}</span>
    </div>
    <div>
      <strong>可探测面积</strong>
      <span>{{ formatArea(task?.metrics?.visible_area_m2) }}</span>
    </div>
    <div>
      <strong>遮挡比例</strong>
      <span>{{ formatRatio(task?.metrics?.blocked_ratio) }}</span>
    </div>
    <div>
      <strong>模型 EPSG</strong>
      <span>{{ task?.model?.target_epsg ?? "-" }}</span>
    </div>
    <div>
      <strong>Warning</strong>
      <span>{{ task?.warnings?.length ? `${task.warnings.length} 条` : "无" }}</span>
    </div>
    <div>
      <strong>元数据</strong>
      <a v-if="metadataUrl" :href="metadataUrl" target="_blank" rel="noreferrer">model_metadata.json</a>
      <span v-else>-</span>
    </div>
    <p v-if="task?.warnings?.length" class="warnings">
      {{ task.warnings.join("；") }}
    </p>
  </section>
</template>

<script setup lang="ts">
import { computed } from "vue";

import { resolveAssetUrl, type CoverageTaskStatus } from "../api/client";

const props = defineProps<{
  task: CoverageTaskStatus | null;
}>();

const metadataUrl = computed(() => resolveAssetUrl(props.task?.outputs?.model_metadata_json));

function formatArea(value?: number | null) {
  if (value == null) {
    return "-";
  }
  if (value > 1_000_000) {
    return `${(value / 1_000_000).toFixed(2)} km²`;
  }
  return `${value.toFixed(0)} m²`;
}

function formatRatio(value?: number | null) {
  if (value == null) {
    return "-";
  }
  return `${(value * 100).toFixed(1)}%`;
}
</script>
