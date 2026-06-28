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
  </section>
</template>

<script setup lang="ts">
import type { CoverageTaskStatus } from "../api/client";

defineProps<{
  task: CoverageTaskStatus | null;
}>();

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
