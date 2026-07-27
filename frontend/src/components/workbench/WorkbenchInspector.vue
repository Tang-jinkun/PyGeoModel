<template>
  <section class="workbench-inspector">
    <div v-if="mode === 'result' && context" class="result-detail" data-result-detail>
      <header class="result-header">
        <div>
          <small>{{ resultLabel }}</small>
          <h1>任务结果</h1>
        </div>
        <button type="button" aria-label="Back to model parameters" title="返回模型配置" @click="emit('show-parameters')">
          <ElIcon><ArrowLeft /></ElIcon>
        </button>
      </header>

      <div class="result-detail__body">
        <section class="result-summary" aria-label="任务状态">
          <div class="result-status" :data-status="context.task.status">
            <i aria-hidden="true"></i>
            <span>{{ statusLabel }}</span>
          </div>
          <span class="result-progress">{{ context.task.progress }}%</span>
          <p v-if="context.task.message">{{ context.task.message }}</p>
        </section>

        <section v-if="context.task.result_state === 'unavailable'" class="result-unavailable" data-result-unavailable>
          <strong>结果不可用</strong>
          <span>{{ context.task.result_reason_code || "ARTIFACT_UNAVAILABLE" }}</span>
        </section>

        <section class="result-section" data-result-metrics>
          <h2>核心指标</h2>
          <MetricGrid :definitions="metricDefinitions" :metrics="effectiveMetrics" />
        </section>

        <section v-if="availableFiles.length" class="result-section" data-result-files>
          <h2>输出文件</h2>
          <a
            v-for="file in availableFiles"
            :key="file.kind"
            :href="resolveApiUrl(file.download_path!)"
            target="_blank"
            rel="noopener noreferrer"
          >
            <span>{{ file.label || file.filename }}</span>
            <small>{{ formatFileSize(file.size_bytes) }}</small>
            <ElIcon aria-hidden="true"><Download /></ElIcon>
          </a>
        </section>
      </div>
    </div>
    <slot v-else name="parameters" />
  </section>
</template>

<script setup lang="ts">
import { ArrowLeft, Download } from "@element-plus/icons-vue";
import { ElIcon } from "element-plus";
import { computed } from "vue";

import { resolveApiUrl } from "../../api/http";
import type { OutputFile } from "../../models/shared";
import { resultContextLabel, resultContextMetricDefinitions, resultContextMetrics, type WorkbenchResultContext } from "../../workbench/resultContext";
import MetricGrid from "../tasks/MetricGrid.vue";

const props = withDefaults(defineProps<{
  mode: "parameters" | "result";
  context?: WorkbenchResultContext | null;
  metrics?: Record<string, unknown> | null;
  outputFiles?: readonly OutputFile[];
}>(), {
  context: null,
  metrics: null,
  outputFiles: () => []
});

const emit = defineEmits<{ "show-parameters": [] }>();
const resultLabel = computed(() => props.context ? resultContextLabel(props.context) : "");
const statusLabel = computed(() => ({
  pending: "等待执行",
  running: "正在运行",
  finished: "已完成",
  partial: "部分完成",
  failed: "执行失败"
}[props.context?.task.status ?? "pending"]));
const effectiveMetrics = computed(() => props.metrics ?? (props.context ? resultContextMetrics(props.context) : null) ?? null);
const metricDefinitions = computed(() => props.context ? resultContextMetricDefinitions(props.context) : []);
const availableFiles = computed(() => props.outputFiles.filter((file) => file.exists && file.download_path));

function formatFileSize(size?: number | null) {
  if (!size || size < 1) return "";
  if (size >= 1_048_576) return `${(size / 1_048_576).toFixed(1)} MB`;
  if (size >= 1_024) return `${(size / 1_024).toFixed(1)} KB`;
  return `${size} B`;
}
</script>

<style scoped>
.workbench-inspector,
.result-detail {
  min-width: 0;
  min-height: 0;
  height: 100%;
}

.result-detail {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  color: var(--wb-fg);
  background: var(--wb-bg);
}

.result-header {
  display: flex;
  min-height: 64px;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--wb-border-soft);
}

.result-header small {
  color: var(--wb-muted);
  font-size: 11px;
}

.result-header h1 {
  margin: 2px 0 0;
  font-size: 16px;
  font-weight: 650;
  letter-spacing: 0;
}

.result-header button {
  display: grid;
  width: 32px;
  height: 32px;
  padding: 0;
  place-items: center;
  color: var(--wb-fg-2);
  background: transparent;
  border: 0;
  border-radius: 8px;
  cursor: pointer;
}

.result-header button:hover { background: var(--wb-surface); }

.result-detail__body {
  min-height: 0;
  overflow: auto;
  padding: 0 14px 16px;
}

.result-summary {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 4px 12px;
  padding: 14px 0;
}

.result-summary p {
  grid-column: 1 / -1;
  margin: 0;
  overflow-wrap: anywhere;
  color: var(--wb-muted);
  font-size: 12px;
}

.result-status {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--wb-accent);
  font-size: 12px;
  font-weight: 600;
}

.result-status i {
  width: 7px;
  height: 7px;
  flex: none;
  border-radius: 50%;
  background: currentColor;
}

.result-status[data-status="finished"] { color: #18a957; }
.result-status[data-status="failed"] { color: #e5484d; }
.result-progress { color: var(--wb-meta); font-size: 12px; font-variant-numeric: tabular-nums; }

.result-unavailable {
  display: grid;
  gap: 4px;
  margin-bottom: 14px;
  padding: 10px;
  color: #a1262f;
  background: #fff2f2;
  border: 1px solid #f2caca;
  border-radius: 8px;
  font-size: 12px;
}

.result-unavailable span { overflow-wrap: anywhere; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 11px; }

.result-section {
  padding: 14px 0;
  border-top: 1px solid var(--wb-border-soft);
}

.result-section h2 {
  margin: 0 0 12px;
  font-size: 13px;
  font-weight: 650;
  letter-spacing: 0;
}

.result-section a {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto 18px;
  align-items: center;
  gap: 8px;
  min-height: 36px;
  color: var(--wb-fg-2);
  border-bottom: 1px solid var(--wb-border-soft);
  font-size: 12px;
  text-decoration: none;
}

.result-section a span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.result-section a small { color: var(--wb-meta); font-size: 10px; }
.result-section a .el-icon { color: var(--wb-accent); }
.result-section a:hover span { color: var(--wb-accent); }
</style>
