<template>
  <div class="metric-grid-view">
    <p v-if="!definitions.length || !metrics" class="metric-grid-view__empty">暂无指标</p>
    <dl v-else>
      <div v-for="definition in definitions" :key="definition.key">
        <dt>{{ definition.label }}</dt>
        <dd>{{ formatMetricValue(metrics[definition.key], definition.format) }}</dd>
      </div>
    </dl>
  </div>
</template>

<script setup lang="ts">
import type { MetricDefinition } from "../../models/shared";

defineProps<{
  definitions: MetricDefinition<Record<string, unknown>>[];
  metrics: Record<string, unknown> | null;
}>();

function formatMetricValue(value: unknown, format: MetricDefinition<Record<string, unknown>>["format"]) {
  if (value === null || value === undefined || value === "") return "--";
  if (format === "text") {
    if (typeof value === "boolean") return value ? "是" : "否";
    return String(value);
  }
  if (typeof value !== "number" || !Number.isFinite(value)) return String(value);

  if (format === "area") {
    return value > 1_000_000 ? `${formatDecimal(value / 1_000_000, 2, 2)} km²` : `${formatDecimal(value, 0, 2)} m²`;
  }
  if (format === "distance") {
    return value > 1_000 ? `${formatDecimal(value / 1_000, 2, 2)} km` : `${formatDecimal(value, 0, 2)} m`;
  }
  if (format === "duration") {
    const totalSeconds = Math.max(0, Math.round(value));
    const hours = Math.floor(totalSeconds / 3_600);
    const minutes = Math.floor((totalSeconds % 3_600) / 60);
    const seconds = totalSeconds % 60;
    return `${hours} h ${minutes} m ${seconds} s`;
  }
  if (format === "percent") return `${formatDecimal(value * 100, 0, 2)}%`;
  return formatDecimal(value, 0, 2);
}

function formatDecimal(value: number, minimumFractionDigits: number, maximumFractionDigits: number) {
  return value.toLocaleString("zh-CN", { minimumFractionDigits, maximumFractionDigits });
}
</script>

<style scoped>
.metric-grid-view__empty {
  margin: 0;
  color: #64748b;
  font-size: 12px;
}

.metric-grid-view dl {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin: 0;
}

.metric-grid-view dl div {
  min-width: 0;
}

.metric-grid-view dt {
  color: #64748b;
  font-size: 11px;
}

.metric-grid-view dd {
  margin: 3px 0 0;
  overflow-wrap: anywhere;
  color: #172033;
  font-size: 14px;
  font-weight: 700;
}
</style>
