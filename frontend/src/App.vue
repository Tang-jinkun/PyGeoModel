<template>
  <main class="app-shell">
    <ControlPanel
      :model="coverageRequest"
      :dem="dem"
      :dem-list="demList"
      :task-list="taskList"
      :selected-task-id="selectedTaskId"
      :task-list-loading="taskListLoading"
      :loading-task-id="loadingTaskId"
      :restoring-task-id="restoringTaskId"
      :deleting-task-id="deletingTaskId"
      :deleting-dem-id="deletingDemId"
      :busy="busy"
      @upload="handleUpload"
      @select-dem="handleSelectDem"
      @select-task="handleSelectTask"
      @restore-task="handleRestoreTask"
      @delete-task="handleDeleteTask"
      @delete-dem="handleDeleteDem"
      @refresh-tasks="refreshTaskList"
      @run="handleRun"
    />

    <section class="map-shell">
      <div ref="mapContainer" class="map-container"></div>
      <LayerControlPanel
        :layers="layerControls"
        :height-layers="heightLayerOptions"
        :selected-height-m="selectedHeightLayerM"
        @update-layer="handleLayerControlUpdate"
        @select-height-layer="handleSelectHeightLayer"
        @focus-result="handleFocusResult"
      />
      <ResultPanel :task="task" @restore-request="restoreRequest" />
      <ProfilePanel :profile="profile" :loading="profileLoading" @close="clearProfile" />
      <FusionPanel
        :tasks="taskList"
        :result="fusionResult"
        :loading="fusionLoading"
        @run="handleRunFusion"
        @clear="clearFusion"
      />
    </section>
  </main>
</template>

<script setup lang="ts">
import maplibregl from "maplibre-gl";
import { ElMessage } from "element-plus";
import { onMounted, reactive, ref, shallowRef, watch } from "vue";

import {
  createCoverageTask,
  createFusionAnalysis,
  deleteDem,
  deleteCoverageTask,
  defaultCoverageRequest,
  demTerrainUrlTemplate,
  demTileUrlTemplate,
  getCoverageTask,
  getCoverageProfile,
  listCoverageTasks,
  listDems,
  normalizeCoverageRequest,
  resolveAssetUrl,
  uploadDem,
  type CoverageProfileResult,
  type CoverageRequest,
  type FusionResult,
  type CoverageTaskSummary,
  type CoverageTaskStatus,
  type DemMetadata
} from "./api/client";
import ControlPanel from "./components/ControlPanel.vue";
import FusionPanel from "./components/FusionPanel.vue";
import LayerControlPanel from "./components/LayerControlPanel.vue";
import ProfilePanel from "./components/ProfilePanel.vue";
import ResultPanel from "./components/ResultPanel.vue";
import {
  addOrUpdateProfileLayer,
  addOrUpdateGeoJsonDataLayer,
  addOrUpdateGeoJsonLayer,
  addOrUpdateDemRasterLayer,
  addOrUpdateDemTerrain,
  addRadarMarker,
  getGeoJsonBounds,
  moveRadarMarkerToTop,
  removeDemRasterLayer,
  removeDemTerrain,
  removeProfileLayer,
  removeFusionLayers,
  removeResultLayers,
  setFusionLayerOpacity,
  setFusionLayerVisibility,
  setResultLayerOpacity,
  setResultLayerVisibility,
  type FusionLayerKey,
  type ResultLayerKey
} from "./map/mapLayers";
import { addOrUpdateRadarVolume, removeRadarVolume } from "./map/radarVolumeLayer";
import {
  canPreviewBeam,
  clipProfileFromBounds,
  resolveBeamRenderRange
} from "./map/beamClipProfile";
import {
  addOrUpdateClippedVolumeLayer,
  loadClippedVolumeData,
  removeClippedVolumeLayer,
  type ClippedVolumeCell
} from "./map/clippedVolumeLayer";
import { addOrUpdateVoxelLayer, loadVoxelData, removeVoxelLayer, type VoxelPoint } from "./map/voxelLayer";

type LayerKey = ResultLayerKey | FusionLayerKey | "radarVolume" | "radarRequestBoundary" | "clippedVolume" | "voxel" | "heightLayer";

interface ResultLayerControl {
  key: LayerKey;
  label: string;
  description: string;
  color: string;
  visible: boolean;
  opacity: number;
  defaultOpacity: number;
  available: boolean;
}

interface HeightLayerOption {
  heightM: number;
  label: string;
  visibleUrl: string;
  blockedUrl: string | null;
  visibleAreaM2: number;
  blockedAreaM2: number;
}

interface HeightLayerManifest {
  height_layers?: Array<{
    height_m?: number;
    filename?: string;
    visible_filename?: string;
    blocked_filename?: string;
    visible_area_m2?: number;
    blocked_area_m2?: number;
  }>;
}

const mapContainer = ref<HTMLDivElement | null>(null);
const map = shallowRef<maplibregl.Map | null>(null);
const dem = ref<DemMetadata | null>(null);
const demList = ref<DemMetadata[]>([]);
const task = ref<CoverageTaskStatus | null>(null);
const taskList = ref<CoverageTaskSummary[]>([]);
const selectedTaskId = ref<string | null>(null);
const taskListLoading = ref(false);
const loadingTaskId = ref<string | null>(null);
const restoringTaskId = ref<string | null>(null);
const deletingTaskId = ref<string | null>(null);
const deletingDemId = ref<string | null>(null);
let pollToken = 0;
let viewToken = 0;
let taskListRequestToken = 0;
const busy = ref(false);
let focusToken = 0;
const voxelPoints = shallowRef<VoxelPoint[]>([]);
const voxelTaskId = ref<string | null>(null);
const clippedVolumeCells = shallowRef<ClippedVolumeCell[]>([]);
const clippedVolumeManifest = shallowRef<{ cell_size_m: number; cell_count: number; fields: string[]; bytes_per_cell: number } | null>(null);
const radarVolumeRequest = shallowRef<CoverageRequest | null>(null);
const radarVolumeTaskId = ref<string | null>(null);
const heightLayerOptions = ref<HeightLayerOption[]>([]);
const selectedHeightLayerM = ref<number | null>(null);
const profile = shallowRef<CoverageProfileResult | null>(null);
const profileLoading = ref(false);
let profileRequestToken = 0;
const fusionResult = shallowRef<FusionResult | null>(null);
const fusionLoading = ref(false);
let fusionRequestToken = 0;
const layerControls = reactive<ResultLayerControl[]>([
  {
    key: "radarVolume",
    label: "可分析理论波束",
    description: "限制在 DEM 有效分析域内",
    color: "#34d399",
    visible: true,
    opacity: 0.62,
    defaultOpacity: 0.62,
    available: false
  },
  {
    key: "radarRequestBoundary",
    label: "完整请求边界",
    description: "DEM 裁剪前的理论波束参考线",
    color: "#94a3b8",
    visible: false,
    opacity: 0.45,
    defaultOpacity: 0.45,
    available: false
  },
  {
    key: "clippedVolume",
    label: "地形裁切波束",
    description: "被地形遮挡后的三维波束体",
    color: "#ef4444",
    visible: true,
    opacity: 0.66,
    defaultOpacity: 0.66,
    available: false
  },
  {
    key: "visible",
    label: "可探测区",
    description: "地形视线可达区域",
    color: "#16a34a",
    visible: true,
    opacity: 0.38,
    defaultOpacity: 0.38,
    available: false
  },
  {
    key: "blocked",
    label: "遮挡区",
    description: "地形遮挡区域",
    color: "#dc2626",
    visible: true,
    opacity: 0.28,
    defaultOpacity: 0.28,
    available: false
  },
  {
    key: "range",
    label: "可分析理论范围",
    description: "理论波束与 DEM 分析域的交集",
    color: "#2563eb",
    visible: false,
    opacity: 0.08,
    defaultOpacity: 0.08,
    available: false
  },
  {
    key: "heightLayer",
    label: "高度层",
    description: "不同目标高度的可见范围",
    color: "#f59e0b",
    visible: true,
    opacity: 0.32,
    defaultOpacity: 0.32,
    available: false
  },
  {
    key: "voxel",
    label: "体素点云",
    description: "按最低可见高度生成的 3D 点云",
    color: "#22d3ee",
    visible: false,
    opacity: 0.8,
    defaultOpacity: 0.8,
    available: false
  },
  {
    key: "fusionVisible",
    label: "融合总覆盖",
    description: "多任务可探测并集",
    color: "#059669",
    visible: true,
    opacity: 0.22,
    defaultOpacity: 0.22,
    available: false
  },
  {
    key: "fusionOverlap",
    label: "融合重叠",
    description: "多任务冗余覆盖",
    color: "#7c3aed",
    visible: true,
    opacity: 0.34,
    defaultOpacity: 0.34,
    available: false
  },
  {
    key: "fusionBlind",
    label: "融合盲区",
    description: "理论范围内未覆盖",
    color: "#ef4444",
    visible: true,
    opacity: 0.3,
    defaultOpacity: 0.3,
    available: false
  }
]);

const coverageRequest = reactive<CoverageRequest>(defaultCoverageRequest());

onMounted(() => {
  void refreshDemList();
  void refreshTaskList();

  if (!mapContainer.value) {
    return;
  }

  map.value = new maplibregl.Map({
    container: mapContainer.value,
    style: "https://demotiles.maplibre.org/style.json",
    center: [coverageRequest.radar.lon, coverageRequest.radar.lat],
    zoom: 8,
    pitch: 55,
    bearing: -20
  });

  map.value.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
  map.value.on("click", handleMapClick);
  map.value.on("load", () => {
    if (dem.value) {
      applyDemMapLayers(dem.value);
    }
    syncRadarVolumeLayer();
  });
});

watch(
  coverageRequest,
  () => {
    radarVolumeRequest.value = coverageRequest;
    radarVolumeTaskId.value = null;
    updateBeamPreviewAvailability();
    syncRadarVolumeLayer(coverageRequest);
  },
  { deep: true }
);

async function handleUpload(file: File) {
  busy.value = true;
  try {
    dem.value = await uploadDem(file);
    coverageRequest.dem_id = dem.value.dem_id;
    await refreshDemList();
    if (dem.value.bounds.length === 4) {
      const [minLon, minLat, maxLon, maxLat] = dem.value.bounds;
      coverageRequest.radar.lon = Number(((minLon + maxLon) / 2).toFixed(6));
      coverageRequest.radar.lat = Number(((minLat + maxLat) / 2).toFixed(6));
      applyDemMapLayers(dem.value);
      map.value?.flyTo({ center: [coverageRequest.radar.lon, coverageRequest.radar.lat], zoom: 9 });
    }
    ElMessage.success("DEM 上传成功");
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "DEM 上传失败");
  } finally {
    busy.value = false;
  }
}

async function refreshDemList() {
  try {
    demList.value = await listDems();
  } catch {
    demList.value = [];
  }
}

async function refreshTaskList() {
  const token = ++taskListRequestToken;
  taskListLoading.value = true;
  try {
    const tasks = await listCoverageTasks();
    if (token === taskListRequestToken) {
      taskList.value = tasks;
    }
  } catch {
    if (token === taskListRequestToken) {
      taskList.value = [];
    }
  } finally {
    if (token === taskListRequestToken) {
      taskListLoading.value = false;
    }
  }
}

function handleSelectDem(demId: string) {
  const selected = demList.value.find((item) => item.dem_id === demId);
  if (!selected) {
    return;
  }
  dem.value = selected;
  coverageRequest.dem_id = selected.dem_id;
  if (selected.bounds.length === 4) {
    const [minLon, minLat, maxLon, maxLat] = selected.bounds;
    coverageRequest.radar.lon = Number(((minLon + maxLon) / 2).toFixed(6));
    coverageRequest.radar.lat = Number(((minLat + maxLat) / 2).toFixed(6));
    applyDemMapLayers(selected);
    map.value?.flyTo({ center: [coverageRequest.radar.lon, coverageRequest.radar.lat], zoom: 9 });
  }
}

function applyDemMapLayers(selected: DemMetadata) {
  if (!map.value || selected.bounds.length !== 4) {
    return;
  }
  addOrUpdateDemRasterLayer(map.value, demTileUrlTemplate(selected.dem_id), selected.bounds);
  addOrUpdateDemTerrain(map.value, demTerrainUrlTemplate(selected.dem_id), selected.bounds);
}

async function handleMapClick(event: maplibregl.MapMouseEvent) {
  const currentTask = task.value;
  if (!map.value || !currentTask || currentTask.status !== "finished" || !currentTask.request) {
    return;
  }

  const token = ++profileRequestToken;
  profileLoading.value = true;
  try {
    const result = await getCoverageProfile(currentTask.task_id, event.lngLat.lng, event.lngLat.lat);
    if (token !== profileRequestToken || task.value?.task_id !== currentTask.task_id) {
      return;
    }
    profile.value = result;
    addOrUpdateProfileLayer(
      map.value,
      [currentTask.request.radar.lon, currentTask.request.radar.lat],
      [result.target_lon, result.target_lat],
      result.obstruction_lon != null && result.obstruction_lat != null
        ? [result.obstruction_lon, result.obstruction_lat]
        : null
    );
    moveRadarMarkerToTop(map.value);
  } catch (error) {
    if (token === profileRequestToken) {
      ElMessage.error(error instanceof Error ? error.message : "剖面分析失败");
      clearProfile();
    }
  } finally {
    if (token === profileRequestToken) {
      profileLoading.value = false;
    }
  }
}

function clearProfile() {
  profileRequestToken++;
  profile.value = null;
  profileLoading.value = false;
  if (map.value) {
    removeProfileLayer(map.value);
  }
}

async function handleRunFusion(taskIds: string[]) {
  if (!map.value || taskIds.length < 2) {
    ElMessage.warning("请选择至少两个已完成任务");
    return;
  }
  const token = ++fusionRequestToken;
  fusionLoading.value = true;
  try {
    const result = await createFusionAnalysis(taskIds);
    if (token !== fusionRequestToken) {
      return;
    }
    fusionResult.value = result;
    updateFusionLayerAvailability(true);
    drawFusionLayers(result);
    ElMessage.success("融合分析完成");
  } catch (error) {
    if (token === fusionRequestToken) {
      ElMessage.error(error instanceof Error ? error.message : "融合分析失败");
    }
  } finally {
    if (token === fusionRequestToken) {
      fusionLoading.value = false;
    }
  }
}

function drawFusionLayers(result: FusionResult) {
  if (!map.value) {
    return;
  }
  removeFusionLayers(map.value);
  addOrUpdateGeoJsonDataLayer(
    map.value,
    "fusion-visible-layer",
    result.visible_union_geojson,
    { "fill-color": "#059669", "fill-opacity": getLayerControl("fusionVisible")?.opacity ?? 0.22 },
    { "line-color": "#047857", "line-width": 2, "line-opacity": Math.max(getLayerControl("fusionVisible")?.opacity ?? 0.22, 0.35) }
  );
  addOrUpdateGeoJsonDataLayer(
    map.value,
    "fusion-overlap-layer",
    result.overlap_geojson,
    { "fill-color": "#7c3aed", "fill-opacity": getLayerControl("fusionOverlap")?.opacity ?? 0.34 },
    { "line-color": "#6d28d9", "line-width": 2, "line-opacity": Math.max(getLayerControl("fusionOverlap")?.opacity ?? 0.34, 0.35) }
  );
  addOrUpdateGeoJsonDataLayer(
    map.value,
    "fusion-blind-layer",
    result.blind_geojson,
    { "fill-color": "#ef4444", "fill-opacity": getLayerControl("fusionBlind")?.opacity ?? 0.3 },
    { "line-color": "#b91c1c", "line-width": 2, "line-opacity": Math.max(getLayerControl("fusionBlind")?.opacity ?? 0.3, 0.35) }
  );
  applyFusionLayerControls();
  moveRadarMarkerToTop(map.value);
}

function clearFusion() {
  fusionRequestToken++;
  fusionResult.value = null;
  fusionLoading.value = false;
  if (map.value) {
    removeFusionLayers(map.value);
  }
  updateFusionLayerAvailability(false);
}

async function handleRun() {
  if (!dem.value) {
    ElMessage.warning("请先上传 DEM");
    return;
  }

  busy.value = true;
  const token = ++pollToken;
  viewToken++;
  try {
    if (!map.value) {
      throw new Error("地图尚未初始化完成");
    }
    clearProfile();
    clearFusion();
    removeResultLayers(map.value);
    clearLayerAvailability();
    radarVolumeRequest.value = coverageRequest;
    radarVolumeTaskId.value = null;
    addRadarMarker(map.value, coverageRequest.radar.lon, coverageRequest.radar.lat);
    syncRadarVolumeLayer();
    const created = await createCoverageTask(coverageRequest);
    if (token !== pollToken) {
      return;
    }
    task.value = created;
    selectedTaskId.value = created.task_id;
    await refreshTaskList();
    await pollTask(created.task_id, token);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "计算失败");
  } finally {
    busy.value = false;
  }
}

async function pollTask(taskId: string, token: number) {
  for (;;) {
    await new Promise((resolve) => window.setTimeout(resolve, 1500));
    if (token !== pollToken) {
      return;
    }
    const latest = await getCoverageTask(taskId);
    if (token !== pollToken) {
      return;
    }
    task.value = latest;
    void refreshTaskList();
    if (latest.status === "finished") {
      loadOutputs(latest);
      ElMessage.success("计算完成");
      return;
    }
    if (latest.status === "failed") {
      clearProfile();
      clearFusion();
      if (map.value) {
        removeResultLayers(map.value);
        removeRadarVolume(map.value);
        removeClippedVolumeLayer(map.value);
        removeVoxelLayer(map.value);
        removeDemRasterLayer(map.value);
        removeDemTerrain(map.value);
      }
      clearLayerAvailability();
      throw new Error(latest.message || "计算失败");
    }
  }
}

async function handleSelectTask(taskId: string) {
  pollToken++;
  const token = ++viewToken;
  selectedTaskId.value = taskId;
  loadingTaskId.value = taskId;
  try {
    const selected = await getCoverageTask(taskId);
    if (token !== viewToken || selectedTaskId.value !== taskId) {
      return;
    }
    task.value = selected;
    if (selected.status === "finished") {
      loadOutputs(selected);
      ElMessage.success("历史任务已加载");
      return;
    }
    clearProfile();
    clearFusion();
    if (map.value) {
      removeResultLayers(map.value);
      removeRadarVolume(map.value);
      removeClippedVolumeLayer(map.value);
      removeVoxelLayer(map.value);
    }
    clearLayerAvailability();
    ElMessage.info(`任务状态：${selected.status}`);
  } catch (error) {
    if (token === viewToken) {
      ElMessage.error(error instanceof Error ? error.message : "加载历史任务失败");
    }
  } finally {
    if (loadingTaskId.value === taskId) {
      loadingTaskId.value = null;
    }
  }
}

async function handleRestoreTask(taskId: string) {
  pollToken++;
  const token = ++viewToken;
  selectedTaskId.value = taskId;
  restoringTaskId.value = taskId;
  try {
    const selected = await getCoverageTask(taskId);
    if (token !== viewToken || selectedTaskId.value !== taskId) {
      return;
    }
    if (!selected.request) {
      ElMessage.warning("该历史任务没有可恢复的参数");
      return;
    }
    task.value = selected;
    restoreRequest(selected.request);
  } catch (error) {
    if (token === viewToken) {
      ElMessage.error(error instanceof Error ? error.message : "恢复历史参数失败");
    }
  } finally {
    if (restoringTaskId.value === taskId) {
      restoringTaskId.value = null;
    }
  }
}

async function handleDeleteTask(taskId: string) {
  deletingTaskId.value = taskId;
  try {
    await deleteCoverageTask(taskId);
    clearFusion();
    if (selectedTaskId.value === taskId) {
      pollToken++;
      viewToken++;
      selectedTaskId.value = null;
      task.value = null;
      clearProfile();
      clearFusion();
      if (map.value) {
        removeResultLayers(map.value);
        removeRadarVolume(map.value);
        removeClippedVolumeLayer(map.value);
        removeVoxelLayer(map.value);
      }
      clearLayerAvailability();
    }
    await refreshTaskList();
    ElMessage.success("历史任务已删除");
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "删除任务失败");
  } finally {
    deletingTaskId.value = null;
  }
}

async function handleDeleteDem(demId: string) {
  deletingDemId.value = demId;
  try {
    await deleteDem(demId);
    if (coverageRequest.dem_id === demId) {
      pollToken++;
      viewToken++;
      coverageRequest.dem_id = "";
      dem.value = null;
      selectedTaskId.value = null;
      task.value = null;
      clearProfile();
      clearFusion();
      if (map.value) {
        removeResultLayers(map.value);
      }
      clearLayerAvailability();
    }
    await refreshDemList();
    await refreshTaskList();
    ElMessage.success("DEM 已删除");
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "删除 DEM 失败");
  } finally {
    deletingDemId.value = null;
  }
}

function restoreRequest(request: CoverageRequest) {
  const normalized = normalizeCoverageRequest(request, defaultCoverageRequest());
  if (!normalized || !normalized.dem_id) {
    ElMessage.warning("历史参数不完整，无法恢复");
    return;
  }
  const restoredDem = demList.value.find((item) => item.dem_id === normalized.dem_id);
  if (!restoredDem) {
    ElMessage.warning("该任务引用的 DEM 已不存在，无法恢复参数");
    return;
  }
  pollToken++;
  viewToken++;
  applyCoverageRequest(normalized);
  selectedTaskId.value = null;
  task.value = null;
  clearProfile();
  clearFusion();
  clearLayerAvailability();
  radarVolumeRequest.value = normalized;

  dem.value = restoredDem;
  if (map.value) {
    removeResultLayers(map.value);
    addRadarMarker(map.value, normalized.radar.lon, normalized.radar.lat);
    syncRadarVolumeLayer();
    map.value.flyTo({ center: [normalized.radar.lon, normalized.radar.lat], zoom: 9 });
  }
  ElMessage.success("历史参数已恢复到表单");
}

function applyCoverageRequest(request: CoverageRequest) {
  coverageRequest.dem_id = request.dem_id;
  coverageRequest.radar.lon = request.radar.lon;
  coverageRequest.radar.lat = request.radar.lat;
  coverageRequest.radar.height_m = request.radar.height_m;
  coverageRequest.target.height_m = request.target.height_m;
  coverageRequest.coverage.max_range_m = request.coverage.max_range_m;
  coverageRequest.coverage.scan_mode = request.coverage.scan_mode;
  coverageRequest.coverage.azimuth_deg = request.coverage.azimuth_deg;
  coverageRequest.coverage.beam_width_deg = request.coverage.beam_width_deg;
  coverageRequest.advanced.use_curvature = request.advanced.use_curvature;
  coverageRequest.advanced.curvature_coeff = request.advanced.curvature_coeff;
  coverageRequest.advanced.output_simplify_tolerance_m = request.advanced.output_simplify_tolerance_m;
  coverageRequest.advanced.voxel_grid_size = request.advanced.voxel_grid_size;
  coverageRequest.advanced.voxel_vertical_levels = request.advanced.voxel_vertical_levels;
  coverageRequest.advanced.voxel_max_height_m = request.advanced.voxel_max_height_m;
  coverageRequest.advanced.min_elevation_deg = request.advanced.min_elevation_deg;
  coverageRequest.advanced.max_elevation_deg = request.advanced.max_elevation_deg;
  coverageRequest.advanced.vertical_beam_width_deg = request.advanced.vertical_beam_width_deg;
  coverageRequest.advanced.visual_dome_mode = request.advanced.visual_dome_mode;
  coverageRequest.advanced.height_layers_m = [...(request.advanced.height_layers_m ?? [])];
  coverageRequest.reserved_radar_params = { ...(request.reserved_radar_params ?? {}) };
}

function loadOutputs(result: CoverageTaskStatus) {
  if (!map.value) {
    return;
  }
  clearProfile();
  removeResultLayers(map.value);
  removeRadarVolume(map.value);
  removeClippedVolumeLayer(map.value);
  removeVoxelLayer(map.value);
  voxelPoints.value = [];
  voxelTaskId.value = null;
  clippedVolumeCells.value = [];
  clippedVolumeManifest.value = null;
  heightLayerOptions.value = [];
  selectedHeightLayerM.value = null;
  radarVolumeRequest.value = result.request ?? coverageRequest;
  radarVolumeTaskId.value = result.request ? result.task_id : null;

  const visible = resolveOutputUrl(result, "visible_geojson", result.outputs?.visible_geojson);
  const blocked = resolveOutputUrl(result, "blocked_geojson", result.outputs?.blocked_geojson);
  const range = resolveOutputUrl(result, "range_geojson", result.outputs?.range_geojson);
  const clippedCells = resolveOutputUrl(result, "clipped_volume_cells_bin", result.outputs?.clipped_volume_cells_bin);
  const clippedManifest = resolveOutputUrl(
    result,
    "clipped_volume_manifest_json",
    result.outputs?.clipped_volume_manifest_json
  );
  const voxelUrl = resolveOutputUrl(result, "voxel_points_bin", result.outputs?.voxel_points_bin);
  const voxelManifest = resolveOutputUrl(result, "voxel_manifest_json", result.outputs?.voxel_manifest_json);
  if (!range && !blocked && !visible) {
    updateLayerAvailability({
      radarVolume: !!result.request,
      radarRequestBoundary: !!result.request,
      clippedVolume: Boolean(clippedCells && clippedManifest),
      voxel: Boolean(voxelUrl && voxelManifest),
      heightLayer: false
    });
    if (result.request) {
      addRadarMarker(map.value, result.request.radar.lon, result.request.radar.lat, result.request.radar.height_m);
    }
    tuneVolumeLayerDefaults(Boolean(clippedCells && clippedManifest));
    applyAllLayerControls();
    void loadClippedVolumeLayer(result);
    return;
  }

  updateLayerAvailability({
    range: !!range,
    blocked: !!blocked,
    visible: !!visible,
    radarVolume: !!result.request,
    radarRequestBoundary: !!result.request,
    clippedVolume: Boolean(clippedCells && clippedManifest),
    voxel: Boolean(voxelUrl && voxelManifest),
    heightLayer: false
  });
  tuneVolumeLayerDefaults(Boolean(clippedCells && clippedManifest));

  if (result.request) {
    addRadarMarker(map.value, result.request.radar.lon, result.request.radar.lat, result.request.radar.height_m);
  }

  if (range) {
    addOrUpdateGeoJsonLayer(
      map.value,
      "range-layer",
      range,
      { "fill-color": "#2563eb", "fill-opacity": 0.08 },
      { "line-color": "#2563eb", "line-width": 2 }
    );
  }
  if (visible) {
    addOrUpdateGeoJsonLayer(
      map.value,
      "visible-layer",
      visible,
      {
        "fill-color": "#16a34a",
        "fill-opacity": 0.38
      },
      { "line-color": "#16a34a", "line-opacity": 0.38, "line-width": 1 }
    );
  }
  if (blocked) {
    addOrUpdateGeoJsonLayer(
      map.value,
      "blocked-layer",
      blocked,
      {
        "fill-color": "#dc2626",
        "fill-opacity": 0.28
      },
      { "line-color": "#dc2626", "line-opacity": 0.38, "line-width": 1 }
    );
  }
  applyAllLayerControls();
  moveRadarMarkerToTop(map.value);

  void loadHeightLayers(result);
  void loadClippedVolumeLayer(result);
}

async function loadHeightLayers(result: CoverageTaskStatus) {
  if (!map.value) {
    return;
  }
  const manifestUrl = resolveOutputUrl(
    result,
    "height_layers_manifest_json",
    result.outputs?.height_layers_manifest_json
  );
  if (!manifestUrl) {
    return;
  }
  try {
    const response = await fetch(manifestUrl);
    if (!response.ok) {
      throw new Error(`高度层清单读取失败：${response.status}`);
    }
    const manifest = await response.json() as HeightLayerManifest;
    const options = normalizeHeightLayerOptions(manifest, manifestUrl);
    if (!options.length || task.value?.task_id !== result.task_id) {
      return;
    }
    heightLayerOptions.value = options;
    selectedHeightLayerM.value = chooseInitialHeightLayer(options, result.request);
    const control = getLayerControl("heightLayer");
    if (control) {
      control.available = true;
    }
    applyHeightLayerControl();
  } catch (error) {
    console.error("Failed to load height layers:", error);
  }
}

async function loadVoxelLayer(result: CoverageTaskStatus) {
  if (!map.value || !result.request) {
    return;
  }
  const voxelUrl = resolveOutputUrl(result, "voxel_points_bin", result.outputs?.voxel_points_bin);
  const manifestUrl = resolveOutputUrl(result, "voxel_manifest_json", result.outputs?.voxel_manifest_json);
  if (!voxelUrl || !manifestUrl) {
    return;
  }
  try {
    const points = await loadVoxelData(voxelUrl, manifestUrl);
    if (map.value && task.value?.task_id === result.task_id) {
      voxelPoints.value = points;
      voxelTaskId.value = result.task_id;
      const control = getLayerControl("voxel");
      if (control) {
        control.available = points.length > 0;
      }
      applyVoxelLayerControl();
    }
  } catch (error) {
    console.error("Failed to load voxel data:", error);
  }
}

async function loadClippedVolumeLayer(result: CoverageTaskStatus) {
  if (!map.value) {
    return;
  }
  const cellsUrl = resolveOutputUrl(result, "clipped_volume_cells_bin", result.outputs?.clipped_volume_cells_bin);
  const manifestUrl = resolveOutputUrl(
    result,
    "clipped_volume_manifest_json",
    result.outputs?.clipped_volume_manifest_json
  );
  if (!cellsUrl || !manifestUrl) {
    return;
  }
  try {
    const { cells, manifest } = await loadClippedVolumeData(cellsUrl, manifestUrl);
    if (map.value && task.value?.task_id === result.task_id) {
      clippedVolumeCells.value = cells;
      clippedVolumeManifest.value = manifest;
      const control = getLayerControl("clippedVolume");
      if (control) {
        control.available = cells.length > 0;
      }
      syncRadarVolumeLayer();
      applyClippedVolumeLayerControl();
    }
  } catch (error) {
    console.error("Failed to load clipped volume data:", error);
  }
}

function resolveOutputUrl(result: CoverageTaskStatus, kind: string, fallback?: string | null) {
  const files = Array.isArray(result.output_files) ? result.output_files : [];
  const file = files.find((item) => item.kind === kind && item.exists && item.url);
  if (file) {
    return resolveAssetUrl(file.url);
  }
  return resolveAssetUrl(fallback);
}

function handleLayerControlUpdate(key: string, patch: Partial<Pick<ResultLayerControl, "visible" | "opacity">>) {
  const control = layerControls.find((item) => item.key === key);
  if (!control) {
    return;
  }
  if (patch.visible != null) {
    control.visible = patch.visible;
  }
  if (patch.opacity != null) {
    control.opacity = Math.min(0.8, Math.max(0, patch.opacity));
  }
  applyLayerControl(control);
}

function handleSelectHeightLayer(heightM: number) {
  selectedHeightLayerM.value = heightM;
  applyHeightLayerControl();
}

async function handleFocusResult() {
  if (!map.value || (!fusionResult.value && (!task.value || task.value.status !== "finished"))) {
    ElMessage.info("暂无可定位的结果");
    return;
  }
  const token = ++focusToken;
  const taskId = task.value?.task_id;
  const currentViewToken = viewToken;

  const urls = layerControls
    .flatMap((control) => {
      if (control.key === "heightLayer" && control.available) {
        const selected = getSelectedHeightLayer();
        return selected ? [selected.visibleUrl, selected.blockedUrl].filter((url): url is string => !!url) : [];
      }
      if (!task.value || task.value.status !== "finished" || !control.available || !isResultLayerKey(control.key)) {
        return [];
      }
      return [resolveLayerOutputUrl(task.value as CoverageTaskStatus, control.key)];
    })
    .filter((url): url is string => !!url);

  const bounds = new maplibregl.LngLatBounds();
  let hasBounds = false;
  try {
    for (const url of urls) {
      const geojson = await fetch(url).then((response) => {
        if (!response.ok) {
          throw new Error(`结果文件读取失败：${response.status}`);
        }
        return response.json() as Promise<GeoJSON.GeoJSON>;
      });
      if (token !== focusToken || currentViewToken !== viewToken || (taskId && task.value?.task_id !== taskId)) {
        return;
      }
      const layerBounds = getGeoJsonBounds(geojson);
      if (layerBounds) {
        bounds.extend(layerBounds.getSouthWest());
        bounds.extend(layerBounds.getNorthEast());
        hasBounds = true;
      }
    }
    for (const geojson of getVisibleFusionGeoJsons()) {
      const layerBounds = getGeoJsonBounds(geojson);
      if (layerBounds) {
        bounds.extend(layerBounds.getSouthWest());
        bounds.extend(layerBounds.getNorthEast());
        hasBounds = true;
      }
    }
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "结果定位失败");
    return;
  }

  if (token !== focusToken || currentViewToken !== viewToken || (taskId && task.value?.task_id !== taskId)) {
    return;
  }
  if (!hasBounds) {
    ElMessage.warning("结果范围为空，无法定位");
    return;
  }
  map.value.fitBounds(bounds, { padding: 80, maxZoom: 13, duration: 600 });
}

function applyAllLayerControls() {
  for (const control of layerControls) {
    applyLayerControl(control);
  }
}

function applyLayerControl(control: ResultLayerControl) {
  if (!map.value || !control.available) {
    return;
  }
  if (control.key === "radarVolume" || control.key === "radarRequestBoundary") {
    syncRadarVolumeLayer();
    return;
  }
  if (control.key === "voxel") {
    applyVoxelLayerControl();
    return;
  }
  if (control.key === "clippedVolume") {
    applyClippedVolumeLayerControl();
    return;
  }
  if (control.key === "heightLayer") {
    applyHeightLayerControl();
    return;
  }
  if (isFusionLayerKey(control.key)) {
    applyFusionLayerControl(control.key);
    return;
  }
  if (!isResultLayerKey(control.key)) {
    return;
  }
  setResultLayerVisibility(map.value, control.key, control.visible);
  setResultLayerOpacity(map.value, control.key, control.opacity);
}

function clearLayerAvailability() {
  focusToken++;
  radarVolumeTaskId.value = null;
  radarVolumeRequest.value = coverageRequest;
  const beamPreviewAvailable = canPreviewBeam(coverageRequest.dem_id, dem.value?.dem_id);
  for (const control of layerControls) {
    control.available = isBeamPreviewLayer(control.key) && beamPreviewAvailable;
    control.visible = defaultLayerVisibility(control.key);
    control.opacity = control.defaultOpacity;
  }
  voxelPoints.value = [];
  voxelTaskId.value = null;
  clippedVolumeCells.value = [];
  clippedVolumeManifest.value = null;
  heightLayerOptions.value = [];
  selectedHeightLayerM.value = null;
  if (map.value) {
    removeRadarVolume(map.value);
    removeClippedVolumeLayer(map.value);
    removeVoxelLayer(map.value);
    removeFusionLayers(map.value);
    if (beamPreviewAvailable) {
      syncRadarVolumeLayer(coverageRequest);
    }
  }
}

function updateLayerAvailability(available: Partial<Record<LayerKey, boolean>>) {
  for (const control of layerControls) {
    control.available = available[control.key] ?? false;
    control.visible = defaultLayerVisibility(control.key);
    control.opacity = control.defaultOpacity;
  }
}

function tuneVolumeLayerDefaults(hasClippedVolume: boolean) {
  const radarControl = getLayerControl("radarVolume");
  if (radarControl?.available && hasClippedVolume) {
    radarControl.opacity = 0.22;
  }
}

function updateFusionLayerAvailability(available: boolean) {
  for (const key of ["fusionVisible", "fusionOverlap", "fusionBlind"] as FusionLayerKey[]) {
    const control = getLayerControl(key);
    if (control) {
      control.available = available;
      control.visible = true;
      control.opacity = control.defaultOpacity;
    }
  }
}

function applyFusionLayerControls() {
  for (const key of ["fusionVisible", "fusionOverlap", "fusionBlind"] as FusionLayerKey[]) {
    applyFusionLayerControl(key);
  }
}

function getVisibleFusionGeoJsons(): GeoJSON.GeoJSON[] {
  if (!fusionResult.value) {
    return [];
  }
  const entries: Array<[FusionLayerKey, GeoJSON.GeoJSON]> = [
    ["fusionVisible", fusionResult.value.visible_union_geojson],
    ["fusionOverlap", fusionResult.value.overlap_geojson],
    ["fusionBlind", fusionResult.value.blind_geojson]
  ];
  return entries
    .filter(([key]) => {
      const control = getLayerControl(key);
      return Boolean(control?.available && control.visible);
    })
    .map(([, geojson]) => geojson);
}

function applyFusionLayerControl(key: FusionLayerKey) {
  if (!map.value) {
    return;
  }
  const control = getLayerControl(key);
  if (!control?.available || !fusionResult.value) {
    setFusionLayerVisibility(map.value, key, false);
    return;
  }
  setFusionLayerVisibility(map.value, key, control.visible);
  setFusionLayerOpacity(map.value, key, control.opacity);
}

function resolveLayerOutputUrl(result: CoverageTaskStatus, key: ResultLayerKey) {
  const outputKind: Record<ResultLayerKey, keyof NonNullable<CoverageTaskStatus["outputs"]>> = {
    range: "range_geojson",
    blocked: "blocked_geojson",
    visible: "visible_geojson"
  };
  const kind = outputKind[key];
  return resolveOutputUrl(result, kind, result.outputs?.[kind]);
}

function getLayerControl(key: LayerKey) {
  return layerControls.find((item) => item.key === key);
}

function isBeamPreviewLayer(key: LayerKey) {
  return key === "radarVolume" || key === "radarRequestBoundary";
}

function updateBeamPreviewAvailability() {
  const available = canPreviewBeam(coverageRequest.dem_id, dem.value?.dem_id);
  for (const key of ["radarVolume", "radarRequestBoundary"] as const) {
    const control = getLayerControl(key);
    if (control) {
      control.available = available;
    }
  }
}

function defaultLayerVisibility(key: LayerKey) {
  return key !== "voxel" && key !== "radarRequestBoundary";
}

function isFusionLayerKey(key: LayerKey): key is FusionLayerKey {
  return key === "fusionVisible" || key === "fusionOverlap" || key === "fusionBlind";
}

function syncRadarVolumeLayer(request?: CoverageRequest) {
  if (!map.value || !map.value.loaded()) {
    return;
  }
  const control = getLayerControl("radarVolume");
  const boundaryControl = getLayerControl("radarRequestBoundary");
  const showSolid = Boolean(control?.available && control.visible);
  const showBoundary = Boolean(boundaryControl?.available && boundaryControl.visible);
  if (!showSolid && !showBoundary) {
    removeRadarVolume(map.value);
    return;
  }
  const renderRequest = request ?? radarVolumeRequest.value ?? coverageRequest;
  const displayedModel = radarVolumeTaskId.value === task.value?.task_id ? task.value?.model ?? null : null;
  const exactProfile = displayedModel?.beam_clip_profile ?? null;
  const renderRangeM = resolveBeamRenderRange(
    renderRequest.coverage.max_range_m,
    displayedModel?.effective_max_range_m
  );
  const volumeRequest = renderRangeM === renderRequest.coverage.max_range_m
    ? renderRequest
    : {
        ...renderRequest,
        coverage: { ...renderRequest.coverage, max_range_m: renderRangeM }
      };
  const requestDem = demList.value.find((item) => item.dem_id === renderRequest.dem_id)
    ?? (dem.value?.dem_id === renderRequest.dem_id ? dem.value : null);
  const clipProfile = exactProfile ?? clipProfileFromBounds(
    requestDem?.bounds ?? [],
    renderRequest.radar,
    renderRangeM
  );
  addOrUpdateRadarVolume(map.value, volumeRequest, {
    opacity: showSolid ? control?.opacity ?? 0.62 : 0,
    showScanPlane: showSolid && !(getLayerControl("clippedVolume")?.available && clippedVolumeCells.value.length),
    clipProfile,
    showFullRequestOutline: showBoundary,
    referenceOpacity: boundaryControl?.opacity ?? 0.45
  });
  moveRadarMarkerToTop(map.value);
}

function applyVoxelLayerControl() {
  if (!map.value) {
    return;
  }
  const control = getLayerControl("voxel");
  if (!control?.available || !control.visible) {
    removeVoxelLayer(map.value);
    return;
  }
  if (!voxelPoints.value.length || voxelTaskId.value !== task.value?.task_id) {
    if (task.value?.status === "finished") {
      void loadVoxelLayer(task.value);
    }
    return;
  }
  addOrUpdateVoxelLayer(map.value, voxelPoints.value, { opacity: control.opacity });
}

function applyClippedVolumeLayerControl() {
  if (!map.value) {
    return;
  }
  const control = getLayerControl("clippedVolume");
  if (!control?.available || !control.visible || !clippedVolumeCells.value.length || !clippedVolumeManifest.value) {
    removeClippedVolumeLayer(map.value);
    return;
  }
  const request = radarVolumeRequest.value ?? task.value?.request ?? coverageRequest;
  addOrUpdateClippedVolumeLayer(map.value, clippedVolumeCells.value, clippedVolumeManifest.value, {
    opacity: control.opacity,
    scanMode: request.coverage.scan_mode,
    azimuthDeg: request.coverage.azimuth_deg,
    beamWidthDeg: request.coverage.beam_width_deg,
    radarLon: request.radar.lon,
    radarLat: request.radar.lat
  });
}

function applyHeightLayerControl() {
  if (!map.value) {
    return;
  }
  const control = getLayerControl("heightLayer");
  const selected = getSelectedHeightLayer();
  if (!control?.available || !selected) {
    setHeightLayerVisibility(false);
    return;
  }
  addOrUpdateGeoJsonLayer(
    map.value,
    "height-layer",
    selected.visibleUrl,
    {
      "fill-color": "#14b8a6",
      "fill-opacity": control.visible ? control.opacity : 0
    },
    { "line-color": "#0f766e", "line-opacity": control.visible ? Math.max(control.opacity, 0.32) : 0, "line-width": 1 }
  );
  if (selected.blockedUrl) {
    addOrUpdateGeoJsonLayer(
      map.value,
      "height-layer-blocked",
      selected.blockedUrl,
      {
        "fill-color": "#ef4444",
        "fill-opacity": control.visible ? Math.max(control.opacity * 0.72, 0.12) : 0
      },
      {
        "line-color": "#b91c1c",
        "line-opacity": control.visible ? Math.max(control.opacity, 0.3) : 0,
        "line-width": 1
      }
    );
  } else {
    for (const layerId of ["height-layer-blocked", "height-layer-blocked-outline"]) {
      if (map.value.getLayer(layerId)) {
        map.value.setLayoutProperty(layerId, "visibility", "none");
      }
    }
  }
  setHeightLayerVisibility(control.visible);
  setHeightLayerOpacity(control.opacity);
  moveRadarMarkerToTop(map.value);
}

function setHeightLayerVisibility(visible: boolean) {
  if (!map.value) {
    return;
  }
  const visibility = visible ? "visible" : "none";
  for (const layerId of ["height-layer", "height-layer-outline", "height-layer-blocked", "height-layer-blocked-outline"]) {
    if (map.value.getLayer(layerId)) {
      map.value.setLayoutProperty(layerId, "visibility", visibility);
    }
  }
}

function setHeightLayerOpacity(opacity: number) {
  if (!map.value) {
    return;
  }
  if (map.value.getLayer("height-layer")) {
    map.value.setPaintProperty("height-layer", "fill-opacity", opacity);
  }
  if (map.value.getLayer("height-layer-outline")) {
    map.value.setPaintProperty("height-layer-outline", "line-opacity", opacity > 0 ? Math.max(opacity, 0.32) : 0);
  }
  if (map.value.getLayer("height-layer-blocked")) {
    map.value.setPaintProperty("height-layer-blocked", "fill-opacity", opacity > 0 ? Math.max(opacity * 0.72, 0.12) : 0);
  }
  if (map.value.getLayer("height-layer-blocked-outline")) {
    map.value.setPaintProperty("height-layer-blocked-outline", "line-opacity", opacity > 0 ? Math.max(opacity, 0.3) : 0);
  }
}

function getSelectedHeightLayer() {
  return heightLayerOptions.value.find((item) => item.heightM === selectedHeightLayerM.value) ?? null;
}

function normalizeHeightLayerOptions(manifest: HeightLayerManifest, manifestUrl: string): HeightLayerOption[] {
  const layers = Array.isArray(manifest.height_layers) ? manifest.height_layers : [];
  return layers
    .flatMap((item) => {
      if (typeof item.height_m !== "number" || !Number.isFinite(item.height_m)) {
        return [];
      }
      const visibleFilename = item.visible_filename ?? item.filename;
      const visibleUrl = visibleFilename ? resolveHeightLayerUrl(manifestUrl, visibleFilename) : null;
      const blockedUrl = item.blocked_filename ? resolveHeightLayerUrl(manifestUrl, item.blocked_filename) : null;
      if (!visibleUrl) {
        return [];
      }
      const visibleArea = typeof item.visible_area_m2 === "number" ? item.visible_area_m2 : 0;
      const blockedArea = typeof item.blocked_area_m2 === "number" ? item.blocked_area_m2 : 0;
      return [{
        heightM: item.height_m,
        label: `${formatHeightLabel(item.height_m)} 可见 ${formatAreaLabel(visibleArea)} / 遮挡 ${formatAreaLabel(blockedArea)}`,
        visibleUrl,
        blockedUrl,
        visibleAreaM2: visibleArea,
        blockedAreaM2: blockedArea
      }];
    })
    .sort((a, b) => a.heightM - b.heightM);
}

function resolveHeightLayerUrl(manifestUrl: string, filename: string) {
  if (/^(https?:|blob:|data:)/.test(filename)) {
    return filename;
  }
  try {
    return new URL(filename, manifestUrl).toString();
  } catch {
    const base = manifestUrl.slice(0, manifestUrl.lastIndexOf("/") + 1);
    return `${base}${filename}`;
  }
}

function chooseInitialHeightLayer(options: HeightLayerOption[], request?: CoverageRequest | null) {
  const targetHeight = request?.target.height_m ?? coverageRequest.target.height_m;
  return options.find((item) => item.heightM >= targetHeight)?.heightM ?? options[options.length - 1]?.heightM ?? null;
}

function formatHeightLabel(heightM: number) {
  if (Math.abs(heightM) >= 1000) {
    return `${(heightM / 1000).toFixed(heightM % 1000 === 0 ? 0 : 1)} km`;
  }
  return `${heightM.toFixed(heightM % 1 === 0 ? 0 : 1)} m`;
}

function formatAreaLabel(areaM2: number) {
  if (!Number.isFinite(areaM2) || areaM2 <= 0) {
    return "0 km²";
  }
  return `${(areaM2 / 1_000_000).toFixed(areaM2 >= 10_000_000 ? 1 : 2)} km²`;
}

function isResultLayerKey(key: LayerKey): key is ResultLayerKey {
  return key === "range" || key === "blocked" || key === "visible";
}
</script>
