<template>
  <section v-if="finishedTasks.length >= 2" class="fusion-panel">
    <header class="fusion-header">
      <div>
        <strong>融合分析</strong>
        <span>并集、重叠覆盖与盲区</span>
      </div>
      <button v-if="result" class="link-button" type="button" @click="$emit('clear')">清除</button>
    </header>

    <div class="fusion-task-list">
      <label v-for="item in finishedTasks" :key="item.task_id" class="fusion-task">
        <input v-model="selectedTaskIds" type="checkbox" :value="item.task_id" />
        <span>{{ shortTaskId(item.task_id) }}</span>
        <small>{{ formatArea(item.metrics?.visible_area_m2) }}</small>
      </label>
    </div>

    <el-button
      type="primary"
      size="small"
      :loading="loading"
      :disabled="selectedTaskIds.length < 2"
      @click="$emit('run', selectedTaskIds)"
    >
      运行融合
    </el-button>

    <div v-if="result" class="fusion-metrics">
      <div>
        <strong>总可探测</strong>
        <span>{{ formatArea(result.metrics.union_visible_area_m2) }}</span>
      </div>
      <div>
        <strong>重叠覆盖</strong>
        <span>{{ formatArea(result.metrics.overlap_visible_area_m2) }}</span>
      </div>
      <div>
        <strong>理论盲区</strong>
        <span>{{ formatArea(result.metrics.blind_area_m2) }}</span>
      </div>
      <div>
        <strong>盲区比例</strong>
        <span>{{ formatRatio(result.metrics.blind_ratio) }}</span>
      </div>
    </div>

    <div v-if="result?.warnings.length" class="fusion-warnings">
      <span v-for="warning in result.warnings" :key="warning">{{ warning }}</span>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";

import type { CoverageTaskSummary, FusionResult } from "../api/client";

const props = defineProps<{
  tasks: CoverageTaskSummary[];
  result: FusionResult | null;
  loading: boolean;
}>();

defineEmits<{
  run: [taskIds: string[]];
  clear: [];
}>();

const selectedTaskIds = ref<string[]>([]);

const finishedTasks = computed(() => props.tasks.filter((task) => task.status === "finished"));

watch(
  finishedTasks,
  (tasks) => {
    const validIds = new Set(tasks.map((task) => task.task_id));
    const retained = selectedTaskIds.value.filter((taskId) => validIds.has(taskId));
    selectedTaskIds.value = retained.length ? retained : tasks.slice(0, 2).map((task) => task.task_id);
  },
  { immediate: true }
);

function shortTaskId(taskId: string) {
  return taskId.replace(/^task_/, "").slice(-8);
}

function formatArea(value?: number | null) {
  if (value == null) {
    return "-";
  }
  if (value >= 1_000_000) {
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
