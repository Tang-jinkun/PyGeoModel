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
      :busy="busy"
      @upload="handleUpload"
      @select-dem="handleSelectDem"
      @select-task="handleSelectTask"
      @restore-task="handleRestoreTask"
      @delete-task="handleDeleteTask"
      @refresh-tasks="refreshTaskList"
      @run="handleRun"
    />

    <section class="map-shell">
      <div ref="mapContainer" class="map-container"></div>
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
  deleteCoverageTask,
  getCoverageTask,
  listCoverageTasks,
  listDems,
  resolveAssetUrl,
  uploadDem,
  type CoverageRequest,
  type CoverageTaskSummary,
  type CoverageTaskStatus,
  type DemMetadata
} from "./api/client";
import ControlPanel from "./components/ControlPanel.vue";
import ResultPanel from "./components/ResultPanel.vue";
import { addOrUpdateGeoJsonLayer, addRadarMarker, removeResultLayers } from "./map/mapLayers";

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
let pollToken = 0;
let viewToken = 0;
let taskListRequestToken = 0;
const busy = ref(false);

const coverageRequest = reactive<CoverageRequest>({
  dem_id: "",
  radar: {
    lon: 105.123456,
    lat: 35.123456,
    height_m: 10
  },
  target: {
    height_m: 0
  },
  coverage: {
    max_range_m: 50000,
    scan_mode: "omni",
    azimuth_deg: 90,
    beam_width_deg: 120
  },
  advanced: {
    use_curvature: true,
    curvature_coeff: 0.75,
    output_simplify_tolerance_m: 30
  }
});

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
    map.value?.addSource("terrain-dem", {
      type: "raster-dem",
      tiles: ["https://demotiles.maplibre.org/terrain-tiles/{z}/{x}/{y}.png"],
      tileSize: 256,
      encoding: "terrarium",
      maxzoom: 12
    });
    map.value?.setTerrain({ source: "terrain-dem", exaggeration: 1.4 });
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
    map.value?.flyTo({ center: [coverageRequest.radar.lon, coverageRequest.radar.lat], zoom: 9 });
  }
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
    addRadarMarker(map.value, coverageRequest.radar.lon, coverageRequest.radar.lat);
    task.value = await createCoverageTask(coverageRequest);
    selectedTaskId.value = task.value.task_id;
    await refreshTaskList();
    await pollTask(task.value.task_id, token);
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
    task.value = selected;
    if (!selected.request) {
      ElMessage.warning("该历史任务没有可恢复的参数");
      return;
    }
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
    }
    await refreshTaskList();
    ElMessage.success("历史任务已删除");
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "删除任务失败");
  } finally {
    deletingTaskId.value = null;
  }
}

function restoreRequest(request: CoverageRequest) {
  pollToken++;
  viewToken++;
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

  dem.value = demList.value.find((item) => item.dem_id === request.dem_id) ?? dem.value;
  if (map.value) {
    removeResultLayers(map.value);
    addRadarMarker(map.value, request.radar.lon, request.radar.lat);
    map.value.flyTo({ center: [request.radar.lon, request.radar.lat], zoom: 9 });
  }
  ElMessage.success("历史参数已恢复到表单");
}

function loadOutputs(result: CoverageTaskStatus) {
  if (!map.value || !result.outputs) {
    return;
  }
  removeResultLayers(map.value);

  const visible = resolveAssetUrl(result.outputs.visible_geojson);
  const blocked = resolveAssetUrl(result.outputs.blocked_geojson);
  const range = resolveAssetUrl(result.outputs.range_geojson);

  if (range) {
    addOrUpdateGeoJsonLayer(
      map.value,
      "range-layer",
      range,
      { "fill-color": "#2563eb", "fill-opacity": 0.08 },
      { "line-color": "#2563eb", "line-width": 2 }
    );
  }
  if (blocked) {
    addOrUpdateGeoJsonLayer(map.value, "blocked-layer", blocked, {
      "fill-color": "#dc2626",
      "fill-opacity": 0.28
    });
  }
  if (visible) {
    addOrUpdateGeoJsonLayer(map.value, "visible-layer", visible, {
      "fill-color": "#16a34a",
      "fill-opacity": 0.38
    });
  }
}
</script>
