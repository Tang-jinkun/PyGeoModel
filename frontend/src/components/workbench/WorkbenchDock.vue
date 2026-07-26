<template>
  <section class="workbench-dock" aria-label="工作区面板">
    <div class="workbench-dock__tabs" role="tablist">
      <button v-for="tab in tabs" :key="tab.id" type="button" :data-dock-tab="tab.id" :aria-selected="activeTab === tab.id" @click="selectTab(tab.id)">
        {{ tab.label }}
      </button>
    </div>

    <div v-show="activeTab === 'catalog'" class="workbench-dock__body">
      <div class="workbench-dock__search"><input :value="search" type="search" placeholder="搜索分析模型" aria-label="Search analysis models" @input="updateSearch"></div>
      <details v-for="group in modelGroups" :key="group.label" open class="workbench-dock__group">
        <summary>{{ group.label }}<span>{{ group.models.length }}</span></summary>
        <button v-for="modelId in group.models" :key="modelId" type="button" class="workbench-dock__model" :class="{ 'is-selected': modelId === modelValue }" :data-model-id="modelId" @click="emit('select-model', modelId)">
          <ElIcon><component :is="modelIcons[modelId]" /></ElIcon>{{ MODEL_REGISTRY[modelId].label }}
        </button>
      </details>
      <p v-if="!modelGroups.length" class="workbench-dock__empty">没有匹配的分析模型</p>
    </div>

    <div v-show="activeTab === 'layers'" class="workbench-dock__body">
      <details open class="workbench-dock__group">
        <summary>任务结果图层<span>{{ layerDefinitions.length + sceneEntries.length }}</span></summary>
        <LayerList
          v-if="layerDefinitions.length"
          :definitions="layerDefinitions"
          :states="layerStates"
          @visibility="(kind, visible) => emit('update-layer-visibility', kind, visible)"
          @opacity="(kind, opacity) => emit('update-layer-opacity', kind, opacity)"
          @focus="(kind) => emit('focus-layer', kind)"
        />
        <div v-for="entry in sceneEntries" :key="entry.kind" :data-layer-kind="entry.kind">
          <SceneGlbControl :file="entry.file" :state="entry.state" @visibility="emit('update-scene-glb', entry.kind, $event)" @focus="emit('focus-scene-glb', entry.kind)" />
        </div>
      </details>
      <details v-if="radarLayers.length" open class="workbench-dock__group">
        <summary>雷达场景</summary>
        <RadarLayerControls :layers="radarLayers" :height-options="heightOptions" :selected-height-m="selectedHeightM" @update-layer="(kind, patch) => emit('update-radar-layer', kind, patch)" @select-height="emit('select-radar-height', $event)" />
      </details>
      <details v-if="multiRadarStations.length" open class="workbench-dock__group">
        <summary>协同雷达站<span>{{ multiRadarStations.length }}</span></summary>
        <MultiRadarStationList :stations="multiRadarStations" :detailed-station-ids="detailedStationIds" @focus="emit('focus-station', $event)" @show-detail="emit('show-station-detail', $event)" @hide-detail="emit('hide-station-detail', $event)" />
      </details>
      <slot name="base-layers" />
      <p v-if="!layerDefinitions.length && !sceneEntries.length && !radarLayers.length && !multiRadarStations.length" class="workbench-dock__empty">尚未加载任务图层</p>
    </div>

    <div v-show="activeTab === 'data'" class="workbench-dock__body">
      <slot name="data"><p class="workbench-dock__empty">暂无 DEM 或任务输出文件</p></slot>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Aim, Compass, Guide, Location, Position, Van, View } from "@element-plus/icons-vue";
import { ElIcon } from "element-plus";
import { computed, ref, watch, type Component } from "vue";

import type { SceneGlbKind, SceneGlbOverlayState, TaskOutputLayerState } from "../../composables/useMapWorkspace";
import { MODEL_REGISTRY, type ModelId } from "../../models/registry";
import type { OutputFile, OutputLayerDefinition } from "../../models/shared";
import type { MultiRadarStationSummary } from "../../models/multiRadar/types";
import LayerList from "../tasks/LayerList.vue";
import MultiRadarStationList from "../tasks/MultiRadarStationList.vue";
import RadarLayerControls, { type RadarControlKind, type RadarControlLayer, type RadarHeightOption } from "../tasks/RadarLayerControls.vue";
import SceneGlbControl from "../tasks/SceneGlbControl.vue";

type DockTab = "catalog" | "layers" | "data";
export interface WorkbenchSceneEntry { kind: SceneGlbKind; file: OutputFile; state: SceneGlbOverlayState }

const props = withDefaults(defineProps<{
  modelValue: ModelId;
  activeTab?: DockTab;
  modelSearch?: string;
  layerDefinitions?: readonly OutputLayerDefinition[];
  layerStates?: readonly TaskOutputLayerState[];
  sceneEntries?: readonly WorkbenchSceneEntry[];
  radarLayers?: RadarControlLayer[];
  heightOptions?: RadarHeightOption[];
  selectedHeightM?: number | null;
  multiRadarStations?: MultiRadarStationSummary[];
  detailedStationIds?: string[];
}>(), {
  activeTab: "catalog",
  modelSearch: "",
  layerDefinitions: () => [],
  layerStates: () => [],
  sceneEntries: () => [],
  radarLayers: () => [],
  heightOptions: () => [],
  selectedHeightM: null,
  multiRadarStations: () => [],
  detailedStationIds: () => []
});

const emit = defineEmits<{
  "select-model": [modelId: ModelId];
  "update:activeTab": [tab: DockTab];
  "update:modelSearch": [query: string];
  "update-layer-visibility": [kind: string, visible: boolean];
  "update-layer-opacity": [kind: string, opacity: number];
  "focus-layer": [kind: string];
  "update-scene-glb": [kind: SceneGlbKind, visible: boolean];
  "focus-scene-glb": [kind: SceneGlbKind];
  "update-radar-layer": [kind: RadarControlKind, patch: { visible?: boolean; opacity?: number }];
  "select-radar-height": [heightM: number];
  "focus-station": [radarId: string];
  "show-station-detail": [radarId: string];
  "hide-station-detail": [radarId: string];
}>();

const tabs: Array<{ id: DockTab; label: string }> = [
  { id: "catalog", label: "模型库" },
  { id: "layers", label: "图层" },
  { id: "data", label: "数据" }
];
const activeTab = ref<DockTab>(props.activeTab);
const search = ref(props.modelSearch);
const modelIcons: Record<ModelId, Component> = { radar: Aim, uav: Position, watchpost: View, artillery: Location, reconVehicle: Van, mobility: Guide, airCorridor: Compass };
const modelGroups = computed(() => groupModels(search.value));

watch(() => props.activeTab, (tab) => { activeTab.value = tab; });
watch(() => props.modelSearch, (query) => { search.value = query; });

function selectTab(tab: DockTab) {
  activeTab.value = tab;
  emit("update:activeTab", tab);
}

function updateSearch(event: Event) {
  search.value = (event.target as HTMLInputElement).value;
  emit("update:modelSearch", search.value);
}

function groupModels(query: string) {
  const needle = query.trim().toLowerCase();
  const groups: Array<{ label: string; models: ModelId[] }> = [
    { label: "观测与侦察", models: ["radar", "uav", "watchpost", "reconVehicle"] },
    { label: "火力与机动", models: ["artillery", "mobility", "airCorridor"] }
  ];
  return groups.map((group) => ({
    ...group,
    models: group.models.filter((modelId) => !needle || MODEL_REGISTRY[modelId].label.toLowerCase().includes(needle))
  })).filter((group) => group.models.length);
}
</script>

<style scoped>
.workbench-dock { display: flex; flex-direction: column; height: 100%; overflow: hidden; color: var(--wb-fg); }
.workbench-dock__tabs { display: flex; gap: 4px; flex: none; padding: 8px 8px 0; border-bottom: 1px solid var(--wb-border-soft); }
.workbench-dock__tabs button { padding: 8px 12px; margin-bottom: -1px; color: var(--wb-muted); background: transparent; border: 0; border-bottom: 2px solid transparent; cursor: pointer; }
.workbench-dock__tabs button[aria-selected="true"] { color: var(--wb-accent); font-weight: 600; border-bottom-color: var(--wb-accent); }
.workbench-dock__body { flex: 1; min-height: 0; padding: 12px; overflow: auto; }
.workbench-dock__search { display: flex; margin-bottom: 12px; }
.workbench-dock__search input { width: 100%; height: 30px; padding: 0 12px; color: var(--wb-fg); background: var(--wb-surface); border: 1px solid var(--wb-border-soft); border-radius: 8px; outline: 0; }
.workbench-dock__search input:focus { background: var(--wb-bg); border-color: var(--wb-accent); box-shadow: 0 0 0 4px rgb(0 113 227 / 25%); }
.workbench-dock__group { margin-bottom: 4px; }
.workbench-dock__group > summary { display: flex; align-items: center; gap: 6px; padding: 6px 8px; color: var(--wb-fg-2); font-size: 12px; font-weight: 600; cursor: pointer; list-style: none; }
.workbench-dock__group > summary::-webkit-details-marker { display: none; }
.workbench-dock__group > summary::before { content: ">"; color: var(--wb-meta); transition: transform 150ms ease; }
.workbench-dock__group[open] > summary::before { transform: rotate(90deg); }
.workbench-dock__group > summary span { margin-left: auto; color: var(--wb-meta); font-weight: 400; }
.workbench-dock__model { display: flex; width: 100%; align-items: center; gap: 8px; padding: 6px 8px 6px 22px; color: var(--wb-fg); font: inherit; text-align: left; background: transparent; border: 0; border-radius: 8px; cursor: pointer; }
.workbench-dock__model:hover { background: var(--wb-surface); }
.workbench-dock__model.is-selected { color: #0066cc; font-weight: 600; background: rgb(0 113 227 / 9%); }
.workbench-dock__empty { padding: 24px; margin: 0; color: var(--wb-meta); font-size: 12px; text-align: center; }
:deep(.task-layer-row), :deep(.scene-glb-row) { min-height: 40px; border-color: var(--wb-border-soft); }
:deep(.radar-layer-controls) { position: static; width: auto; border: 0; border-radius: 0; box-shadow: none; }
</style>
