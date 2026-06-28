<template>
  <main class="app-shell">
    <ControlPanel
      :model="coverageRequest"
      :dem="dem"
      :dem-list="demList"
      :task-list="taskList"
      :busy="busy"
      @upload="handleUpload"
      @select-dem="handleSelectDem"
      @select-task="handleSelectTask"
      @run="handleRun"
    />

    <section class="map-shell">
      <div ref="mapContainer" class="map-container"></div>
      <ResultPanel :task="task" />
    </section>
  </main>
</template>

<script setup lang="ts">
import maplibregl from "maplibre-gl";
import { ElMessage } from "element-plus";
import { onMounted, reactive, ref, shallowRef } from "vue";

import {
  createCoverageTask,
  getCoverageTask,
  listCoverageTasks,
  listDems,
  resolveAssetUrl,
  uploadDem,
  type CoverageRequest,
  type CoverageTaskStatus,
  type DemMetadata
} from "./api/client";
import ControlPanel from "./components/ControlPanel.vue";
import ResultPanel from "./components/ResultPanel.vue";
import { addOrUpdateGeoJsonLayer, addRadarMarker } from "./map/mapLayers";

const mapContainer = ref<HTMLDivElement | null>(null);
const map = shallowRef<maplibregl.Map | null>(null);
const dem = ref<DemMetadata | null>(null);
const demList = ref<DemMetadata[]>([]);
const task = ref<CoverageTaskStatus | null>(null);
const taskList = ref<CoverageTaskStatus[]>([]);
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
  try {
    taskList.value = await listCoverageTasks();
  } catch {
    taskList.value = [];
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
  try {
    addRadarMarker(map.value!, coverageRequest.radar.lon, coverageRequest.radar.lat);
    task.value = await createCoverageTask(coverageRequest);
    await refreshTaskList();
    await pollTask(task.value.task_id);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "计算失败");
  } finally {
    busy.value = false;
  }
}

async function pollTask(taskId: string) {
  for (;;) {
    await new Promise((resolve) => window.setTimeout(resolve, 1500));
    task.value = await getCoverageTask(taskId);
    void refreshTaskList();
    if (task.value.status === "finished") {
      loadOutputs(task.value);
      ElMessage.success("计算完成");
      return;
    }
    if (task.value.status === "failed") {
      throw new Error(task.value.message || "计算失败");
    }
  }
}

async function handleSelectTask(taskId: string) {
  try {
    const selected = await getCoverageTask(taskId);
    task.value = selected;
    if (selected.status === "finished") {
      loadOutputs(selected);
      ElMessage.success("历史任务已加载");
      return;
    }
    ElMessage.info(`任务状态：${selected.status}`);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "加载历史任务失败");
  }
}

function loadOutputs(result: CoverageTaskStatus) {
  if (!map.value || !result.outputs) {
    return;
  }

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
