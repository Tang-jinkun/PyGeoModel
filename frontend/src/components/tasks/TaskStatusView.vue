<template>
  <section class="task-status-view" :data-status="task.status">
    <div class="task-status-view__heading">
      <div>
        <strong>{{ statusLabel }}</strong>
        <span>{{ task.message || "暂无任务消息" }}</span>
      </div>
      <span class="task-status-view__progress">{{ normalizedProgress }}%</span>
    </div>

    <div
      class="task-status-view__bar"
      role="progressbar"
      aria-label="任务进度"
      :aria-valuenow="normalizedProgress"
      aria-valuemin="0"
      aria-valuemax="100"
    >
      <span :style="{ width: `${normalizedProgress}%` }" />
    </div>

    <dl class="task-status-view__details">
      <div>
        <dt>任务编号</dt>
        <dd>{{ task.task_id }}</dd>
      </div>
      <div>
        <dt>更新时间</dt>
        <dd>{{ formattedTime }}</dd>
      </div>
    </dl>

    <div v-if="task.warnings.length" class="task-status-view__warnings">
      <strong>注意事项</strong>
      <ul>
        <li v-for="warning in task.warnings" :key="warning">{{ warning }}</li>
      </ul>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from "vue";

import type { BaseModelRequest, TaskSummary } from "../../models/shared";

const props = defineProps<{
  task: TaskSummary<BaseModelRequest, unknown, unknown, unknown>;
}>();

const STATUS_LABELS = {
  pending: "任务等待中",
  running: "任务运行中",
  finished: "任务已完成",
  failed: "任务失败"
} as const;

const statusLabel = computed(() => STATUS_LABELS[props.task.status]);
const normalizedProgress = computed(() => Math.min(100, Math.max(0, Math.round(props.task.progress))));
const formattedTime = computed(() => {
  const value = props.task.updated_at ?? props.task.created_at;
  if (!value) return "--";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
});
</script>

<style scoped>
.task-status-view {
  display: grid;
  gap: 12px;
}

.task-status-view__heading,
.task-status-view__heading > div {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.task-status-view__heading {
  justify-content: space-between;
}

.task-status-view__heading > div {
  align-items: flex-start;
  flex-direction: column;
  gap: 3px;
}

.task-status-view__heading strong {
  color: #172033;
  font-size: 14px;
}

.task-status-view__heading span,
.task-status-view__details dt {
  color: #64748b;
  font-size: 12px;
}

.task-status-view__progress {
  flex: 0 0 auto;
  font-weight: 700;
}

.task-status-view__bar {
  height: 6px;
  overflow: hidden;
  background: #e2e8f0;
  border-radius: 3px;
}

.task-status-view__bar span {
  display: block;
  height: 100%;
  background: #2563eb;
}

.task-status-view[data-status="finished"] .task-status-view__bar span {
  background: #15803d;
}

.task-status-view[data-status="failed"] .task-status-view__bar span {
  background: #dc2626;
}

.task-status-view__details {
  display: grid;
  gap: 8px;
  margin: 0;
}

.task-status-view__details div {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr);
  gap: 8px;
}

.task-status-view__details dd {
  min-width: 0;
  margin: 0;
  overflow-wrap: anywhere;
  color: #334155;
  font-size: 12px;
}

.task-status-view__warnings {
  padding: 9px;
  color: #9a3412;
  background: #fff7ed;
  border: 1px solid #fed7aa;
  border-radius: 6px;
  font-size: 12px;
}

.task-status-view__warnings ul {
  margin: 6px 0 0;
  padding-left: 18px;
}
</style>
