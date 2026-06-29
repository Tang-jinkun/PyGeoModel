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
      <LayerControlPanel :layers="layerControls" @update-layer="handleLayerControlUpdate" @focus-result="handleFocusResult" />
      <ResultPanel :task="task" @restore-request="restoreRequest" />
    </section>
  </main>
</template>

<script setup lang="ts">
import maplibregl from "maplibre-gl";
import { ElMessage } from "element-plus";
import { onMounted, reactive, ref, shallowRef } from "vue";

import {
  createCoverageTask,
  deleteDem,
  deleteCoverageTask,
  defaultCoverageRequest,
  demTerrainUrlTemplate,
  demTileUrlTemplate,
  getCoverageTask,
  listCoverageTasks,
  listDems,
  normalizeCoverageRequest,
  resolveAssetUrl,
  uploadDem,
  type CoverageRequest,
  type CoverageTaskSummary,
  type CoverageTaskStatus,
  type DemMetadata
} from "./api/client";
import ControlPanel from "./components/ControlPanel.vue";
import LayerControlPanel from "./components/LayerControlPanel.vue";
import ResultPanel from "./components/ResultPanel.vue";
import {
  addOrUpdateGeoJsonLayer,
  addOrUpdateDemRasterLayer,
  addOrUpdateDemTerrain,
  addRadarMarker,
  getGeoJsonBounds,
  moveRadarMarkerToTop,
  removeDemRasterLayer,
  removeDemTerrain,
  removeResultLayers,
  setResultLayerOpacity,
  setResultLayerVisibility,
  type ResultLayerKey
} from "./map/mapLayers";
import { addOrUpdateRadarVolume, removeRadarVolume } from "./map/radarVolumeLayer";
import { addOrUpdateVoxelLayer, loadVoxelData, removeVoxelLayer } from "./map/voxelLayer";

interface ResultLayerControl {
  key: ResultLayerKey;
  label: string;
  description: string;
  color: string;
  visible: boolean;
  opacity: number;
  defaultOpacity: number;
  available: boolean;
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
const layerControls = reactive<ResultLayerControl[]>([
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
    label: "理论范围",
    description: "最大探测半径",
    color: "#2563eb",
    visible: false,
    opacity: 0.08,
    defaultOpacity: 0.08,
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
  map.value.on("load", () => {
    if (dem.value) {
      applyDemMapLayers(dem.value);
    }
  });
});

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
    removeResultLayers(map.value);
    clearLayerAvailability();
    addRadarMarker(map.value, coverageRequest.radar.lon, coverageRequest.radar.lat);
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
      if (map.value) {
        removeResultLayers(map.value);
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
    if (map.value) {
      removeResultLayers(map.value);
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
    if (selectedTaskId.value === taskId) {
      pollToken++;
      viewToken++;
      selectedTaskId.value = null;
      task.value = null;
      if (map.value) {
        removeResultLayers(map.value);
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
  clearLayerAvailability();

  dem.value = restoredDem;
  if (map.value) {
    removeResultLayers(map.value);
    addRadarMarker(map.value, normalized.radar.lon, normalized.radar.lat);
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
  coverageRequest.advanced.max_elevation_deg = request.advanced.max_elevation_deg;
  coverageRequest.advanced.height_layers_m = [...(request.advanced.height_layers_m ?? [])];
  coverageRequest.reserved_radar_params = { ...(request.reserved_radar_params ?? {}) };
}

function loadOutputs(result: CoverageTaskStatus) {
  if (!map.value) {
    return;
  }
  removeResultLayers(map.value);
  removeRadarVolume(map.value);
  removeVoxelLayer(map.value);

  const visible = resolveOutputUrl(result, "visible_geojson", result.outputs?.visible_geojson);
  const blocked = resolveOutputUrl(result, "blocked_geojson", result.outputs?.blocked_geojson);
  const range = resolveOutputUrl(result, "range_geojson", result.outputs?.range_geojson);
  if (!range && !blocked && !visible) {
    clearLayerAvailability();
    return;
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
  moveRadarMarkerToTop(map.value);
  updateLayerAvailability({ range: !!range, blocked: !!blocked, visible: !!visible });
  applyAllLayerControls();

  // Load voxel point cloud if available
  if (result.request) {
    void loadVoxelLayer(result);
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
      addOrUpdateVoxelLayer(map.value, points);
    }
  } catch (error) {
    console.error("Failed to load voxel data:", error);
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

function handleLayerControlUpdate(key: ResultLayerKey, patch: Partial<Pick<ResultLayerControl, "visible" | "opacity">>) {
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

async function handleFocusResult() {
  if (!map.value || !task.value || task.value.status !== "finished") {
    ElMessage.info("暂无可定位的结果");
    return;
  }
  const token = ++focusToken;
  const taskId = task.value.task_id;
  const currentViewToken = viewToken;

  const urls = layerControls
    .filter((control) => control.available)
    .map((control) => resolveLayerOutputUrl(task.value as CoverageTaskStatus, control.key))
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
      if (token !== focusToken || currentViewToken !== viewToken || task.value?.task_id !== taskId) {
        return;
      }
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

  if (token !== focusToken || currentViewToken !== viewToken || task.value?.task_id !== taskId) {
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
  setResultLayerVisibility(map.value, control.key, control.visible);
  setResultLayerOpacity(map.value, control.key, control.opacity);
}

function clearLayerAvailability() {
  focusToken++;
  for (const control of layerControls) {
    control.available = false;
    control.visible = true;
    control.opacity = control.defaultOpacity;
  }
}

function updateLayerAvailability(available: Record<ResultLayerKey, boolean>) {
  for (const control of layerControls) {
    control.available = available[control.key];
    control.visible = true;
    control.opacity = control.defaultOpacity;
  }
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
</script>
