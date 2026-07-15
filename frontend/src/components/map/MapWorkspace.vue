<template>
  <section ref="workspace" class="map-workspace" aria-label="Interactive map">
    <div ref="mapContainer" class="map-workspace__canvas"></div>
    <div v-if="editing" class="map-workspace__toolbar" role="toolbar" aria-label="Map editing commands">
      <ElTooltip content="Finish editing" :show-after="300">
        <ElButton circle :icon="Check" data-action="finish-editing" aria-label="Finish editing" @click="emit('finish')" />
      </ElTooltip>
      <ElTooltip content="Undo edit" :show-after="300">
        <ElButton circle :icon="RefreshLeft" data-action="undo-editing" aria-label="Undo edit" @click="emitCommand('undo')" />
      </ElTooltip>
      <ElTooltip content="Clear spatial input" :show-after="300">
        <ElButton circle :icon="Delete" data-action="clear-editing" aria-label="Clear spatial input" @click="emitCommand('clear')" />
      </ElTooltip>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Check, Delete, RefreshLeft } from "@element-plus/icons-vue";
import { ElButton, ElTooltip } from "element-plus";
import maplibregl from "maplibre-gl";
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from "vue";

import { demTerrainUrlTemplate, demTileUrlTemplate, type DemMetadata } from "../../api/dem";
import {
  addOrUpdateDemRasterLayer,
  addOrUpdateDemTerrain,
  fitGeoJsonBounds,
  removeDemRasterLayer,
  removeDemTerrain
} from "../../map/mapLayers";
import type {
  SpatialCoordinate,
  SpatialDraft,
  SpatialDraftAction
} from "../../map/spatialInput";
import type { SpatialInputKind } from "../../models/shared";

type EditTarget = "auto" | "point" | "route" | "start" | "end" | "threat";

const props = withDefaults(defineProps<{
  kind: SpatialInputKind;
  draft: SpatialDraft;
  editing?: boolean;
  editTarget?: EditTarget;
  activeThreatId?: string | null;
  dem?: DemMetadata | null;
  mapStyle?: string | maplibregl.StyleSpecification;
  center?: SpatialCoordinate;
  zoom?: number;
}>(), {
  editing: false,
  editTarget: "auto",
  activeThreatId: null,
  dem: null,
  mapStyle: (): maplibregl.StyleSpecification => ({
    version: 8,
    sources: {},
    layers: []
  }),
  center: () => [79.80513693057287, 31.4827708959419],
  zoom: 8
});

const emit = defineEmits<{
  "coordinate-edit": [coordinate: SpatialCoordinate];
  "spatial-edit": [action: SpatialDraftAction];
  "map-ready": [map: maplibregl.Map];
  finish: [];
  undo: [];
  clear: [];
}>();

const workspace = ref<HTMLElement | null>(null);
const mapContainer = ref<HTMLDivElement | null>(null);
const map = shallowRef<maplibregl.Map | null>(null);
let resizeObserver: ResizeObserver | null = null;
let transitionTarget: Element | null = null;
let styleLoaded = false;
let lastSyncedDemId: string | null = null;
let lastSyncedTerrainUrl: string | null = null;

onMounted(() => {
  if (!mapContainer.value || map.value) return;

  const instance = new maplibregl.Map({
    container: mapContainer.value,
    style: props.mapStyle,
    center: props.center,
    zoom: props.zoom
  });
  map.value = instance;
  instance.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
  instance.on("click", handleMapClick);
  instance.on("load", handleMapLoad);
  emit("map-ready", instance);

  transitionTarget = workspace.value?.closest(".workspace-shell") ?? workspace.value;
  transitionTarget?.addEventListener("transitionend", resizeAfterTransition);
  if (typeof ResizeObserver !== "undefined" && workspace.value) {
    resizeObserver = new ResizeObserver(() => instance.resize());
    resizeObserver.observe(workspace.value);
  }
});

onBeforeUnmount(() => {
  transitionTarget?.removeEventListener("transitionend", resizeAfterTransition);
  resizeObserver?.disconnect();
  const instance = map.value;
  if (!instance) return;
  instance.off("click", handleMapClick);
  instance.off("load", handleMapLoad);
  instance.remove();
  map.value = null;
});

watch(() => props.dem, (dem) => {
  if (!map.value || !styleLoaded) return;
  syncDem(map.value, dem);
});

function handleMapLoad() {
  if (!map.value) return;
  styleLoaded = true;
  syncDem(map.value, props.dem);
}

function syncDem(instance: maplibregl.Map, dem: DemMetadata | null) {
  if (!dem || dem.bounds.length !== 4) {
    removeDemTerrain(instance);
    removeDemRasterLayer(instance);
    lastSyncedDemId = null;
    lastSyncedTerrainUrl = null;
    return;
  }
  const terrainUrl = demTerrainUrlTemplate(dem.dem_id);
  if (lastSyncedDemId === dem.dem_id && lastSyncedTerrainUrl === terrainUrl) return;
  addOrUpdateDemRasterLayer(instance, demTileUrlTemplate(dem.dem_id), dem.bounds);
  addOrUpdateDemTerrain(instance, terrainUrl, dem.bounds);
  lastSyncedDemId = dem.dem_id;
  lastSyncedTerrainUrl = terrainUrl;
}

function handleMapClick(event: maplibregl.MapMouseEvent) {
  if (!props.editing) return;
  const coordinate = normalizeCoordinate([event.lngLat.lng, event.lngLat.lat]);
  emit("coordinate-edit", coordinate);
  const action = actionForCoordinate(coordinate);
  if (action) emit("spatial-edit", action);
}

function actionForCoordinate(coordinate: SpatialCoordinate): SpatialDraftAction | null {
  const target = props.editTarget;
  if (target === "point") return { type: "set-point", coordinate };
  if (target === "route") return { type: "append", coordinate };
  if (target === "start") return { type: "set-start", coordinate };
  if (target === "end") return { type: "set-end", coordinate };
  if (target === "threat") {
    return props.activeThreatId
      ? { type: "update-threat", id: props.activeThreatId, coordinate }
      : { type: "add-threat", threat: { id: crypto.randomUUID(), coordinate } };
  }
  if (props.kind === "point") return { type: "set-point", coordinate };
  if (props.kind === "point-or-route") return { type: "append", coordinate };
  return props.draft.start
    ? { type: "set-end", coordinate }
    : { type: "set-start", coordinate };
}

function normalizeCoordinate([longitude, latitude]: SpatialCoordinate): SpatialCoordinate {
  return [roundCoordinate(longitude), roundCoordinate(latitude)];
}

function roundCoordinate(value: number) {
  return Math.round(value * 1_000_000) / 1_000_000;
}

function emitCommand(type: "undo" | "clear") {
  if (type === "undo") {
    emit("undo");
  } else {
    emit("clear");
  }
  emit("spatial-edit", { type });
}

function resizeAfterTransition() {
  requestAnimationFrame(() => map.value?.resize());
}

function resize() {
  map.value?.resize();
}

function focusBounds(data: GeoJSON.GeoJSON) {
  return map.value ? fitGeoJsonBounds(map.value, data) : false;
}

defineExpose({ map, resize, focusBounds });
</script>

<style scoped>
.map-workspace {
  position: relative;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 240px;
  overflow: hidden;
}

.map-workspace__canvas {
  position: absolute;
  inset: 0;
}

.map-workspace__toolbar {
  position: absolute;
  z-index: 2;
  top: 10px;
  left: 10px;
  display: flex;
  gap: 4px;
  padding: 4px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  background: #ffffff;
  box-shadow: 0 1px 4px rgb(0 0 0 / 14%);
}
</style>
