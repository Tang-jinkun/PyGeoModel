<template>
  <section class="workbench-task-center" aria-label="任务中心">
    <header class="tasks-head">
      <span class="title">任务中心</span>
      <button v-for="tab in tabs" :key="tab.id" type="button" class="task-tab" role="tab" :aria-selected="activeTab === tab.id" @click="emit('update:activeTab', tab.id)">
        {{ tab.label }}<span v-if="tab.id === 'running' && runningTaskCount" class="badge">{{ runningTaskCount }}</span>
      </button>
      <span class="spacer"></span>
    </header>
    <div class="tasks-body">
      <div v-if="activeTab === 'logs'" class="task-pane active log-pane">
        <p v-for="task in multiRadarTasks" :key="task.task_id" class="log-line"><time>{{ multiRadarTaskTime(task) }}</time><span>[{{ shortId(task.task_id) }}] {{ task.message || multiRadarStatusLabel(task) }}</span></p>
        <p v-for="row in rows" :key="row.key" class="log-line"><time>{{ taskTime(row) }}</time><span>[{{ shortId(row.task.task_id) }}] {{ row.task.message || row.statusLabel }}</span></p>
        <p v-if="!rows.length && !multiRadarTasks.length" class="empty-state">暂无日志</p>
      </div>
      <div v-else class="task-pane active">
        <div v-for="task in visibleMultiRadarTasks" :key="task.task_id" class="task-row" data-multi-radar-task role="button" tabindex="0" @click="emit('select-multi-radar-task', task.task_id)" @keydown.enter="emit('select-multi-radar-task', task.task_id)">
          <span class="tid">{{ shortId(task.task_id) }}</span><span class="tmodel">多雷达协同</span>
          <span class="tinfo">{{ [task.dem_id, task.message || multiRadarStatusLabel(task)].filter(Boolean).join(" · ") }}</span>
          <span v-if="isMultiRadarRunning(task)" class="progress"><span class="bar"><i :style="{ width: `${task.progress}%` }"></i></span><span class="pv">{{ task.progress }}%</span></span><span v-else></span>
          <span class="status-chip" :class="multiRadarStatusClass(task)">{{ multiRadarStatusLabel(task) }}</span>
          <span class="task-act"></span>
        </div>
        <div v-for="row in visibleRows" :key="row.key" class="task-row" :data-task-key="row.key" role="button" tabindex="0" @click="select(row)" @keydown.enter="select(row)">
          <span class="tid">{{ shortId(row.task.task_id) }}</span><span class="tmodel">{{ row.label }}</span>
          <span class="tinfo">{{ taskInfo(row) }}</span>
          <span v-if="isRunning(row)" class="progress"><span class="bar"><i :style="{ width: `${row.task.progress}%` }"></i></span><span class="pv">{{ row.task.progress }}%</span></span><span v-else></span>
          <span class="status-chip" :class="statusClass(row)">{{ row.statusLabel }}</span>
          <span class="task-act"><button type="button" @click.stop="select(row)">{{ row.task.status === 'failed' ? '查看日志' : '查看图层' }}</button><a v-if="row.task.status === 'finished' && firstDownload(row)" :href="firstDownload(row)" target="_blank" @click.stop>下载</a></span>
        </div>
        <p v-if="!visibleRows.length && !visibleMultiRadarTasks.length" class="empty-state">暂无任务</p>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from "vue";

import type { MultiRadarTask } from "../../models/multiRadar/types";
import type { WorkbenchTaskRow } from "../../workbench/taskPresentation";
import type { TaskCenterTab } from "../../workbench/useWorkbenchPresentation";

const props = withDefaults(defineProps<{ rows: readonly WorkbenchTaskRow[]; activeTab?: TaskCenterTab; multiRadarTasks?: readonly MultiRadarTask[] }>(), { activeTab: "running", multiRadarTasks: () => [] });
const emit = defineEmits<{ "update:activeTab": [tab: TaskCenterTab]; "select-task": [modelId: WorkbenchTaskRow["modelId"], taskId: string]; "select-multi-radar-task": [taskId: string] }>();
const tabs: Array<{ id: TaskCenterTab; label: string }> = [{ id: "running", label: "运行中" }, { id: "history", label: "历史记录" }, { id: "logs", label: "日志" }];
const runningRows = computed(() => props.rows.filter(isRunning));
const visibleRows = computed(() => props.activeTab === "running" ? runningRows.value : props.rows.filter(({ task }) => task.status === "finished" || task.status === "failed"));
const runningMultiRadarTasks = computed(() => props.multiRadarTasks.filter(isMultiRadarRunning));
const runningTaskCount = computed(() => runningRows.value.length + runningMultiRadarTasks.value.length);
const visibleMultiRadarTasks = computed(() => props.activeTab === "running"
  ? runningMultiRadarTasks.value
  : props.activeTab === "history"
    ? props.multiRadarTasks.filter((task) => !isMultiRadarRunning(task))
    : []);
function isMultiRadarRunning(task: MultiRadarTask) { return task.status === "pending" || task.status === "running"; }
function multiRadarStatusLabel(task: MultiRadarTask) { return { pending: "等待中", running: "运行中", finished: "已完成", partial: "部分完成", failed: "失败" }[task.status]; }
function multiRadarStatusClass(task: MultiRadarTask) {
  const status = task.status;
  return status === "finished" ? "ok" : status === "failed" ? "fail" : status === "partial" ? "partial" : "run";
}
function isRunning(row: WorkbenchTaskRow) { return row.task.status === "pending" || row.task.status === "running"; }
function statusClass(row: WorkbenchTaskRow) { return row.task.status === "finished" ? "ok" : row.task.status === "failed" ? "fail" : "run"; }
function select(row: WorkbenchTaskRow) { emit("select-task", row.modelId, row.task.task_id); }
function taskInfo(row: WorkbenchTaskRow) {
  const summary = row.task.status === "finished" ? row.primaryMetric || row.task.message : row.task.message || row.primaryMetric;
  return [row.task.dem_id, summary].filter(Boolean).join(" · ") || "--";
}
function firstDownload(row: WorkbenchTaskRow) { const file = row.task.output_files.find(({ exists }) => exists); return file?.download_url || file?.url || ""; }
function shortId(id: string) { return id.length > 10 ? `T-${id.slice(0, 8)}` : id; }
function taskTime(row: WorkbenchTaskRow) { const value = row.task.updated_at || row.task.created_at; return value ? new Date(value).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "--:--:--"; }
function multiRadarTaskTime(task: MultiRadarTask) { const value = task.updated_at || task.created_at; return value ? new Date(value).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "--:--:--"; }
</script>

<style scoped>
.workbench-task-center{display:flex;height:100%;min-height:0;flex-direction:column}.tasks-head{display:flex;height:38px;flex:none;align-items:center;gap:4px;padding:0 8px}.title{padding:0 8px;color:var(--wb-fg);font-size:14px;font-weight:600}.task-tab{padding:6px 12px;border:0;border-radius:980px;background:transparent;color:var(--wb-muted);font-size:12px;cursor:pointer}.task-tab[aria-selected="true"]{background:var(--wb-surface);color:var(--wb-fg);font-weight:600}.badge{display:inline-block;min-width:16px;margin-left:4px;padding:0 4px;border-radius:980px;background:var(--wb-accent);color:#fff;font-size:10px;line-height:16px;text-align:center}.spacer{flex:1}.tasks-body{height:176px;overflow-y:auto;border-top:1px solid var(--wb-border-soft)}.task-pane{display:block}.task-row{display:grid;grid-template-columns:92px 170px minmax(0,1fr) 200px 140px auto;align-items:center;gap:16px;padding:8px 16px;border-bottom:1px solid var(--wb-border-soft);color:var(--wb-fg);font-size:14px;cursor:pointer}.task-row:hover{background:var(--wb-surface-warm)}.tid,.tinfo{overflow:hidden;color:var(--wb-muted);font-size:12px;text-overflow:ellipsis;white-space:nowrap}.tid,.pv{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}.tmodel{overflow:hidden;font-weight:600;text-overflow:ellipsis;white-space:nowrap}.progress{display:flex;align-items:center;gap:8px}.bar{height:5px;flex:1;overflow:hidden;border-radius:980px;background:var(--wb-surface)}.bar i{display:block;height:100%;border-radius:980px;background:var(--wb-accent);transition:width 400ms ease}.pv{width:36px;color:var(--wb-fg-2);font-size:12px;text-align:right}.status-chip{display:inline-flex;align-items:center;gap:6px;color:var(--wb-accent);font-size:12px;font-weight:600;white-space:nowrap}.status-chip::before{width:7px;height:7px;flex:none;border-radius:50%;background:currentColor;content:""}.status-chip.ok{color:#18a957}.status-chip.partial{color:#c78100}.status-chip.fail{color:#e5484d}.task-act{display:flex;justify-content:flex-end;gap:4px}.task-act button,.task-act a{padding:4px 10px;border:0;border-radius:980px;background:transparent;color:var(--wb-accent);font-size:12px;text-decoration:none;white-space:nowrap;cursor:pointer}.task-act button:hover,.task-act a:hover{background:rgb(0 113 227 / 9%)}.empty-state{padding:24px;margin:0;color:var(--wb-meta);font-size:12px;text-align:center}.log-line{display:flex;gap:12px;margin:0;padding:8px 16px;border-bottom:1px solid var(--wb-border-soft);font-size:12px}.log-line time{flex:none;color:var(--wb-meta)}.log-line span{overflow:hidden;color:var(--wb-fg-2);text-overflow:ellipsis;white-space:nowrap}@media(max-width:900px){.task-row{grid-template-columns:92px 1fr 120px auto}.task-row .tinfo,.task-row .progress{display:none}}
</style>
