<template>
  <section class="task-result-panel" :data-status="task.status">
    <div class="task-result-panel__tabs" role="tablist" aria-label="任务结果">
      <button
        v-for="tab in TABS"
        :key="tab.id"
        type="button"
        role="tab"
        :data-tab="tab.id"
        :aria-selected="activeTab === tab.id"
        :class="{ 'is-active': activeTab === tab.id }"
        @click="activeTab = tab.id"
      >
        {{ tab.label }}
      </button>
    </div>

    <div class="task-result-panel__content" role="tabpanel">
      <TaskStatusView v-if="activeTab === 'task'" :task="task" />
      <MetricGrid
        v-else-if="activeTab === 'metrics'"
        :definitions="metricDefinitions"
        :metrics="effectiveMetrics"
      />
      <div v-else-if="activeTab === 'layers'" class="task-result-panel__layers">
        <LayerList
          :definitions="definition.outputLayers"
          :states="layerStates"
          @visibility="(kind, visible) => emit('layer-visibility', kind, visible)"
          @opacity="(kind, opacity) => emit('layer-opacity', kind, opacity)"
          @focus="(kind) => emit('layer-focus', kind)"
        />
        <SceneGlbControl
          v-for="entry in sceneGlbEntries"
          :key="entry.kind"
          :file="entry.file"
          :state="entry.state"
          @visibility="emit('scene-glb-visibility', entry.kind, $event)"
          @focus="emit('scene-glb-focus', entry.kind)"
        />
      </div>
      <OutputFileList v-else :files="effectiveOutputFiles" />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";

import type {
  SceneGlbKind,
  SceneGlbOverlayState,
  TaskOutputLayerState
} from "../../composables/useMapWorkspace";
import { getModelDefinition } from "../../models/registry";
import type { BaseModelRequest, ModelId, OutputFile, TaskSummary } from "../../models/shared";
import LayerList from "./LayerList.vue";
import MetricGrid from "./MetricGrid.vue";
import OutputFileList from "./OutputFileList.vue";
import SceneGlbControl from "./SceneGlbControl.vue";
import TaskStatusView from "./TaskStatusView.vue";

type ResultTab = "task" | "metrics" | "layers" | "files";

const props = withDefaults(defineProps<{
  modelId: ModelId;
  task: TaskSummary<BaseModelRequest, unknown, unknown, unknown>;
  metrics?: Record<string, unknown> | null;
  outputFiles?: readonly OutputFile[];
  layerStates?: readonly TaskOutputLayerState[];
  sceneGlbState?: SceneGlbOverlayState | null;
  radarPlatformGlbState?: SceneGlbOverlayState | null;
}>(), {
  metrics: null,
  outputFiles: () => [],
  layerStates: () => [],
  sceneGlbState: null,
  radarPlatformGlbState: null
});

const emit = defineEmits<{
  "layer-visibility": [kind: string, visible: boolean];
  "layer-opacity": [kind: string, opacity: number];
  "layer-focus": [kind: string];
  "scene-glb-visibility": [kind: SceneGlbKind, visible: boolean];
  "scene-glb-focus": [kind: SceneGlbKind];
}>();

const TABS: Array<{ id: ResultTab; label: string }> = [
  { id: "task", label: "任务" },
  { id: "metrics", label: "指标" },
  { id: "layers", label: "图层" },
  { id: "files", label: "文件" }
];

const activeTab = ref<ResultTab>("task");
const definition = computed(() => getModelDefinition(props.modelId));
const metricDefinitions = computed(() => definition.value.metrics as never);
const effectiveMetrics = computed(() => props.metrics ?? props.task.metrics as Record<string, unknown> | null ?? null);
const effectiveOutputFiles = computed(() => props.outputFiles.length ? props.outputFiles : props.task.output_files);
const sceneGlbEntries = computed(() => {
  const states: Record<SceneGlbKind, SceneGlbOverlayState | null> = {
    scene_glb: props.sceneGlbState,
    radar_platform_glb: props.radarPlatformGlbState
  };
  return (["scene_glb", "radar_platform_glb"] as const).flatMap((kind) => {
    const file = effectiveOutputFiles.value.find(
      (candidate) => candidate.kind === kind && candidate.exists
    );
    const state = states[kind];
    return file && state ? [{ kind, file, state }] : [];
  });
});
</script>

<style scoped>
.task-result-panel {
  display: grid;
  grid-template-rows: 38px minmax(0, 1fr);
  min-width: 0;
  height: 100%;
  background: #ffffff;
}

.task-result-panel__tabs {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  border-bottom: 1px solid #dbe3ec;
}

.task-result-panel__tabs button {
  min-width: 0;
  padding: 0 6px;
  color: #64748b;
  background: transparent;
  border: 0;
  border-bottom: 2px solid transparent;
  font-size: 12px;
  font-weight: 650;
  cursor: pointer;
}

.task-result-panel__tabs button.is-active {
  color: #1d4ed8;
  border-bottom-color: #2563eb;
}

.task-result-panel__content {
  min-height: 0;
  overflow: auto;
  padding: 14px;
}

.task-result-panel__layers {
  min-width: 0;
}
</style>
