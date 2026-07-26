<template>
  <GisWorkbenchShell :tasks-collapsed="presentation.taskCenterCollapsed.value" @update:tasks-collapsed="presentation.toggleTaskCenter">
    <template #topbar><WorkbenchTopbar :dem-label="selectedDem?.filename ?? 'No DEM selected'" :connected="!taskManager.connectionInterrupted.value" :search="modelSearch" @update:search="modelSearch = $event" /></template>
    <template #dock>
      <WorkbenchDock :model-value="workspace.selectedModel.value" :active-tab="presentation.dockTab.value" :model-search="modelSearch" :layer-definitions="selectedTaskContext?.task.status === 'finished' ? getModelDefinition(selectedTaskContext.modelId).outputLayers : []" :layer-states="mapWorkspace.layerStates.value" :scene-entries="workbenchSceneEntries" :multi-radar-stations="activeMultiRadarTask?.stations ?? []" @select-model="selectWorkbenchModel" @update:active-tab="presentation.selectDockTab" @update:model-search="modelSearch = $event" @update-layer-visibility="setLayerVisibility" @update-layer-opacity="setLayerOpacity" @focus-layer="focusLayer" @update-scene-glb="setSceneGlbVisibility" @focus-scene-glb="focusSceneGlb" @focus-station="focusMultiRadarStation">
        <template #data><WorkbenchDataPane :dems="demManager.dems.value" :model-value="demManager.selectedDem.value" :loading="demManager.loading.value" :uploading="demManager.uploading.value" @update:model-value="demManager.select" @upload="(file) => runCommand(demManager.upload, file)" @delete="(demId) => runCommand(demManager.remove, demId)" @refresh="runCommand(demManager.load)" /></template>
      </WorkbenchDock>
    </template>
    <template #map>
      <div class="workspace-map-stack"><MapWorkspace :key="workspace.selectedModel.value" :kind="activeDefinition.spatialInput" :draft="mapWorkspace.draft.value" :editing="mapEditing" :edit-target="mapEditTarget" :dem="selectedDem" @map-ready="setMap" @spatial-edit="applyMapEdit" @out-of-bounds="showError(new Error('Pick a location inside the selected DEM.'))" /><MapPickBar v-if="mapEditing" :target="mapEditTarget === 'auto' ? 'point' : mapEditTarget" @cancel="finishMapPicking" @undo="applyMapEdit({ type: 'undo' })" @finish="finishMapPicking" /></div>
    </template>
    <template #tasks><WorkbenchTaskCenter :rows="workbenchTaskRows" :multi-radar-tasks="multiRadarTasks" :active-tab="presentation.taskTab.value" @update:active-tab="presentation.selectTaskTab" @select-task="selectWorkbenchTask" @select-multi-radar-task="selectMultiRadarTask" /></template>
    <template #status>
      <div class="workbench-status">
        <span class="workbench-status__item workbench-status__map-info">坐标 <span class="workbench-status__mono">—</span></span>
        <span class="workbench-status__item workbench-status__map-info">高程 <span class="workbench-status__mono">—</span></span>
        <span class="workbench-status__item workbench-status__map-info">比例尺 <span class="workbench-status__mono">—</span></span>
        <span class="workbench-status__item">坐标系 <span class="workbench-status__mono">{{ selectedDem?.crs ?? "EPSG:4326" }}</span></span>
        <span class="workbench-status__grow"></span>
        <span class="workbench-status__item">当前 DEM：{{ selectedDem?.filename ?? "未选择" }}</span>
        <span class="workbench-status__live" :data-connected="!taskManager.connectionInterrupted.value">
          {{ taskManager.connectionInterrupted.value ? "任务轮询中断" : "任务轮询正常" }}
        </span>
      </div>
    </template>
  </GisWorkbenchShell>
  <ModelRunDialog v-if="configuredModelId" :open="runDialogOpen" :model-id="configuredModelId" :request="workspace.currentDraft.value.request" :inputs="workspace.inputSelectionsFor(configuredModelId)" :slots="activeDefinition.inputSlots" :assets="demManager.dems.value" :submitting="submitting" @update:open="runDialogOpen = $event" @update:request="updateDraft" @update:inputs="updateRunInputs" @activate-map-tool="activateMapTool" @submit="submitModelRun" />

  <!-- legacy shell retained below during migration -->
  <!--
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
        <MultiRadarPanel
          v-if="workspace.selectedModel.value === 'radar'"
          :dem-id="demManager.selectedDem.value ?? ''"
          :detailed-station-ids="multiRadarDetailStationIds"
          @show-aggregate="showMultiRadarAggregate"
          @show-detail="showMultiRadarDetail"
          @hide-detail="hideMultiRadarDetail"
          @focus-station="focusMultiRadarStation"
          @error="showError"
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
            :radar-platform-glb-state="mapWorkspace.sceneGlbStateFor(selectedTaskContext.task.task_id, 'radar_platform_glb')"
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
  -->
</template>

<script setup lang="ts">
import type mapboxgl from "mapbox-gl";
import { ElMessage } from "element-plus";
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, shallowRef, toRaw, watch } from "vue";

import GisWorkbenchShell from "./components/workbench/GisWorkbenchShell.vue";
import WorkbenchDataPane from "./components/workbench/WorkbenchDataPane.vue";
import WorkbenchDock, { type RadarControlKind, type RadarControlLayer, type RadarHeightOption, type WorkbenchSceneEntry } from "./components/workbench/WorkbenchDock.vue";
import ModelRunDialog, { type ModelRunSubmission } from "./components/workbench/ModelRunDialog.vue";
import WorkbenchTaskCenter from "./components/workbench/WorkbenchTaskCenter.vue";
import WorkbenchTopbar from "./components/workbench/WorkbenchTopbar.vue";
import MapPickBar from "./components/map/MapPickBar.vue";
import MapWorkspace from "./components/map/MapWorkspace.vue";
import { useDemManager } from "./composables/useDemManager";
import { useMapWorkspace, type SceneGlbKind } from "./composables/useMapWorkspace";
import { useModelWorkspace, type ActiveDraft } from "./composables/useModelWorkspace";
import { useTaskManager } from "./composables/useTaskManager";
import { buildWorkbenchTaskRows } from "./workbench/taskPresentation";
import { useWorkbenchPresentation } from "./workbench/useWorkbenchPresentation";
import { shouldShowRadarPreview } from "./workbench/radarPreviewPolicy";
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
import type { BaseModelRequest, OutputFile, OutputLayerDefinition, TaskSummary } from "./models/shared";
import { applySpatialDraftToRequest, spatialDraftFromRequest } from "./models/spatialAdapter";
import { useRadarAnalysis } from "./models/radar/useRadarAnalysis";
import { createHeightLayerLoader } from "./models/radar/heightLayerLoader";
import { getCoverageTask, type CoverageTaskStatus } from "./api/radar";
import { createMultiRadarTask, getMultiRadarTask, listMultiRadarTasks } from "./api/multiRadar";
import type { MultiRadarPresentationMode, MultiRadarStationInput, MultiRadarTask } from "./models/multiRadar/types";
import { createFusionSceneTask } from "./models/multiRadar/fusionScene";
import {
  cooperativeStationSceneTaskIds,
  createCooperativeIntersectionTask
} from "./models/multiRadar/cooperativeScene";
import { resolveAssetUrl } from "./api/http";
import { createMultiRadarLayerAdapter } from "./map/multiRadarLayerAdapter";

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
const demManager = useDemManager();
const taskManager = useTaskManager({ pollIntervalMs: 1000 });
const presentation = useWorkbenchPresentation(taskManager.selectedTaskKey);
const modelSearch = ref("");
const radarAnalysis = useRadarAnalysis();
const mapWorkspace = useMapWorkspace(
  getModelDefinition(workspace.selectedModel.value).spatialInput,
  spatialDraftFromRequest(workspace.selectedModel.value, toRaw(workspace.currentDraft.value.request))
);
const map = shallowRef<mapboxgl.Map | null>(null);
const historyOpen = ref(false);
const submitting = ref(false);
const mapEditing = ref(false);
const profilePicking = ref(false);
const mapEditTarget = ref<MapEditTarget>("auto");
const runDialogOpen = ref(false);
const configuredModelId = ref<ModelId | null>(null);
const renderedTaskLayers = new Map<string, string>();
const renderedHeightLayers = new Map<string, string>();
const radarLayerErrors = ref<string[]>([]);
const heightOptions = ref<RadarHeightOption[]>([]);
const selectedHeightM = ref<number | null>(null);
const activeHeightData = shallowRef<HeightLayerData[]>([]);
const activeMultiRadarTask = shallowRef<MultiRadarTask | null>(null);
const multiRadarTasks = ref<MultiRadarTask[]>([]);
const multiRadarDetailTasks = new Map<string, CoverageTaskStatus>();
const multiRadarDetailStationIds = ref<string[]>([]);
const cooperativeStationTasks = new Map<string, CoverageTaskStatus>();
const multiRadarAdapter = createMultiRadarLayerAdapter({
  removeDetail(stationId) {
    const detail = multiRadarDetailTasks.get(stationId);
    if (detail && map.value) mapWorkspace.removeSceneGlb(map.value, detail.task_id);
    multiRadarDetailTasks.delete(stationId);
    multiRadarDetailStationIds.value = multiRadarDetailStationIds.value.filter((id) => id !== stationId);
  }
});
const heightLayerLoader = createHeightLayerLoader(fetchJson);
let heightRenderToken = 0;
let lastRadarTaskId: string | null = null;
let multiRadarPollTimer: number | null = null;
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
const workbenchTaskRows = computed(() => buildWorkbenchTaskRows(historyTasks.value as never));
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
const workbenchSceneEntries = computed<WorkbenchSceneEntry[]>(() => {
  const context = selectedTaskContext.value;
  if (!context || context.task.status !== "finished") return [];
  return mapWorkspace.outputFiles.value
    .filter((file) => file.kind === "scene_glb" || file.kind === "radar_platform_glb")
    .map((file) => {
      const kind = file.kind as SceneGlbKind;
      const state = mapWorkspace.sceneGlbStateFor(context.task.task_id, kind);
      return state ? { kind, file, state } : null;
    })
    .filter((entry): entry is WorkbenchSceneEntry => entry !== null);
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
    loadMultiRadarTasks(),
    ...MODEL_IDS.map((modelId) => taskManager.refreshModel(modelId))
  ]);
  if (results.every(({ status }) => status === "rejected")) {
    ElMessage.error("Unable to load workspace data.");
  }
});

onBeforeUnmount(() => {
  stopMultiRadarPolling();
  radarAnalysis.dispose();
  radarLayers.dispose();
  if (map.value) {
    mapWorkspace.removeAllSceneGlbs(map.value);
    removeProfileLayer(map.value);
    removeFusionLayers(map.value);
    removeRadarMarker(map.value);
    if (import.meta.env.DEV) {
      const devWindow = window as Window & { __PYGEOMODEL_MAP__?: mapboxgl.Map };
      if (devWindow.__PYGEOMODEL_MAP__ === map.value) {
        delete devWindow.__PYGEOMODEL_MAP__;
      }
    }
  }
  clearTaskLayers();
  taskManager.dispose();
  mapWorkspace.clearTaskOutputs();
  if (map.value) multiRadarAdapter.clear(map.value);
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
    stopMultiRadarPolling();
    activeMultiRadarTask.value = null;
    if (map.value) multiRadarAdapter.clear(map.value);
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

function selectWorkbenchModel(modelId: ModelId) {
  presentation.selectModel();
  selectModel(modelId);
  configuredModelId.value = modelId;
  runDialogOpen.value = true;
}

function selectWorkbenchTask(modelId: ModelId, taskId: string) {
  taskManager.select(modelId, taskId);
  presentation.selectTask();
}

async function selectMultiRadarTask(taskId: string) {
  try {
    const task = await getMultiRadarTask(taskId);
    upsertMultiRadarTask(task);
    activeMultiRadarTask.value = task;
    demManager.select(task.dem_id);
    if (task.status === "finished" || task.status === "partial") await nextTick(() => showMultiRadarAggregate(task));
  } catch (error) {
    showError(error);
  }
}

async function showMultiRadarAggregate(task: MultiRadarTask) {
  const instance = map.value;
  const outputs = task.outputs;
  if (!instance || !outputs?.visible_union_geojson || !outputs.overlap_geojson || !outputs.blind_geojson
    || !outputs.coverage_count_geojson || !outputs.stations_geojson) return;
  try {
    const urls = [
      outputs.visible_union_geojson, outputs.overlap_geojson, outputs.blind_geojson,
      outputs.coverage_count_geojson, outputs.stations_geojson
    ].map((url) => resolveAssetUrl(url));
    if (urls.some((url) => !url)) return;
    const [visible, overlap, blind, coverageCount, stations] = await Promise.all(
      urls.map((url) => fetchJson<GeoJSON.GeoJSON>(url!))
    );
    multiRadarAdapter.showAggregate(instance, { visible, overlap, blind, coverageCount, stations });
    activeMultiRadarTask.value = task;
    if (task.request?.presentation_mode === "cooperative_3d") {
      await showMultiRadarCooperativeScene(task);
    } else {
      await showMultiRadarFusion(task);
    }
  } catch (error) {
    showError(error);
  }
}

async function showMultiRadarDetail(stationId: string, detail: CoverageTaskStatus | null) {
  if (activeMultiRadarTask.value?.request?.presentation_mode === "cooperative_3d") {
    const finished = cooperativeStationTasks.get(stationId);
    const instance = map.value;
    const demId = demManager.selectedDem.value;
    if (!finished || !instance || !demId) return;
    await mapWorkspace.setSceneGlbVisibility(instance, demId, "radar", finished as never, true, "scene_glb");
    await mapWorkspace.setSceneGlbVisibility(instance, demId, "radar", finished as never, true, "radar_platform_glb");
    if (!multiRadarDetailStationIds.value.includes(stationId)) {
      multiRadarDetailStationIds.value = [...multiRadarDetailStationIds.value, stationId];
    }
    mapWorkspace.focusSceneGlb(instance, finished.task_id, "scene_glb");
    return;
  }
  if (!detail) return;
  multiRadarAdapter.selectStationDetail(stationId);
  multiRadarDetailStationIds.value = multiRadarAdapter.selectedStationIds();
  try {
    const finished = await waitForMultiRadarDetail(detail.task_id);
    const instance = map.value;
    const demId = demManager.selectedDem.value;
    if (!instance || !demId || finished.status !== "finished") return;
    multiRadarDetailTasks.set(stationId, finished);
    await mapWorkspace.setSceneGlbVisibility(instance, demId, "radar", finished as never, true, "scene_glb");
    await mapWorkspace.setSceneGlbVisibility(instance, demId, "radar", finished as never, true, "radar_platform_glb");
    mapWorkspace.focusSceneGlb(instance, finished.task_id, "scene_glb");
  } catch (error) {
    showError(error);
  }
}

async function showMultiRadarFusion(task: MultiRadarTask) {
  const instance = map.value;
  const demId = demManager.selectedDem.value;
  const url = task.outputs?.fusion_scene_glb;
  if (!instance || !demId || !url) return;
  const fusionTask = createFusionSceneTask(task.task_id, task.dem_id, url);
  await mapWorkspace.setSceneGlbVisibility(instance, demId, "radar", fusionTask as never, true, "scene_glb");
  mapWorkspace.focusSceneGlb(instance, fusionTask.task_id, "scene_glb");
}

async function showMultiRadarCooperativeScene(task: MultiRadarTask) {
  const instance = map.value;
  const demId = demManager.selectedDem.value;
  if (!instance || !demId) return;
  cooperativeStationTasks.clear();
  const sceneTaskIds = cooperativeStationSceneTaskIds(task);
  const stationBySceneTaskId = new Map(task.stations.map((station) => [station.scene_task_id, station.radar_id]));
  const children = await Promise.allSettled(sceneTaskIds.map((taskId) => getCoverageTask(taskId)));
  const finished = children.flatMap((result) => (
    result.status === "fulfilled" && result.value.status === "finished" ? [result.value] : []
  ));
  for (const stationTask of finished) {
    const stationId = stationBySceneTaskId.get(stationTask.task_id);
    if (stationId) cooperativeStationTasks.set(stationId, stationTask);
  }
  const stationLoads = finished.flatMap((stationTask) => [
    mapWorkspace.setSceneGlbVisibility(instance, demId, "radar", stationTask as never, true, "scene_glb"),
    mapWorkspace.setSceneGlbVisibility(instance, demId, "radar", stationTask as never, true, "radar_platform_glb")
  ]);
  await Promise.allSettled(stationLoads);
  const intersectionUrl = task.outputs?.cooperative_intersection_glb;
  const intersectionTask = intersectionUrl
    ? createCooperativeIntersectionTask(task.task_id, task.dem_id, intersectionUrl)
    : null;
  if (intersectionTask) {
    await mapWorkspace.setSceneGlbVisibility(instance, demId, "radar", intersectionTask as never, true, "scene_glb");
  }
  multiRadarDetailStationIds.value = [...cooperativeStationTasks.keys()];
  mapWorkspace.focusSceneGlbs(instance, [
    ...finished.map((stationTask) => ({ taskId: stationTask.task_id })),
    ...(intersectionTask ? [{ taskId: intersectionTask.task_id }] : [])
  ]);
}

function hideMultiRadarDetail(stationId: string) {
  const cooperativeTask = cooperativeStationTasks.get(stationId);
  if (cooperativeTask && map.value) {
    mapWorkspace.removeSceneGlb(map.value, cooperativeTask.task_id);
    multiRadarDetailStationIds.value = multiRadarDetailStationIds.value.filter((id) => id !== stationId);
    return;
  }
  multiRadarAdapter.removeStationDetail(stationId);
}

function focusMultiRadarStation(stationId: string) {
  const station = activeMultiRadarTask.value?.request?.radars.find((item) => item.radar_id === stationId);
  if (map.value && station) map.value.flyTo({ center: [station.radar.lon, station.radar.lat], zoom: 12, duration: 700 });
}

async function waitForMultiRadarDetail(taskId: string): Promise<CoverageTaskStatus> {
  for (let attempt = 0; attempt < 180; attempt += 1) {
    const task = await getCoverageTask(taskId);
    if (["finished", "failed"].includes(task.status)) return task;
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
  }
  throw new Error("Radar detail generation timed out.");
}

function updateDraft(request: BaseModelRequest) {
  workspace.currentDraft.value = {
    modelId: workspace.selectedModel.value,
    request
  } as ActiveDraft;
  syncSpatialDraft();
}

function updateRunInputs(inputs: Record<string, string[]>) {
  const modelId = configuredModelId.value;
  if (!modelId) return;
  workspace.updateInputSelections(modelId, inputs);
  const terrainId = inputs.terrain?.[0] ?? null;
  if (terrainId) demManager.select(terrainId);
}

function submitModelRun(submission: ModelRunSubmission) {
  const { inputs } = submission;
  updateRunInputs(inputs);
  runDialogOpen.value = false;
  if (submission.multiRadar) {
    const demId = inputs.terrain?.[0] ?? "";
    void submitMultiRadarRun(demId, submission.multiRadar.stations, submission.multiRadar.presentationMode);
    return;
  }
  updateDraft(submission.request);
  void submitTask(submission.request);
}

async function submitMultiRadarRun(
  demId: string,
  stations: MultiRadarStationInput[],
  presentationMode: MultiRadarPresentationMode
) {
  submitting.value = true;
  try {
    const task = await createMultiRadarTask({ dem_id: demId, radars: stations, presentation_mode: presentationMode });
    activeMultiRadarTask.value = task;
    upsertMultiRadarTask(task);
    startMultiRadarPolling(task.task_id);
  } catch (error) {
    showError(error);
  } finally {
    submitting.value = false;
  }
}

function startMultiRadarPolling(taskId: string) {
  stopMultiRadarPolling();
  multiRadarPollTimer = window.setInterval(() => {
    void refreshMultiRadarTask(taskId);
  }, 1000);
}

function stopMultiRadarPolling() {
  if (multiRadarPollTimer !== null) window.clearInterval(multiRadarPollTimer);
  multiRadarPollTimer = null;
}

async function refreshMultiRadarTask(taskId: string) {
  try {
    const task = await getMultiRadarTask(taskId);
    activeMultiRadarTask.value = task;
    upsertMultiRadarTask(task);
    if (!["finished", "partial", "failed"].includes(task.status)) return;
    stopMultiRadarPolling();
    if (task.status === "finished" || task.status === "partial") await showMultiRadarAggregate(task);
  } catch (error) {
    stopMultiRadarPolling();
    showError(error);
  }
}

async function loadMultiRadarTasks() {
  const tasks = await listMultiRadarTasks();
  multiRadarTasks.value = tasks;
}

function upsertMultiRadarTask(task: MultiRadarTask) {
  const index = multiRadarTasks.value.findIndex(({ task_id }) => task_id === task.task_id);
  if (index === -1) multiRadarTasks.value = [task, ...multiRadarTasks.value];
  else multiRadarTasks.value.splice(index, 1, task);
  multiRadarTasks.value.sort((left, right) => Date.parse(right.updated_at ?? right.created_at ?? "") - Date.parse(left.updated_at ?? left.created_at ?? ""));
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
  runDialogOpen.value = false;
}

function finishMapPicking() {
  mapEditing.value = false;
  if (configuredModelId.value) runDialogOpen.value = true;
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
  if (action.type !== "undo" && action.type !== "clear" && mapEditTarget.value !== "route") finishMapPicking();
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

function setMap(instance: mapboxgl.Map) {
  if (map.value && map.value !== instance) {
    mapWorkspace.resetSceneGlbStates();
  }
  map.value = instance;
  if (import.meta.env.DEV) {
    (window as Window & { __PYGEOMODEL_MAP__?: mapboxgl.Map })
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

async function setSceneGlbVisibility(
  kindOrVisible: SceneGlbKind | boolean,
  nextVisible?: boolean
) {
  const instance = map.value;
  const context = selectedTaskContext.value;
  const selectedDemId = demManager.selectedDem.value;
  if (!instance || !context || !selectedDemId) return;
  const kind = typeof kindOrVisible === "boolean" ? "scene_glb" : kindOrVisible;
  const visible = typeof kindOrVisible === "boolean" ? kindOrVisible : Boolean(nextVisible);
  await mapWorkspace.setSceneGlbVisibility(
    instance,
    selectedDemId,
    context.modelId,
    context.task as never,
    visible,
    kind
  );
}

function focusSceneGlb(kind: SceneGlbKind = "scene_glb") {
  const instance = map.value;
  const context = selectedTaskContext.value;
  if (instance && context) {
    mapWorkspace.focusSceneGlb(instance, context.task.task_id, kind);
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
  radarLayers.clear();
  radarLayerErrors.value = [];
  if (map.value) {
    removeRadarMarker(map.value);
    removeRadarVolume(map.value);
  }
  const current = selectedTaskContext.value;
  if (workspace.selectedModel.value !== "radar"
    || current?.modelId !== "radar"
    || current.task.task_id !== radarTask.task_id) return;
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
  if (!shouldShowRadarPreview(selectedTaskContext.value?.modelId === "radar" ? selectedTaskContext.value.task.status : null)) {
    removeRadarMarker(instance);
    removeRadarVolume(instance);
    return;
  }
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

async function handleRadarMapClick(event: mapboxgl.MapMouseEvent) {
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
  instance: mapboxgl.Map,
  id: string,
  data: GeoJSON.GeoJSON,
  definition: OutputLayerDefinition,
  visible: boolean,
  opacity: number,
  registry = renderedTaskLayers
) {
  const sourceId = `${id}-source`;
  const source = instance.getSource(sourceId) as mapboxgl.GeoJSONSource | undefined;
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
  instance: mapboxgl.Map,
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
  if (!areaM2) return "0 km虏";
  return `${(areaM2 / 1_000_000).toFixed(areaM2 >= 10_000_000 ? 1 : 2)} km虏`;
}

function sanitizeId(value: string) {
  return value.replace(/[^a-zA-Z0-9_-]/g, "-");
}

function mapReady(instance: mapboxgl.Map) {
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
