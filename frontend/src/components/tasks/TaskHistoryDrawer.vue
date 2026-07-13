<template>
  <aside v-if="open" class="task-history-drawer" aria-label="任务历史">
    <header class="task-history-drawer__header">
      <div>
        <strong>任务历史</strong>
        <span>{{ rows.length }} 条记录</span>
      </div>
      <ElTooltip content="关闭" placement="left" :show-after="300">
        <button type="button" aria-label="关闭任务历史" @click="emit('close')">
          <ElIcon><Close /></ElIcon>
        </button>
      </ElTooltip>
    </header>

    <p v-if="!rows.length" class="task-history-drawer__empty">暂无历史任务</p>
    <div v-else class="task-history-drawer__list">
      <article v-for="row in rows" :key="`${row.modelId}:${row.task.task_id}`" class="task-history-row">
        <div class="task-history-row__main">
          <div class="task-history-row__title">
            <strong>{{ modelLabel(row.modelId) }}</strong>
            <span :data-status="row.task.status">{{ statusLabel(row.task.status) }}</span>
          </div>
          <span class="task-history-row__time">{{ taskTime(row.task) }}</span>
          <div class="task-history-row__progress">
            <span :style="{ width: `${normalizedProgress(row.task.progress)}%` }" />
          </div>
        </div>

        <div class="task-history-row__actions">
          <ElTooltip content="恢复参数" placement="top" :show-after="300">
            <button
              type="button"
              data-action="restore"
              aria-label="恢复任务参数"
              :disabled="isBusy(row)"
              @click="restore(row)"
            >
              <ElIcon><RefreshLeft /></ElIcon>
            </button>
          </ElTooltip>
          <ElTooltip content="定位结果" placement="top" :show-after="300">
            <button type="button" data-action="focus" aria-label="定位任务结果" @click="emit('focus', row.modelId, row.task)">
              <ElIcon><Location /></ElIcon>
            </button>
          </ElTooltip>
          <ElTooltip content="删除任务" placement="top" :show-after="300">
            <button
              type="button"
              data-action="delete"
              aria-label="删除任务"
              :disabled="isBusy(row)"
              @click="remove(row)"
            >
              <ElIcon><Delete /></ElIcon>
            </button>
          </ElTooltip>
        </div>
      </article>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { Close, Delete, Location, RefreshLeft } from "@element-plus/icons-vue";
import { ElIcon, ElTooltip } from "element-plus";
import { computed, ref } from "vue";

import { MODEL_IDS, MODEL_REGISTRY } from "../../models/registry";
import type { BaseModelRequest, ModelId, TaskStatus, TaskSummary } from "../../models/shared";

type HistoryTask = TaskSummary<BaseModelRequest, unknown, unknown, unknown>;
interface HistoryRow { modelId: ModelId; task: HistoryTask }
interface TaskHistoryManager {
  restoreRequest(modelId: ModelId, taskId: string): Promise<BaseModelRequest | null>;
  remove(modelId: ModelId, taskId: string): Promise<unknown>;
}

const props = defineProps<{
  open: boolean;
  tasksByModel: Partial<Record<ModelId, readonly HistoryTask[]>>;
  taskManager: TaskHistoryManager;
  confirmDelete?: (message: string) => boolean | Promise<boolean>;
}>();

const emit = defineEmits<{
  close: [];
  restore: [modelId: ModelId, request: BaseModelRequest];
  focus: [modelId: ModelId, task: HistoryTask];
  deleted: [modelId: ModelId, taskId: string];
  error: [error: unknown];
}>();

const busyKeys = ref(new Set<string>());
const rows = computed<HistoryRow[]>(() => MODEL_IDS.flatMap((modelId) => (
  props.tasksByModel[modelId] ?? []
).map((task) => ({ modelId, task }))).sort((left, right) => taskTimestamp(right.task) - taskTimestamp(left.task)));

const STATUS_LABELS: Record<TaskStatus, string> = {
  pending: "等待中",
  running: "运行中",
  finished: "已完成",
  failed: "失败"
};

const MODEL_LABELS: Record<ModelId, string> = {
  radar: "雷达覆盖",
  uav: "无人机侦察",
  watchpost: "观察哨",
  artillery: "火炮阵地",
  reconVehicle: "侦察车",
  mobility: "机动性对比",
  airCorridor: "空中走廊"
};

function modelLabel(modelId: ModelId) {
  return MODEL_LABELS[modelId] ?? MODEL_REGISTRY[modelId].label;
}

function statusLabel(status: TaskStatus) {
  return STATUS_LABELS[status];
}

function normalizedProgress(progress: number) {
  return Math.min(100, Math.max(0, progress));
}

function taskTimestamp(task: HistoryTask) {
  const value = task.updated_at ?? task.created_at;
  if (!value) return 0;
  const timestamp = new Date(value).getTime();
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

function taskTime(task: HistoryTask) {
  const timestamp = taskTimestamp(task);
  return timestamp ? new Date(timestamp).toLocaleString("zh-CN", { hour12: false }) : "时间未知";
}

function rowKey(row: HistoryRow) {
  return `${row.modelId}:${row.task.task_id}`;
}

function isBusy(row: HistoryRow) {
  return busyKeys.value.has(rowKey(row));
}

function setBusy(row: HistoryRow, busy: boolean) {
  const next = new Set(busyKeys.value);
  if (busy) next.add(rowKey(row));
  else next.delete(rowKey(row));
  busyKeys.value = next;
}

async function restore(row: HistoryRow) {
  setBusy(row, true);
  try {
    const request = await props.taskManager.restoreRequest(row.modelId, row.task.task_id);
    if (request) emit("restore", row.modelId, request);
  } catch (error) {
    emit("error", error);
  } finally {
    setBusy(row, false);
  }
}

async function remove(row: HistoryRow) {
  const message = "删除后，后端任务记录和输出文件将被移除，且无法恢复。确定删除吗？";
  const confirmed = await (props.confirmDelete ? props.confirmDelete(message) : window.confirm(message));
  if (!confirmed) return;

  setBusy(row, true);
  try {
    await props.taskManager.remove(row.modelId, row.task.task_id);
    emit("deleted", row.modelId, row.task.task_id);
  } catch (error) {
    emit("error", error);
  } finally {
    setBusy(row, false);
  }
}
</script>

<style scoped>
.task-history-drawer {
  position: fixed;
  top: 0;
  right: 0;
  z-index: 30;
  display: grid;
  grid-template-rows: 54px minmax(0, 1fr);
  width: min(420px, 100vw);
  height: 100vh;
  color: #27364a;
  background: #ffffff;
  border-left: 1px solid #dbe3ec;
  box-shadow: -12px 0 28px rgb(15 23 42 / 12%);
}

.task-history-drawer__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 14px;
  border-bottom: 1px solid #dbe3ec;
}

.task-history-drawer__header > div {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.task-history-drawer__header strong {
  font-size: 14px;
}

.task-history-drawer__header span,
.task-history-drawer__empty,
.task-history-row__time {
  color: #64748b;
  font-size: 11px;
}

.task-history-drawer__header button,
.task-history-row__actions button {
  display: grid;
  width: 30px;
  height: 30px;
  padding: 0;
  place-items: center;
  color: #475569;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 4px;
  cursor: pointer;
}

.task-history-drawer__header button:hover,
.task-history-row__actions button:hover:not(:disabled) {
  color: #1d4ed8;
  background: #eff6ff;
  border-color: #bfdbfe;
}

.task-history-drawer__empty {
  margin: 18px 14px;
}

.task-history-drawer__list {
  overflow: auto;
}

.task-history-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  padding: 12px 14px;
  border-bottom: 1px solid #e2e8f0;
}

.task-history-row__main {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.task-history-row__title {
  display: flex;
  align-items: center;
  gap: 7px;
}

.task-history-row__title strong {
  overflow: hidden;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-history-row__title span {
  padding: 2px 5px;
  color: #475569;
  background: #f1f5f9;
  border-radius: 3px;
  font-size: 10px;
}

.task-history-row__title span[data-status="finished"] {
  color: #166534;
  background: #dcfce7;
}

.task-history-row__title span[data-status="failed"] {
  color: #991b1b;
  background: #fee2e2;
}

.task-history-row__progress {
  height: 4px;
  overflow: hidden;
  background: #e2e8f0;
  border-radius: 2px;
}

.task-history-row__progress span {
  display: block;
  height: 100%;
  background: #2563eb;
}

.task-history-row__actions {
  display: flex;
  align-items: center;
}

.task-history-row__actions button:disabled {
  cursor: default;
  opacity: 0.35;
}
</style>
