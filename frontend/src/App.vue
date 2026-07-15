<template>
  <WorkspaceShell
    :model-value="workspace.selectedModel.value"
    :dem-label="selectedDem?.filename ?? 'No DEM selected'"
    :connected="!taskManager.connectionInterrupted.value"
    @select-model="selectModel"
    @open-history="historyOpen = true"
  >
    <template #parameters>
      <div class="workspace-parameter-stack">
        <header class="workspace-panel-heading">
          <div>
            <span>Analysis model</span>
            <h1 data-parameter-heading>{{ activeDefinition.label }}</h1>
          </div>
        </header>
        <DemSelector
          class="workspace-dem-selector"
          :dems="demManager.dems.value"
          :model-value="demManager.selectedDem.value"
          :loading="demManager.loading.value"
          :uploading="demManager.uploading.value"
          @update:model-value="demManager.select"
          @upload="(file) => runCommand(demManager.upload, file)"
          @delete="(demId) => runCommand(demManager.remove, demId)"
          @refresh="runCommand(demManager.load)"
        />
        <ModelParameterPanel
          :model-id="workspace.selectedModel.value"
          :model-value="workspace.currentDraft.value.request"
          :submitting="submitting"
          @update:model-value="updateDraft"
          @submit="submitTask"
          @activate-map-tool="activateMapTool"
        />
      </div>
    </template>

    <template #map>
      <div class="workspace-map-stack">
        <MapWorkspace
          :key="workspace.selectedModel.value"
          :kind="activeDefinition.spatialInput"
          :draft="mapWorkspace.draft.value"
          :editing="mapEditing"
          :edit-target="mapEditTarget"
          :dem="selectedDem"
          @map-ready="setMap"
          @spatial-edit="applyMapEdit"
          @finish="mapEditing = false"
        />
        <RadarLayerControls
          v-if="workspace.selectedModel.value === 'radar'"
          :layers="radarControlLayers"
          :height-options="heightOptions"
          :selected-height-m="selectedHeightM"
          @update-layer="updateRadarControl"
          @select-height="selectHeightLayer"
        />
        <ProfilePanel
          v-if="workspace.selectedModel.value === 'radar'"
          :profile="radarAnalysis.profile.value?.result ?? null"
          :loading="radarAnalysis.profileLoading.value"
          @close="clearProfile"
        />
        <FusionPanel
          v-if="workspace.selectedModel.value === 'radar'"
          :tasks="radarTasks"
          :result="radarAnalysis.fusion.value?.result ?? null"
          :loading="radarAnalysis.fusionLoading.value"
          @run="runFusion"
          @clear="clearFusion"
        />
      </div>
    </template>

    <template #results>
      <div
        v-if="selectedTaskContext"
        class="workspace-result-stack"
        :data-selected-task-id="selectedTaskContext.task.task_id"
      >
        <header class="workspace-panel-heading workspace-panel-heading--result">
          <div>
            <span>{{ getModelDefinition(selectedTaskContext.modelId).label }}</span>
            <h2>Task results</h2>
          </div>
          <div class="workspace-result-actions">
            <ElTooltip
              v-if="selectedTaskContext.modelId === 'radar' && selectedTaskContext.task.status === 'finished'"
              content="Select profile target"
              placement="bottom"
            >
              <ElButton
                circle
                :type="profilePicking ? 'primary' : 'default'"
                :icon="Aim"
                data-action="profile-tool"
                aria-label="Select radar profile target"
                @click="toggleProfilePicking"
              />
            </ElTooltip>
            <strong :data-status="selectedTaskContext.task.status">
              {{ selectedTaskContext.task.status }}
            </strong>
          </div>
        </header>
        <div class="workspace-result-content">
          <div v-if="radarLayerErrors.length" class="workspace-layer-errors" role="alert">
            <span v-for="message in radarLayerErrors" :key="message">{{ message }}</span>
          </div>
          <TaskResultPanel
            :model-id="selectedTaskContext.modelId"
            :task="selectedTaskContext.task"
            :metrics="mapWorkspace.taskMetrics.value"
            :output-files="mapWorkspace.outputFiles.value"
            :layer-states="mapWorkspace.layerStates.value"
            :scene-glb-state="mapWorkspace.sceneGlbStateFor(selectedTaskContext.task.task_id)"
            @layer-visibility="setLayerVisibility"
            @layer-opacity="setLayerOpacity"
            @layer-focus="focusLayer"
            @scene-glb-visibility="setSceneGlbVisibility"
            @scene-glb-focus="focusSceneGlb"
          />
        </div>
      </div>
      <div v-else class="workspace-empty-result">
        <strong>No task selected</strong>
        <span>Run an analysis or restore a task from history.</span>
      </div>
    </template>
  </WorkspaceShell>

  <TaskHistoryDrawer
    :open="historyOpen"
    :tasks-by-model="historyTasks"
    :task-manager="taskManager"
    @close="historyOpen = false"
    @restore="restoreRequest"
    @focus="focusTask"
    @deleted="removeDeletedTaskScene"
    @error="showError"
  />
</template>

<script setup lang="ts">
import type maplibregl from "maplibre-gl";
import { Aim } from "@element-plus/icons-vue";
import { ElButton, ElMessage, ElTooltip } from "element-plus";
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, shallowRef, toRaw, watch } from "vue";

import DemSelector from "./components/dem/DemSelector.vue";
import FusionPanel from "./components/FusionPanel.vue";
import ModelParameterPanel from "./components/forms/ModelParameterPanel.vue";
import WorkspaceShell from "./components/layout/WorkspaceShell.vue";
import MapWorkspace from "./components/map/MapWorkspace.vue";
import ProfilePanel from "./components/ProfilePanel.vue";
import TaskHistoryDrawer from "./components/tasks/TaskHistoryDrawer.vue";
import RadarLayerControls, {
  type RadarControlKind,
  type RadarControlLayer,
  type RadarHeightOption
} from "./components/tasks/RadarLayerControls.vue";
import TaskResultPanel from "./components/tasks/TaskResultPanel.vue";
import { useDemManager } from "./composables/useDemManager";
import { useMapWorkspace } from "./composables/useMapWorkspace";
import { useModelWorkspace, type ActiveDraft } from "./composables/useModelWorkspace";
import { useTaskManager } from "./composables/useTaskManager";
import type { SpatialDraftAction } from "./map/spatialInput";
import { clipProfileFromBounds } from "./map/beamClipProfile";
import {
  addOrUpdateClippedVolumeLayer,
  loadClippedVolumeData,
  removeClippedVolumeLayer
} from "./map/clippedVolumeLayer";
import { addOrUpdateRadarVolume, removeRadarVolume } from "./map/radarVolumeLayer";
import { addOrUpdateVoxelLayer, loadVoxelData, removeVoxelLayer } from "./map/voxelLayer";
import {
  addOrUpdateGeoJsonDataLayer,
  addOrUpdateProfileLayer,
  addRadarMarker,
  removeFusionLayers,
  removeProfileLayer,
  removeRadarMarker
} from "./map/mapLayers";
import { getModelDefinition, MODEL_IDS, type ModelId, type ModelRequestMap } from "./models/registry";
import {
  createRadarLayerAdapter,
  type RadarLayerPlan,
  type RadarTask
} from "./models/radar/layerAdapter";
import type { BaseModelRequest, OutputLayerDefinition, TaskSummary } from "./models/shared";
import { applySpatialDraftToRequest, spatialDraftFromRequest } from "./models/spatialAdapter";
import { useRadarAnalysis } from "./models/radar/useRadarAnalysis";
import { createHeightLayerLoader } from "./models/radar/heightLayerLoader";

type MapEditTarget = "auto" | "point" | "route" | "start" | "end" | "threat";
type GenericTask = TaskSummary<BaseModelRequest, unknown, unknown, unknown>;
interface SelectedTaskContext { modelId: ModelId; task: GenericTask }
interface HeightLayerData extends RadarHeightOption { visibleUrl: string; blockedUrl: string | null }
interface HeightManifest {
  height_layers?: Array<{
    height_m?: number;
    visible_filename?: string;
    blocked_filename?: string;
    visible_area_m2?: number;
    blocked_area_m2?: number;
  }>;
}

const workspace = useModelWorkspace();
const demManager = useDemManager(workspace);
const taskManager = useTaskManager({ pollIntervalMs: 1000 });
const radarAnalysis = useRadarAnalysis();
const mapWorkspace = useMapWorkspace(
  getModelDefinition(workspace.selectedModel.value).spatialInput,
  spatialDraftFromRequest(workspace.selectedModel.value, toRaw(workspace.currentDraft.value.request))
);
const map = shallowRef<maplibregl.Map | null>(null);
const historyOpen = ref(false);
const submitting = ref(false);
const mapEditing = ref(false);
const profilePicking = ref(false);
const mapEditTarget = ref<MapEditTarget>("auto");
const renderedTaskLayers = new Map<string, string>();
const renderedHeightLayers = new Map<string, string>();
const radarLayerErrors = ref<string[]>([]);
const heightOptions = ref<RadarHeightOption[]>([]);
const selectedHeightM = ref<number | null>(null);
const activeHeightData = shallowRef<HeightLayerData[]>([]);
const heightLayerLoader = createHeightLayerLoader(fetchJson);
let heightRenderToken = 0;
let lastRadarTaskId: string | null = null;
const radarControlLayers = reactive<RadarControlLayer[]>([
  { kind: "volume", label: "Radar volume", color: "#22c55e", visible: true, opacity: 0.62, available: true },
  { kind: "boundary", label: "Request boundary", color: "#94a3b8", visible: false, opacity: 0.45, available: true },
  { kind: "clipped", label: "Terrain-clipped beam", color: "#ef4444", visible: true, opacity: 0.66, available: false },
  { kind: "voxel", label: "Voxel cloud", color: "#06b6d4", visible: false, opacity: 0.8, available: false },
  { kind: "height", label: "Height coverage", color: "#f59e0b", visible: true, opacity: 0.24, available: false }
]);

const activeDefinition = computed(() => getModelDefinition(workspace.selectedModel.value));
const selectedDem = computed(() => demManager.dems.value.find(
  ({ dem_id }) => dem_id === demManager.selectedDem.value
) ?? null);
const historyTasks = computed(() => taskManager.tasksByModel as unknown as Partial<
  Record<ModelId, readonly GenericTask[]>
>);
const radarTasks = computed(() => taskManager.tasksByModel.radar as unknown as RadarTask[]);
const selectedTaskContext = computed<SelectedTaskContext | null>(() => {
  const key = taskManager.selectedTaskKey.value;
  if (!key) return null;
  const separator = key.indexOf(":");
  const modelId = key.slice(0, separator) as ModelId;
  const taskId = key.slice(separator + 1);
  if (!MODEL_IDS.includes(modelId)) return null;
  const task = taskManager.getTask(modelId, taskId) as GenericTask | undefined;
  return task ? { modelId, task } : null;
});

const radarLayers = createRadarLayerAdapter({
  renderVolume(plan) {
    if (!map.value || !mapReady(map.value)) return;
    const control = radarControl("volume");
    const boundary = radarControl("boundary");
    control.available = true;
    boundary.available = true;
    if (!control.visible && !boundary.visible) return;
    addOrUpdateRadarVolume(map.value, plan.request, {
      opacity: control.visible ? control.opacity : 0,
      clipProfile: plan.clipProfile,
      showScanPlane: control.visible,
      showFullRequestOutline: boundary.visible,
      referenceOpacity: boundary.opacity
    });
  },
  removeVolume() {
    if (map.value) removeRadarVolume(map.value);
  },
  loadVoxel(plan) {
    return loadVoxelData(plan.outputUrls.voxel_points_bin, plan.outputUrls.voxel_manifest_json);
  },
  renderVoxel(data) {
    const control = radarControl("voxel");
    control.available = true;
    if (control.visible && map.value && mapReady(map.value)) {
      addOrUpdateVoxelLayer(map.value, data, { opacity: control.opacity });
    }
  },
  removeVoxel() {
    if (map.value) removeVoxelLayer(map.value);
  },
  loadClipped(plan) {
    return loadClippedVolumeData(
      plan.outputUrls.clipped_volume_cells_bin,
      plan.outputUrls.clipped_volume_manifest_json
    );
  },
  renderClipped(data, plan) {
    if (!map.value || !mapReady(map.value)) return;
    const control = radarControl("clipped");
    control.available = true;
    if (!control.visible) return;
    addOrUpdateClippedVolumeLayer(map.value, data.cells, data.manifest, {
      opacity: control.opacity,
      scanMode: plan.request.coverage.scan_mode,
      azimuthDeg: plan.request.coverage.azimuth_deg,
      beamWidthDeg: plan.request.coverage.beam_width_deg,
      radarLon: plan.request.radar.lon,
      radarLat: plan.request.radar.lat
    });
  },
  removeClipped() {
    if (map.value) removeClippedVolumeLayer(map.value);
  },
  loadHeightLayers: loadHeightLayers,
  renderHeightLayers(data) {
    activeHeightData.value = data;
    heightOptions.value = data.map(({ heightM, label }) => ({ heightM, label }));
    if (!data.some(({ heightM }) => heightM === selectedHeightM.value)) {
      const targetHeight = selectedTaskContext.value?.task.request
        ? (selectedTaskContext.value.task as RadarTask).request?.target.height_m ?? 0
        : 0;
      selectedHeightM.value = data.find(({ heightM }) => heightM >= targetHeight)?.heightM
        ?? data.at(-1)?.heightM
        ?? null;
    }
    radarControl("height").available = data.length > 0;
    void renderSelectedHeightLayer();
  },
  removeHeightLayers
});

onMounted(async () => {
  taskManager.setVisibleModel(workspace.selectedModel.value);
  const results = await Promise.allSettled([
    demManager.load(),
    ...MODEL_IDS.map((modelId) => taskManager.refreshModel(modelId))
  ]);
  if (results.every(({ status }) => status === "rejected")) {
    ElMessage.error("Unable to load workspace data.");
  }
});

onBeforeUnmount(() => {
  radarAnalysis.dispose();
  radarLayers.dispose();
  if (map.value) {
    mapWorkspace.removeAllSceneGlbs(map.value);
    removeProfileLayer(map.value);
    removeFusionLayers(map.value);
    removeRadarMarker(map.value);
    if (import.meta.env.DEV) {
      const devWindow = window as Window & { __PYGEOMODEL_MAP__?: maplibregl.Map };
      if (devWindow.__PYGEOMODEL_MAP__ === map.value) {
        delete devWindow.__PYGEOMODEL_MAP__;
      }
    }
  }
  clearTaskLayers();
  taskManager.dispose();
  mapWorkspace.clearTaskOutputs();
});

watch(selectedTaskContext, async (context) => {
  const nextRadarTaskId = context?.modelId === "radar" ? context.task.task_id : null;
  if (nextRadarTaskId !== lastRadarTaskId) {
    radarLayers.clear();
    heightLayerLoader.setTask(nextRadarTaskId);
    lastRadarTaskId = nextRadarTaskId;
    resetRadarOutputControls();
  }
  if (!context || context.modelId !== "radar"
    || radarAnalysis.profile.value?.task.task_id !== context.task.task_id) {
    clearProfile();
  }
  if (!context) {
    mapWorkspace.clearTaskOutputs();
    radarLayers.clear();
    clearTaskLayers();
    syncRadarPreview();
    return;
  }
  const loaded = await mapWorkspace.loadTaskOutputs(context.modelId, context.task as never);
  const current = selectedTaskContext.value;
  if (!loaded || !current
    || current.modelId !== context.modelId
    || current.task.task_id !== context.task.task_id) return;
  renderTaskLayers();
  await syncRadarLayers(context);
}, { immediate: true });

watch(() => mapWorkspace.layerStates.value, renderTaskLayers, { deep: true });
watch(() => demManager.selectedDem.value, (nextDemId) => {
  if (map.value) mapWorkspace.removeIncompatibleSceneGlbs(map.value, nextDemId ?? "");
});
watch(() => workspace.drafts.radar, () => {
  if (workspace.selectedModel.value !== "radar") return;
  radarLayers.clear();
  syncRadarPreview();
}, { deep: true });

function selectModel(modelId: ModelId) {
  workspace.selectModel(modelId);
  taskManager.setVisibleModel(modelId);
  radarLayers.setRadarVisible(modelId === "radar");
  mapEditing.value = false;
  profilePicking.value = false;
  if (modelId !== "radar") {
    radarAnalysis.clearProfile();
    radarAnalysis.clearFusion();
    if (map.value) {
      removeRadarMarker(map.value);
      removeProfileLayer(map.value);
      removeFusionLayers(map.value);
    }
  }
  syncSpatialDraft();
  if (modelId === "radar") void nextTick(syncCurrentRadarView);
}

function updateDraft(request: BaseModelRequest) {
  workspace.currentDraft.value = {
    modelId: workspace.selectedModel.value,
    request
  } as ActiveDraft;
  syncSpatialDraft();
}

async function submitTask(request: BaseModelRequest) {
  submitting.value = true;
  try {
    await taskManager.submit(workspace.selectedModel.value, structuredClone(toRaw(request)));
  } catch (error) {
    showError(error);
  } finally {
    submitting.value = false;
  }
}

function restoreRequest(modelId: ModelId, request: BaseModelRequest) {
  workspace.currentDraft.value = { modelId, request } as ActiveDraft;
  taskManager.setVisibleModel(modelId);
  radarLayers.setRadarVisible(modelId === "radar");
  historyOpen.value = false;
  syncSpatialDraft();
}

function focusTask(modelId: ModelId, task: GenericTask) {
  taskManager.select(modelId, task.task_id);
  historyOpen.value = false;
}

function activateMapTool(operation: MapEditTarget = "auto") {
  profilePicking.value = false;
  mapEditTarget.value = operation;
  mapEditing.value = true;
}

function toggleProfilePicking() {
  profilePicking.value = !profilePicking.value;
  if (profilePicking.value) mapEditing.value = false;
}

function applyMapEdit(action: SpatialDraftAction) {
  const nextDraft = mapWorkspace.dispatch(action);
  const current = workspace.currentDraft.value;
  const request = applySpatialDraftToRequest(
    current.modelId,
    toRaw(current.request) as ModelRequestMap[typeof current.modelId],
    nextDraft
  );
  workspace.currentDraft.value = { modelId: current.modelId, request } as ActiveDraft;
  mapWorkspace.replaceDraft(spatialDraftFromRequest(current.modelId, request));
}

function syncSpatialDraft() {
  void nextTick(() => {
    const current = workspace.currentDraft.value;
    mapWorkspace.replaceDraft(spatialDraftFromRequest(
      current.modelId,
      toRaw(current.request) as ModelRequestMap[typeof current.modelId]
    ));
  });
}

function setMap(instance: maplibregl.Map) {
  if (map.value && map.value !== instance) {
    mapWorkspace.resetSceneGlbStates();
  }
  map.value = instance;
  if (import.meta.env.DEV) {
    (window as Window & { __PYGEOMODEL_MAP__?: maplibregl.Map })
      .__PYGEOMODEL_MAP__ = instance;
  }
  instance.on("load", handleMapLoad);
  instance.on("click", handleRadarMapClick);
  if (mapReady(instance)) handleMapLoad();
}

function handleMapLoad() {
  renderTaskLayers();
  radarLayers.clear();
  if (selectedTaskContext.value) void syncRadarLayers(selectedTaskContext.value);
  else syncRadarPreview();
  renderRadarAnalysisLayers();
}

function setLayerVisibility(kind: string, visible: boolean) {
  mapWorkspace.setTaskLayerVisibility(kind, visible);
}

function setLayerOpacity(kind: string, opacity: number) {
  mapWorkspace.setTaskLayerOpacity(kind, opacity);
}

function focusLayer(kind: string) {
  if (map.value) mapWorkspace.focusTaskLayer(map.value, kind);
}

function removeDeletedTaskScene(_modelId: ModelId, taskId: string) {
  if (map.value) mapWorkspace.removeSceneGlb(map.value, taskId);
}

async function setSceneGlbVisibility(visible: boolean) {
  const instance = map.value;
  const context = selectedTaskContext.value;
  const selectedDemId = demManager.selectedDem.value;
  if (!instance || !context || !selectedDemId) return;
  await mapWorkspace.setSceneGlbVisibility(
    instance,
    selectedDemId,
    context.modelId,
    context.task as never,
    visible
  );
}

function focusSceneGlb() {
  const instance = map.value;
  const context = selectedTaskContext.value;
  if (instance && context) {
    mapWorkspace.focusSceneGlb(instance, context.task.task_id);
  }
}

function renderTaskLayers() {
  const instance = map.value;
  const context = selectedTaskContext.value;
  if (!instance || !context || !mapReady(instance)) return;
  const definitions = getModelDefinition(context.modelId).outputLayers;
  const activeIds = new Set<string>();
  for (const state of mapWorkspace.layerStates.value) {
    if (state.status !== "ready" || !state.data) continue;
    const definition = definitions.find(({ kind }) => kind === state.kind);
    if (!definition) continue;
    const id = `task-output-${sanitizeId(state.kind)}`;
    activeIds.add(id);
    renderGeoJsonLayer(instance, id, state.data, definition, state.visible, state.opacity);
  }
  for (const id of [...renderedTaskLayers.keys()]) {
    if (!activeIds.has(id)) removeGeoJsonLayer(instance, id);
  }
}

function clearTaskLayers() {
  if (!map.value) return;
  for (const id of [...renderedTaskLayers.keys()]) removeGeoJsonLayer(map.value, id);
}

async function syncRadarLayers(context: SelectedTaskContext) {
  if (workspace.selectedModel.value !== "radar") {
    radarLayers.setRadarVisible(false);
    if (map.value) removeRadarMarker(map.value);
    return;
  }
  if (context.modelId !== "radar") {
    radarLayers.clear();
    if (workspace.selectedModel.value === "radar") syncRadarPreview();
    return;
  }
  if (context.task.status !== "finished") {
    radarLayers.clear();
    syncRadarPreview();
    return;
  }
  const radarTask = context.task as RadarTask;
  const dem = demManager.dems.value.find(({ dem_id }) => dem_id === context.task.dem_id) ?? selectedDem.value;
  const hasSceneGlb = radarTask.output_files.some(
    (file) => file.kind === "scene_glb" && file.exists
  );
  if (hasSceneGlb) {
    radarLayers.clear();
    radarLayerErrors.value = [];
  } else {
    await radarLayers.showTask(radarTask, dem?.bounds ?? []);
  }
  const current = selectedTaskContext.value;
  if (workspace.selectedModel.value !== "radar"
    || current?.modelId !== "radar"
    || current.task.task_id !== radarTask.task_id) return;
  radarLayerErrors.value = Object.values(radarLayers.errors)
    .filter((error): error is Error => error instanceof Error)
    .map(({ message }) => message);
  if (map.value && radarTask.request) {
    addRadarMarker(
      map.value,
      radarTask.request.radar.lon,
      radarTask.request.radar.lat,
      radarTask.request.radar.height_m
    );
  }
}

function syncCurrentRadarView() {
  const context = selectedTaskContext.value;
  if (context?.modelId === "radar") void syncRadarLayers(context);
  else syncRadarPreview();
  renderRadarAnalysisLayers();
}

function syncRadarPreview() {
  const instance = map.value;
  if (!instance || !mapReady(instance) || workspace.selectedModel.value !== "radar") return;
  const request = workspace.drafts.radar;
  const volumeControl = radarControl("volume");
  const boundaryControl = radarControl("boundary");
  volumeControl.available = true;
  boundaryControl.available = true;
  addRadarMarker(instance, request.radar.lon, request.radar.lat, request.radar.height_m);
  const dem = demManager.dems.value.find(({ dem_id }) => dem_id === request.dem_id) ?? selectedDem.value;
  if ((!volumeControl.visible && !boundaryControl.visible) || !dem || dem.bounds.length !== 4) {
    removeRadarVolume(instance);
    return;
  }
  addOrUpdateRadarVolume(instance, request, {
    opacity: volumeControl.visible ? volumeControl.opacity : 0,
    showScanPlane: volumeControl.visible,
    clipProfile: clipProfileFromBounds(dem.bounds, request.radar, request.coverage.max_range_m),
    showFullRequestOutline: boundaryControl.visible,
    referenceOpacity: boundaryControl.opacity
  });
}

async function handleRadarMapClick(event: maplibregl.MapMouseEvent) {
  if (!profilePicking.value) return;
  const context = selectedTaskContext.value;
  if (!context || context.modelId !== "radar" || context.task.status !== "finished") return;
  profilePicking.value = false;
  try {
    await radarAnalysis.runProfile(context.task as RadarTask, {
      lon: event.lngLat.lng,
      lat: event.lngLat.lat
    });
    const profile = radarAnalysis.profile.value;
    const current = selectedTaskContext.value;
    if (workspace.selectedModel.value !== "radar"
      || !profile || !current || current.task.task_id !== profile.task.task_id) return;
    renderProfileLayer();
  } catch (error) {
    showError(error);
  }
}

function renderProfileLayer() {
  const instance = map.value;
  const profile = radarAnalysis.profile.value;
  const current = selectedTaskContext.value;
  if (workspace.selectedModel.value !== "radar"
    || !instance || !profile || !mapReady(instance)
    || current?.modelId !== "radar"
    || current.task.task_id !== profile.task.task_id) return;
  const result = profile.result;
  const obstruction = result.blocked
    && result.obstruction_lon != null
    && result.obstruction_lat != null
    ? [result.obstruction_lon, result.obstruction_lat] as [number, number]
    : null;
  addOrUpdateProfileLayer(
    instance,
    [profile.task.request!.radar.lon, profile.task.request!.radar.lat],
    [profile.target.lon, profile.target.lat],
    obstruction
  );
}

function clearProfile() {
  radarAnalysis.clearProfile();
  if (map.value) removeProfileLayer(map.value);
}

async function runFusion(taskIds: string[]) {
  const tasks = radarTasks.value.filter(({ task_id }) => taskIds.includes(task_id));
  try {
    await radarAnalysis.runFusion(tasks);
    renderFusionLayers();
  } catch (error) {
    showError(error);
  }
}

function renderFusionLayers() {
  const instance = map.value;
  const fusion = radarAnalysis.fusion.value?.result;
  if (workspace.selectedModel.value !== "radar" || !instance || !fusion || !mapReady(instance)) return;
  addOrUpdateGeoJsonDataLayer(instance, "fusion-visible-layer", cloneGeoJson(fusion.visible_union_geojson), {
    "fill-color": "#059669", "fill-opacity": 0.22
  }, { "line-color": "#047857", "line-opacity": 0.48, "line-width": 1 });
  addOrUpdateGeoJsonDataLayer(instance, "fusion-overlap-layer", cloneGeoJson(fusion.overlap_geojson), {
    "fill-color": "#7c3aed", "fill-opacity": 0.34
  }, { "line-color": "#6d28d9", "line-opacity": 0.52, "line-width": 1 });
  addOrUpdateGeoJsonDataLayer(instance, "fusion-blind-layer", cloneGeoJson(fusion.blind_geojson), {
    "fill-color": "#ef4444", "fill-opacity": 0.3
  }, { "line-color": "#dc2626", "line-opacity": 0.5, "line-width": 1 });
}

function clearFusion() {
  radarAnalysis.clearFusion();
  if (map.value) removeFusionLayers(map.value);
}

function renderRadarAnalysisLayers() {
  if (workspace.selectedModel.value !== "radar") return;
  renderProfileLayer();
  renderFusionLayers();
}

async function loadHeightLayers(plan: RadarLayerPlan): Promise<HeightLayerData[]> {
  const manifestUrl = plan.outputUrls.height_layers_manifest_json;
  const manifest = await fetchJson<HeightManifest>(manifestUrl);
  return (manifest.height_layers ?? []).flatMap((layer) => {
    if (layer.height_m == null || !layer.visible_filename) return [];
    const visibleArea = formatArea(layer.visible_area_m2);
    const blockedArea = formatArea(layer.blocked_area_m2);
    return [{
      heightM: layer.height_m,
      label: `${formatHeight(layer.height_m)} | visible ${visibleArea} | blocked ${blockedArea}`,
      visibleUrl: resolveRelativeUrl(manifestUrl, layer.visible_filename),
      blockedUrl: layer.blocked_filename ? resolveRelativeUrl(manifestUrl, layer.blocked_filename) : null
    }];
  }).sort((left, right) => left.heightM - right.heightM);
}

function removeHeightLayers() {
  heightRenderToken++;
  if (!map.value) return;
  for (const id of [...renderedHeightLayers.keys()]) {
    removeGeoJsonLayer(map.value, id, renderedHeightLayers);
  }
}

async function renderSelectedHeightLayer() {
  removeHeightLayers();
  const instance = map.value;
  const control = radarControl("height");
  const selected = activeHeightData.value.find(({ heightM }) => heightM === selectedHeightM.value);
  if (!instance || !mapReady(instance) || !control.visible || !selected) return;
  const token = ++heightRenderToken;
  const taskId = selectedTaskContext.value?.task.task_id;
  try {
    const loaded = await heightLayerLoader.load(selected.heightM, selected.visibleUrl, selected.blockedUrl);
    if (!loaded || token !== heightRenderToken || selectedTaskContext.value?.task.task_id !== taskId) return;
    renderGeoJsonLayer(instance, "radar-height-visible", loaded.visible, {
      kind: "height-visible", label: "Height visible", color: "#22c55e", geometry: "fill", defaultOpacity: 0.2
    }, true, control.opacity, renderedHeightLayers);
    if (loaded.blocked) {
      renderGeoJsonLayer(instance, "radar-height-blocked", loaded.blocked, {
        kind: "height-blocked", label: "Height blocked", color: "#ef4444", geometry: "fill", defaultOpacity: 0.14
      }, true, Math.max(0.1, control.opacity * 0.7), renderedHeightLayers);
    }
  } catch (error) {
    if (token === heightRenderToken) radarLayerErrors.value = [...radarLayerErrors.value, errorMessage(error)];
  }
}

function updateRadarControl(kind: RadarControlKind, patch: { visible?: boolean; opacity?: number }) {
  Object.assign(radarControl(kind), patch);
  if (kind === "height") {
    void renderSelectedHeightLayer();
    return;
  }
  refreshRadarLayerRendering();
}

function selectHeightLayer(heightM: number) {
  selectedHeightM.value = heightM;
  void renderSelectedHeightLayer();
}

function refreshRadarLayerRendering() {
  if (workspace.selectedModel.value !== "radar") return;
  const context = selectedTaskContext.value;
  if (context?.modelId === "radar" && context.task.status === "finished") {
    radarLayers.setRadarVisible(false);
    radarLayers.setRadarVisible(true);
  } else {
    syncRadarPreview();
  }
}

function radarControl(kind: RadarControlKind) {
  return radarControlLayers.find((layer) => layer.kind === kind)!;
}

function resetRadarOutputControls() {
  for (const kind of ["clipped", "voxel", "height"] as const) radarControl(kind).available = false;
  heightOptions.value = [];
  activeHeightData.value = [];
  selectedHeightM.value = null;
  removeHeightLayers();
  radarLayerErrors.value = [];
}

function renderGeoJsonLayer(
  instance: maplibregl.Map,
  id: string,
  data: GeoJSON.GeoJSON,
  definition: OutputLayerDefinition,
  visible: boolean,
  opacity: number,
  registry = renderedTaskLayers
) {
  const sourceId = `${id}-source`;
  const source = instance.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;
  if (source) source.setData(data);
  else instance.addSource(sourceId, { type: "geojson", data });

  if (!instance.getLayer(id)) {
    if (definition.geometry === "line") {
      instance.addLayer({ id, source: sourceId, type: "line", paint: { "line-color": definition.color, "line-width": 3 } });
    } else if (definition.geometry === "circle") {
      instance.addLayer({ id, source: sourceId, type: "circle", paint: { "circle-color": definition.color, "circle-radius": 5 } });
    } else {
      instance.addLayer({ id, source: sourceId, type: "fill", paint: { "fill-color": definition.color } });
    }
  }
  instance.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
  const opacityProperty = definition.geometry === "line"
    ? "line-opacity"
    : definition.geometry === "circle" ? "circle-opacity" : "fill-opacity";
  instance.setPaintProperty(id, opacityProperty, opacity);
  registry.set(id, sourceId);
}

function removeGeoJsonLayer(
  instance: maplibregl.Map,
  id: string,
  registry = renderedTaskLayers
) {
  const sourceId = registry.get(id) ?? `${id}-source`;
  if (instance.getLayer(id)) instance.removeLayer(id);
  if (instance.getSource(sourceId)) instance.removeSource(sourceId);
  registry.delete(id);
}

async function runCommand<T extends unknown[]>(command: (...args: T) => unknown, ...args: T) {
  try {
    await command(...args);
  } catch (error) {
    showError(error);
  }
}

function showError(error: unknown) {
  ElMessage.error(errorMessage(error));
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

function formatHeight(heightM: number) {
  return heightM >= 1000 ? `${heightM / 1000} km` : `${heightM} m`;
}

function formatArea(areaM2?: number) {
  if (!areaM2) return "0 km²";
  return `${(areaM2 / 1_000_000).toFixed(areaM2 >= 10_000_000 ? 1 : 2)} km²`;
}

function sanitizeId(value: string) {
  return value.replace(/[^a-zA-Z0-9_-]/g, "-");
}

function mapReady(instance: maplibregl.Map) {
  return typeof instance.isStyleLoaded !== "function" || instance.isStyleLoaded();
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Layer request failed (${response.status})`);
  return response.json() as Promise<T>;
}

function resolveRelativeUrl(base: string, filename: string) {
  return new URL(filename, new URL(base, window.location.origin)).toString();
}

function cloneGeoJson(value: object): GeoJSON.GeoJSON {
  return structuredClone(toRaw(value)) as GeoJSON.GeoJSON;
}
</script>
