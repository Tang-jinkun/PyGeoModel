import type maplibregl from "maplibre-gl";
import { ref, shallowRef } from "vue";

import { createTaskClient } from "../api/tasks";
import { fitGeoJsonBounds } from "../map/mapLayers";
import {
  createSpatialDraft,
  reduceSpatialDraft,
  type SpatialCoordinate,
  type SpatialDraft,
  type SpatialDraftAction,
  type SpatialThreat
} from "../map/spatialInput";
import { getModelDefinition, type ModelMetricMap, type ModelRequestMap } from "../models/registry";
import type { RadarDiagnostics, RadarMetrics, RadarModelMetadata, RadarRequest } from "../models/radar/types";
import type { ModelId, OutputFile, SpatialInputKind, TaskSummary } from "../models/shared";

export type TaskOutputLayerStatus = "idle" | "loading" | "ready" | "error";

export interface TaskOutputLayerState {
  kind: string;
  status: TaskOutputLayerStatus;
  visible: boolean;
  opacity: number;
  data: GeoJSON.GeoJSON | null;
  error: string | null;
}

export type RadarTaskSummary = TaskSummary<RadarRequest, RadarMetrics, RadarModelMetadata, RadarDiagnostics>;
export type ModelTaskSummary<K extends ModelId> = K extends "radar"
  ? RadarTaskSummary
  : TaskSummary<ModelRequestMap[K], ModelMetricMap[K]>;

export interface LoadedTaskOutputs<K extends ModelId> {
  modelId: K;
  task: ModelTaskSummary<K>;
  metrics: ModelMetricMap[K] | null;
  outputFiles: OutputFile[];
  layerStates: TaskOutputLayerState[];
}

interface TaskResultClient {
  metrics(taskId: string): Promise<unknown>;
  outputs(taskId: string): Promise<OutputFile[]>;
}

export interface UseMapWorkspaceOptions {
  clientFactory?: (basePath: string, modelId: ModelId) => TaskResultClient;
  fetchGeoJson?: (url: string) => Promise<unknown>;
}

export function useMapWorkspace(kind: SpatialInputKind, initialDraft?: SpatialDraft, options: UseMapWorkspaceOptions = {}) {
  const draft = shallowRef<SpatialDraft>(initialDraft ? structuredClone(initialDraft) : createSpatialDraft(kind));
  const loadedTask = shallowRef<TaskSummary<never, unknown, unknown, unknown> | null>(null);
  const taskMetrics = shallowRef<Record<string, unknown> | null>(null);
  const outputFiles = ref<OutputFile[]>([]);
  const layerStates = ref<TaskOutputLayerState[]>([]);
  const clients = new Map<ModelId, TaskResultClient>();
  const clientFactory = options.clientFactory ?? ((basePath: string) => createTaskClient(basePath));
  const fetchGeoJson = options.fetchGeoJson ?? requestGeoJson;
  let outputLoadVersion = 0;

  function dispatch(action: SpatialDraftAction) {
    draft.value = reduceSpatialDraft(draft.value, action);
    return draft.value;
  }

  function pickPoint(coordinate: SpatialCoordinate) {
    return dispatch({ type: "set-point", coordinate });
  }

  function appendWaypoint(coordinate: SpatialCoordinate) {
    return dispatch({ type: "append", coordinate });
  }

  function moveWaypoint(index: number, coordinate: SpatialCoordinate) {
    return dispatch({ type: "move", index, coordinate });
  }

  function removeWaypoint(index: number) {
    return dispatch({ type: "remove", index });
  }

  function setStart(coordinate: SpatialCoordinate) {
    return dispatch({ type: "set-start", coordinate });
  }

  function setEnd(coordinate: SpatialCoordinate) {
    return dispatch({ type: "set-end", coordinate });
  }

  function addThreat(threat: SpatialThreat) {
    return dispatch({ type: "add-threat", threat });
  }

  function updateThreat(id: string, coordinate: SpatialCoordinate, properties?: Record<string, unknown>) {
    return dispatch({ type: "update-threat", id, coordinate, properties });
  }

  function removeThreat(id: string) {
    return dispatch({ type: "remove-threat", id });
  }

  function undo() {
    return dispatch({ type: "undo" });
  }

  function clear() {
    return dispatch({ type: "clear" });
  }

  function focusBounds(map: maplibregl.Map, data: GeoJSON.GeoJSON) {
    return fitGeoJsonBounds(map, data);
  }

  function replaceDraft(nextDraft: SpatialDraft) {
    draft.value = structuredClone(nextDraft);
  }

  function clientFor(modelId: ModelId) {
    const existing = clients.get(modelId);
    if (existing) return existing;
    const client = clientFactory(getModelDefinition(modelId).taskBasePath, modelId);
    clients.set(modelId, client);
    return client;
  }

  async function loadTaskOutputs<K extends ModelId>(modelId: K, task: ModelTaskSummary<K>): Promise<LoadedTaskOutputs<K> | null> {
    const version = ++outputLoadVersion;
    const definition = getModelDefinition(modelId);
    loadedTask.value = task as TaskSummary<never, unknown, unknown, unknown>;
    taskMetrics.value = toMetricRecord(task.metrics);
    outputFiles.value = [...task.output_files];
    layerStates.value = definition.outputLayers.map((layer) => createLayerState(layer, task.status === "finished" ? "loading" : "idle"));

    if (task.status !== "finished") return snapshot(modelId, task);

    const client = clientFor(modelId);
    const [metricsResult, outputsResult] = await Promise.allSettled([
      client.metrics(task.task_id),
      client.outputs(task.task_id)
    ]);
    if (version !== outputLoadVersion) return null;

    if (metricsResult.status === "fulfilled") taskMetrics.value = toMetricRecord(metricsResult.value);
    if (outputsResult.status === "fulfilled") outputFiles.value = [...outputsResult.value];

    const files = outputFiles.value;
    const layerLoads = definition.outputLayers.map(async (layer) => {
      const url = resolveLayerUrl(layer.kind, files, task.outputs);
      if (!url) {
        updateLayer(version, layer.kind, { status: "idle", error: null });
        return;
      }

      try {
        const data = await fetchGeoJson(url);
        if (!isGeoJson(data)) throw new Error("Invalid GeoJSON document");
        updateLayer(version, layer.kind, { status: "ready", data, error: null });
      } catch {
        updateLayer(version, layer.kind, {
          status: "error",
          data: null,
          error: `${localizedLayerLabel(layer.kind, layer.label)}加载失败`
        });
      }
    });
    await Promise.allSettled(layerLoads);
    if (version !== outputLoadVersion) return null;
    return snapshot(modelId, task);
  }

  function setTaskLayerVisibility(kind: string, visible: boolean) {
    updateLayer(outputLoadVersion, kind, { visible });
  }

  function setTaskLayerOpacity(kind: string, opacity: number) {
    updateLayer(outputLoadVersion, kind, { opacity: Math.min(1, Math.max(0, opacity)) });
  }

  function focusTaskLayer(map: maplibregl.Map, kind: string) {
    const layer = layerStates.value.find((candidate) => candidate.kind === kind);
    return layer?.data ? focusBounds(map, layer.data) : false;
  }

  function clearTaskOutputs() {
    outputLoadVersion++;
    loadedTask.value = null;
    taskMetrics.value = null;
    outputFiles.value = [];
    layerStates.value = [];
  }

  function updateLayer(version: number, kind: string, patch: Partial<TaskOutputLayerState>) {
    if (version !== outputLoadVersion) return;
    layerStates.value = layerStates.value.map((layer) => layer.kind === kind ? { ...layer, ...patch } : layer);
  }

  function snapshot<K extends ModelId>(modelId: K, task: ModelTaskSummary<K>): LoadedTaskOutputs<K> {
    return {
      modelId,
      task,
      metrics: taskMetrics.value as ModelMetricMap[K] | null,
      outputFiles: [...outputFiles.value],
      layerStates: layerStates.value.map((layer) => ({ ...layer }))
    };
  }

  return {
    draft,
    dispatch,
    pickPoint,
    appendWaypoint,
    moveWaypoint,
    removeWaypoint,
    setStart,
    setEnd,
    addThreat,
    updateThreat,
    removeThreat,
    undo,
    clear,
    focusBounds,
    replaceDraft,
    loadedTask,
    taskMetrics,
    outputFiles,
    layerStates,
    loadTaskOutputs,
    setTaskLayerVisibility,
    setTaskLayerOpacity,
    focusTaskLayer,
    clearTaskOutputs
  };
}

function createLayerState(
  layer: { kind: string; defaultOpacity: number; primary?: boolean },
  status: TaskOutputLayerStatus
): TaskOutputLayerState {
  return {
    kind: layer.kind,
    status,
    visible: Boolean(layer.primary),
    opacity: layer.defaultOpacity,
    data: null,
    error: null
  };
}

function resolveLayerUrl(kind: string, files: readonly OutputFile[], legacyOutputs?: Record<string, string | null> | null) {
  const file = files.find((candidate) => candidate.kind === kind && candidate.exists);
  return file?.download_url || file?.url || legacyOutputs?.[kind] || null;
}

function toMetricRecord(value: unknown) {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function isGeoJson(value: unknown): value is GeoJSON.GeoJSON {
  if (!value || typeof value !== "object") return false;
  const type = (value as { type?: unknown }).type;
  return type === "Feature" || type === "FeatureCollection" || type === "Point" || type === "MultiPoint"
    || type === "LineString" || type === "MultiLineString" || type === "Polygon" || type === "MultiPolygon"
    || type === "GeometryCollection";
}

async function requestGeoJson(url: string) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`GeoJSON request failed (${response.status})`);
  return response.json();
}

function localizedLayerLabel(kind: string, fallback: string) {
  const labels: Record<string, string> = {
    footprint_geojson: "传感器足迹",
    blocked_geojson: "地形遮挡区",
    visible_geojson: "可见区",
    range_geojson: "探测范围"
  };
  return labels[kind] ?? fallback;
}
