<template>
  <div class="task-layer-list">
    <p v-if="!rows.length" class="task-layer-list__empty">暂无可加载图层</p>
    <div v-for="row in rows" :key="row.definition.kind" class="task-layer-row">
      <span class="task-layer-row__swatch" :style="{ backgroundColor: row.definition.color }" aria-hidden="true" />
      <div class="task-layer-row__identity">
        <strong>{{ layerLabel(row.definition.kind, row.definition.label) }}</strong>
        <span :data-state="row.state.status">{{ stateLabel(row.state) }}</span>
      </div>
      <label class="task-layer-row__visibility">
        <span class="sr-only">显示{{ layerLabel(row.definition.kind, row.definition.label) }}</span>
        <input
          type="checkbox"
          :checked="row.state.visible"
          :disabled="row.state.status !== 'ready'"
          @change="emitVisibility(row.state.kind, $event)"
        >
      </label>
      <input
        class="task-layer-row__opacity"
        type="range"
        min="0"
        max="1"
        step="0.05"
        :aria-label="`${layerLabel(row.definition.kind, row.definition.label)}透明度`"
        :value="row.state.opacity"
        :disabled="row.state.status !== 'ready'"
        @input="emitOpacity(row.state.kind, $event)"
      >
      <ElTooltip content="定位图层" placement="top" :show-after="300">
        <button
          type="button"
          class="task-layer-row__focus"
          :aria-label="`定位${layerLabel(row.definition.kind, row.definition.label)}`"
          :disabled="row.state.status !== 'ready'"
          @click="emit('focus', row.state.kind)"
        >
          <ElIcon><Location /></ElIcon>
        </button>
      </ElTooltip>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Location } from "@element-plus/icons-vue";
import { ElIcon, ElTooltip } from "element-plus";
import { computed } from "vue";

import type { OutputLayerDefinition } from "../../models/shared";
import type { TaskOutputLayerState } from "../../composables/useMapWorkspace";

const props = defineProps<{
  definitions: readonly OutputLayerDefinition[];
  states: readonly TaskOutputLayerState[];
}>();

const emit = defineEmits<{
  visibility: [kind: string, visible: boolean];
  opacity: [kind: string, opacity: number];
  focus: [kind: string];
}>();

const CHINESE_LAYER_LABELS: Record<string, string> = {
  footprint_geojson: "传感器足迹",
  blocked_geojson: "地形遮挡区",
  visible_geojson: "可见区",
  range_geojson: "探测范围"
};

const rows = computed(() => props.definitions.map((definition) => ({
  definition,
  state: props.states.find(({ kind }) => kind === definition.kind) ?? {
    kind: definition.kind,
    status: "idle" as const,
    visible: Boolean(definition.primary),
    opacity: definition.defaultOpacity,
    data: null,
    error: null
  }
})));

function layerLabel(kind: string, fallback: string) {
  return CHINESE_LAYER_LABELS[kind] ?? fallback;
}

function stateLabel(state: TaskOutputLayerState) {
  if (state.status === "error") return state.error || "图层加载失败";
  if (state.status === "loading") return "正在加载";
  if (state.status === "ready") return "已加载";
  return "无输出";
}

function emitVisibility(kind: string, event: Event) {
  emit("visibility", kind, (event.target as HTMLInputElement).checked);
}

function emitOpacity(kind: string, event: Event) {
  emit("opacity", kind, Number((event.target as HTMLInputElement).value));
}
</script>

<style scoped>
.task-layer-list {
  display: grid;
}

.task-layer-list__empty {
  margin: 0;
  color: #64748b;
  font-size: 12px;
}

.task-layer-row {
  display: grid;
  grid-template-columns: 10px minmax(92px, 1fr) 30px minmax(72px, 110px) 30px;
  align-items: center;
  gap: 8px;
  min-height: 48px;
  border-bottom: 1px solid #e2e8f0;
}

.task-layer-row:last-child {
  border-bottom: 0;
}

.task-layer-row__swatch {
  width: 10px;
  height: 10px;
  border-radius: 2px;
}

.task-layer-row__identity {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.task-layer-row__identity strong,
.task-layer-row__identity span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-layer-row__identity strong {
  color: #27364a;
  font-size: 12px;
}

.task-layer-row__identity span {
  color: #64748b;
  font-size: 11px;
}

.task-layer-row__identity span[data-state="error"] {
  color: #dc2626;
}

.task-layer-row__visibility {
  display: grid;
  place-items: center;
}

.task-layer-row__visibility input {
  width: 15px;
  height: 15px;
  accent-color: #2563eb;
}

.task-layer-row__opacity {
  width: 100%;
  accent-color: #2563eb;
}

.task-layer-row__focus {
  display: grid;
  width: 28px;
  height: 28px;
  padding: 0;
  place-items: center;
  color: #475569;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 4px;
  cursor: pointer;
}

.task-layer-row__focus:hover:not(:disabled) {
  color: #1d4ed8;
  background: #eff6ff;
  border-color: #bfdbfe;
}

.task-layer-row__focus:disabled {
  cursor: default;
  opacity: 0.35;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  clip-path: inset(50%);
}
</style>
