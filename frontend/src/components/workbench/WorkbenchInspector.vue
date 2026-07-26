<template>
  <section class="workbench-inspector">
    <div v-if="mode === 'result' && context" class="result-detail" data-result-detail>
      <header><div><small>{{ definitionLabel }}</small><h1>任务结果</h1></div><button type="button" aria-label="Back to model parameters" @click="emit('show-parameters')"><ElIcon><ArrowLeft /></ElIcon></button></header>
      <div class="result-detail__body">
        <p class="result-status" :data-status="context.task.status">{{ statusLabel }}</p>
        <p v-if="context.task.message" class="result-message">{{ context.task.message }}</p>
        <details open><summary>核心指标</summary><dl><template v-for="metric in metrics" :key="metric.label"><dt>{{ metric.label }}</dt><dd>{{ metric.value }}</dd></template></dl></details>
        <details v-if="context.task.output_files?.length" open><summary>输出文件</summary><a v-for="file in context.task.output_files" :key="file.url" :href="file.download_url || file.url" target="_blank">{{ file.label || file.filename }}</a></details>
      </div>
    </div>
    <slot v-else name="parameters" />
  </section>
</template>

<script setup lang="ts">
import { ArrowLeft } from "@element-plus/icons-vue";
import { ElIcon } from "element-plus";
import { computed } from "vue";

import { getModelDefinition, type ModelId } from "../../models/registry";
import type { BaseModelRequest, TaskSummary } from "../../models/shared";

type Context = { modelId: ModelId; task: TaskSummary<BaseModelRequest, unknown, unknown, unknown> };
const props = defineProps<{ mode: "parameters" | "result"; context?: Context | null }>();
const emit = defineEmits<{ "show-parameters": [] }>();
const definitionLabel = computed(() => props.context ? getModelDefinition(props.context.modelId).label : "");
const statusLabel = computed(() => ({ pending: "等待执行", running: "正在运行", finished: "已完成", failed: "执行失败" }[props.context?.task.status ?? "pending"]));
const metrics = computed(() => Object.entries((props.context?.task.metrics ?? {}) as Record<string, unknown>).slice(0, 8).map(([key, value]) => ({ label: formatKey(key), value: typeof value === "number" ? formatNumber(value) : String(value) })));
function formatKey(key: string) { return key.replace(/_m2$/, " 面积").replace(/_/g, " "); }
function formatNumber(value: number) { return Math.abs(value) > 1000 ? value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : value.toFixed(2); }
</script>

<style scoped>
.workbench-inspector,.result-detail{height:100%;min-height:0}.result-detail{display:grid;grid-template-rows:auto minmax(0,1fr)}header{display:flex;align-items:flex-start;justify-content:space-between;padding:16px;border-bottom:1px solid var(--wb-border-soft)}small{color:var(--wb-muted);font-size:12px}h1{margin:2px 0 0;font-size:21px}header button{display:grid;width:32px;height:32px;place-items:center;border:0;border-radius:8px;background:transparent;color:var(--wb-fg-2);cursor:pointer}.result-detail__body{overflow:auto;padding:16px}.result-status{display:inline-block;margin:0 0 10px;padding:4px 9px;border-radius:980px;background:var(--wb-surface);color:var(--wb-fg-2);font-size:12px}.result-status[data-status="finished"]{background:#e8f8ee;color:#15803d}.result-status[data-status="failed"]{background:#fff0f0;color:#c33030}.result-message{margin:0 0 14px;color:var(--wb-muted);font-size:13px}.result-detail details{padding:10px 0;border-top:1px solid var(--wb-border-soft)}summary{color:var(--wb-fg);font-size:14px;font-weight:600;list-style:none}summary::before{content:">";display:inline-block;margin-right:6px;color:var(--wb-meta);transform:rotate(90deg)}dl{display:grid;grid-template-columns:1fr auto;gap:8px;margin:12px 0 0;font-size:13px}dt{color:var(--wb-muted)}dd{margin:0;color:var(--wb-fg);font-variant-numeric:tabular-nums}a{display:block;margin-top:10px;color:var(--wb-accent);font-size:13px;text-decoration:none}
</style>
