<template>
  <section class="workbench-dock" aria-label="工作区面板">
    <nav class="workbench-dock__tabs" role="tablist">
      <button v-for="tab in tabs" :key="tab.id" type="button" :data-dock-tab="tab.id" :aria-selected="activeTab === tab.id" @click="selectTab(tab.id)">
        {{ tab.label }}
      </button>
    </nav>

    <div v-show="activeTab === 'catalog'" class="workbench-dock__body">
      <label class="workbench-dock__search"><span class="sr-only">搜索分析模型</span><input :value="search" type="search" placeholder="搜索模型" aria-label="Search analysis models" @input="updateSearch"></label>
      <details v-for="group in modelGroups" :key="group.label" open class="tree-group">
        <summary>{{ group.label }}<span>{{ group.models.length }}</span></summary>
        <button v-for="modelId in group.models" :key="modelId" type="button" class="model-row" :class="{ 'is-selected': modelId === modelValue }" :data-model-id="modelId" @click="emit('select-model', modelId)">
          <ElIcon><component :is="modelIcons[modelId]" /></ElIcon><span>{{ MODEL_REGISTRY[modelId].label }}</span>
        </button>
      </details>
      <p v-if="!modelGroups.length" class="empty-state">没有匹配的分析模型</p>
    </div>

    <div v-show="activeTab === 'layers'" class="workbench-dock__body">
      <details open class="tree-group">
        <summary>任务结果图层<span>{{ resultLayerCount }}</span></summary>
        <label v-for="definition in layerDefinitions" :key="definition.kind" class="layer-row" :data-layer-kind="definition.kind">
          <input type="checkbox" :checked="layerState(definition.kind)?.visible ?? false" :aria-label="`显示${definition.label}`" @change="emit('update-layer-visibility', definition.kind, checked($event))">
          <input class="layer-row__color" type="color" data-layer-color :value="layerState(definition.kind)?.color ?? definition.color" :aria-label="`${definition.label} color`" @input="emit('update-layer-color', definition.kind, color($event))">
          <span>{{ definition.label }}</span>
          <input type="range" min="0" max="1" step="0.05" :value="layerState(definition.kind)?.opacity ?? 1" :aria-label="`${definition.label}透明度`" @input="emit('update-layer-opacity', definition.kind, number($event))">
          <button type="button" aria-label="定位图层" @click="emit('focus-layer', definition.kind)"><ElIcon><Location /></ElIcon></button>
        </label>
        <label v-for="entry in sceneEntries" :key="entry.id" class="layer-row" :data-layer-id="entry.id" :data-layer-kind="entry.kind">
          <input type="checkbox" :checked="entry.state.visible" :aria-label="`显示${entry.file.label}`" @change="emit('update-scene-glb', entry.id, checked($event))">
          <input class="layer-row__color" type="color" data-scene-glb-color :value="entry.state.color ?? sceneColor(entry.kind)" :aria-label="`${entry.file.label} color`" @input="emit('update-scene-glb-color', entry.id, color($event))"><span>{{ entry.file.label }}</span><button type="button" class="layer-row__reset" data-scene-glb-reset-color aria-label="恢复原始配色" title="恢复原始配色" @click="emit('reset-scene-glb-color', entry.id)"><ElIcon><Refresh /></ElIcon></button>
          <small>{{ sceneLabel(entry.state.status) }}</small>
          <button type="button" aria-label="定位三维模型" @click="emit('focus-scene-glb', entry.id)"><ElIcon><Location /></ElIcon></button>
        </label>
        <p v-if="!resultLayerCount" class="empty-state">尚未加载任务图层</p>
      </details>

      <details v-if="multiRadarStations.length" open class="tree-group">
        <summary>协同雷达站<span>{{ multiRadarStations.length }}</span></summary>
        <div v-for="station in multiRadarStations" :key="station.radar_id" class="station-row">
          <i :data-status="station.status"></i><span>{{ station.name || station.radar_id }}</span><small>{{ station.message }}</small>
          <button type="button" aria-label="定位雷达站" @click="emit('focus-station', station.radar_id)"><ElIcon><Location /></ElIcon></button>
        </div>
      </details>
      <slot name="base-layers" />
    </div>

    <div v-show="activeTab === 'data'" class="workbench-dock__body"><slot name="data"><p class="empty-state">暂无 DEM 或任务输出文件</p></slot></div>
  </section>
</template>

<script setup lang="ts">
import { Aim, Compass, Guide, Location, Position, Refresh, Van, View } from "@element-plus/icons-vue";
import { ElIcon } from "element-plus";
import { computed, ref, watch, type Component } from "vue";

import type { SceneGlbKind, SceneGlbOverlayState, TaskOutputLayerState } from "../../composables/useMapWorkspace";
import { MODEL_REGISTRY, type ModelId } from "../../models/registry";
import type { OutputFile, OutputLayerDefinition } from "../../models/shared";
import type { MultiRadarStationSummary } from "../../models/multiRadar/types";

type DockTab = "catalog" | "layers" | "data";
export type RadarControlKind = "volume" | "boundary" | "clipped" | "voxel" | "height";
export interface RadarControlLayer { kind: RadarControlKind; label: string; color: string; visible: boolean; opacity: number; available: boolean }
export interface RadarHeightOption { heightM: number; label: string }
export interface WorkbenchSceneEntry { id: string; taskId: string; kind: SceneGlbKind; file: OutputFile; state: SceneGlbOverlayState }

const props = withDefaults(defineProps<{
  modelValue: ModelId; activeTab?: DockTab; modelSearch?: string; layerDefinitions?: readonly OutputLayerDefinition[];
  layerStates?: readonly TaskOutputLayerState[]; sceneEntries?: readonly WorkbenchSceneEntry[]; multiRadarStations?: MultiRadarStationSummary[];
}>(), { activeTab: "catalog", modelSearch: "", layerDefinitions: () => [], layerStates: () => [], sceneEntries: () => [], multiRadarStations: () => [] });

const emit = defineEmits<{
  "select-model": [modelId: ModelId]; "update:activeTab": [tab: DockTab]; "update:modelSearch": [query: string];
  "update-layer-visibility": [kind: string, visible: boolean]; "update-layer-opacity": [kind: string, opacity: number]; "update-layer-color": [kind: string, color: string]; "focus-layer": [kind: string];
  "update-scene-glb": [entryId: string, visible: boolean]; "update-scene-glb-color": [entryId: string, color: string]; "reset-scene-glb-color": [entryId: string]; "focus-scene-glb": [entryId: string]; "focus-station": [radarId: string];
}>();

const tabs: Array<{ id: DockTab; label: string }> = [{ id: "catalog", label: "模型库" }, { id: "layers", label: "图层" }, { id: "data", label: "数据" }];
const activeTab = ref<DockTab>(props.activeTab);
const search = ref(props.modelSearch);
const modelIcons: Record<ModelId, Component> = { radar: Aim, uav: Position, watchpost: View, artillery: Location, reconVehicle: Van, mobility: Guide, airCorridor: Compass };
const modelGroups = computed(() => groupModels(search.value));
const resultLayerCount = computed(() => props.layerDefinitions.length + props.sceneEntries.length);

watch(() => props.activeTab, (tab) => { activeTab.value = tab; });
watch(() => props.modelSearch, (query) => { search.value = query; });
function selectTab(tab: DockTab) { activeTab.value = tab; emit("update:activeTab", tab); }
function updateSearch(event: Event) { search.value = (event.target as HTMLInputElement).value; emit("update:modelSearch", search.value); }
function checked(event: Event) { return (event.target as HTMLInputElement).checked; }
function number(event: Event) { return Number((event.target as HTMLInputElement | HTMLSelectElement).value); }
function color(event: Event) { return (event.target as HTMLInputElement).value; }
function layerState(kind: string) { return props.layerStates.find((state) => state.kind === kind); }
function sceneColor(kind: SceneGlbKind) { return kind === "radar_platform_glb" ? "#d99a24" : "#0f9f78"; }
function sceneLabel(status: SceneGlbOverlayState["status"]) { return { idle: "待加载", loading: "加载中", visible: "已加载", error: "加载失败" }[status]; }
function groupModels(query: string) {
  const needle = query.trim().toLowerCase();
  return [{ label: "观测与侦察", models: ["radar", "uav", "watchpost", "reconVehicle"] as ModelId[] }, { label: "火力与机动", models: ["artillery", "mobility", "airCorridor"] as ModelId[] }]
    .map((group) => ({ ...group, models: group.models.filter((modelId) => !needle || MODEL_REGISTRY[modelId].label.toLowerCase().includes(needle)) })).filter((group) => group.models.length);
}
</script>

<style scoped>
.workbench-dock{display:flex;height:100%;flex-direction:column;overflow:hidden;color:var(--wb-fg)}.workbench-dock__tabs{display:flex;gap:20px;padding:0 16px;border-bottom:1px solid var(--wb-border-soft)}.workbench-dock__tabs button{height:48px;padding:0;border:0;border-bottom:2px solid transparent;background:transparent;color:var(--wb-muted);font:inherit;cursor:pointer}.workbench-dock__tabs button[aria-selected="true"]{color:var(--wb-accent);font-weight:600;border-bottom-color:var(--wb-accent)}.workbench-dock__body{min-height:0;flex:1;overflow:auto;padding:12px}.workbench-dock__search{display:block;margin-bottom:12px}.workbench-dock__search input{width:100%;height:32px;padding:0 10px;border:1px solid var(--wb-border);border-radius:8px;background:var(--wb-surface);color:var(--wb-fg);outline:0}.tree-group{margin:0 0 8px}.tree-group summary{display:flex;gap:6px;padding:8px 4px;color:var(--wb-fg-2);font-size:12px;font-weight:600;list-style:none;cursor:pointer}.tree-group summary::before{content:">";color:var(--wb-meta);transform:rotate(90deg)}.tree-group summary span{margin-left:auto;color:var(--wb-meta);font-weight:400}.model-row,.layer-row,.station-row{display:grid;width:100%;align-items:center;gap:8px;min-height:36px;padding:4px;border:0;border-bottom:1px solid var(--wb-border-soft);background:transparent;color:var(--wb-fg);font:inherit;text-align:left}.model-row{grid-template-columns:18px minmax(0,1fr);padding-left:18px;cursor:pointer}.model-row:hover,.model-row.is-selected{background:var(--wb-surface)}.model-row.is-selected{color:var(--wb-accent);font-weight:600}.layer-row{grid-template-columns:16px 10px minmax(0,1fr) 28px 62px 24px}.layer-row input[type="checkbox"]{width:16px;height:16px;margin:0;accent-color:var(--wb-accent)}.layer-row input[type="color"]{width:28px;height:28px;padding:2px;border:0;background:transparent;cursor:pointer}.layer-row input[type="range"]{width:62px;margin:0;accent-color:var(--wb-accent)}.layer-row i,.station-row i{width:10px;height:10px;border-radius:2px;background:#2e6be6}.layer-row__glb{background:#7856ff!important}.layer-row button,.station-row button{display:grid;width:24px;height:24px;place-items:center;border:0;border-radius:6px;background:transparent;color:var(--wb-muted);cursor:pointer}.layer-row small{color:var(--wb-meta);font-size:11px;text-align:right}.station-row{grid-template-columns:10px minmax(0,1fr) minmax(0,1fr) 24px;padding-left:18px}.station-row small{overflow:hidden;color:var(--wb-meta);font-size:11px;text-overflow:ellipsis;white-space:nowrap}.station-row i[data-status="finished"]{background:#18a957}.station-row i[data-status="failed"]{background:#e5484d}.empty-state{margin:0;padding:20px 8px;color:var(--wb-meta);font-size:12px;text-align:center}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}
.layer-row{grid-template-columns:16px 22px minmax(0,1fr) 62px 24px}
.layer-row input[type="color"].layer-row__color{width:22px;height:22px;padding:1px;border:1px solid var(--wb-border);border-radius:3px;background:var(--wb-surface);cursor:pointer}
.layer-row input[type="color"].layer-row__color::-webkit-color-swatch-wrapper{padding:0}
.layer-row input[type="color"].layer-row__color::-webkit-color-swatch{border:0;border-radius:2px}
.layer-row[data-layer-id]{grid-template-columns:16px 22px minmax(0,1fr) 24px 62px 24px}
.layer-row__reset{grid-column:4}
</style>
