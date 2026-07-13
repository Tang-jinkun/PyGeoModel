import { reactive, readonly, ref, toRaw } from "vue";
import { createTaskClient } from "../api/tasks";
import { getModelDefinition, MODEL_IDS } from "../models/registry";
import type { BaseModelRequest, ModelId, TaskSummary } from "../models/shared";

interface TaskClientLike {
  list?(): Promise<TaskSummary[]>;
  create?(request: BaseModelRequest): Promise<TaskSummary>;
  get(taskId: string): Promise<TaskSummary>;
  delete?(taskId: string): Promise<unknown>;
}

export interface UseTaskManagerOptions {
  pollIntervalMs: number;
  maxRetryDelayMs?: number;
  clientFactory?: (basePath: string, modelId: ModelId) => TaskClientLike;
}

const taskKey = (modelId: ModelId, taskId: string) => `${modelId}:${taskId}`;
const isTerminal = (task: TaskSummary) => task.status === "finished" || task.status === "failed";

function createTaskState() {
  const state = {} as Record<ModelId, TaskSummary[]>;
  for (const modelId of MODEL_IDS) state[modelId] = [];
  return state;
}

export function useTaskManager(options: UseTaskManagerOptions) {
  const tasksByModel = reactive(createTaskState());
  const selectedTaskKey = ref<string | null>(null);
  const connectionInterrupted = ref(false);
  const timers = new Map<string, ReturnType<typeof setTimeout>>();
  const failures = new Map<string, number>();
  const pollVersions = new Map<string, number>();
  const inFlightVersions = new Map<string, number>();
  const refreshVersions = new Map<ModelId, number>();
  const restoreVersions = new Map<string, number>();
  const inFlightRestores = new Map<string, Promise<TaskSummary | null>>();
  const clients = new Map<ModelId, TaskClientLike>();
  const clientFactory = options.clientFactory ?? ((basePath: string) => createTaskClient(basePath));
  const maxRetryDelayMs = options.maxRetryDelayMs ?? 30_000;
  let visibleModel: ModelId | null = null;
  let disposed = false;

  function clientFor(modelId: ModelId) {
    const existing = clients.get(modelId);
    if (existing) return existing;
    const client = clientFactory(getModelDefinition(modelId).taskBasePath, modelId);
    clients.set(modelId, client);
    return client;
  }

  function getTask(modelId: ModelId, taskId: string) {
    return tasksByModel[modelId].find((task) => task.task_id === taskId);
  }

  function syncConnectionState() {
    connectionInterrupted.value = failures.size > 0;
  }

  function clearFailure(key: string) {
    if (!failures.delete(key)) return;
    syncConnectionState();
  }

  function clearPollingState(key: string) {
    const timer = timers.get(key);
    if (timer !== undefined) clearTimeout(timer);
    timers.delete(key);
    failures.delete(key);
    pollVersions.set(key, (pollVersions.get(key) ?? 0) + 1);
    inFlightVersions.delete(key);
    syncConnectionState();
  }

  function storeTask(modelId: ModelId, task: TaskSummary) {
    const existingIndex = tasksByModel[modelId].findIndex(({ task_id }) => task_id === task.task_id);
    if (existingIndex === -1) tasksByModel[modelId].push(task);
    else tasksByModel[modelId][existingIndex] = task;
  }

  function invalidateRefresh(modelId: ModelId) {
    const version = (refreshVersions.get(modelId) ?? 0) + 1;
    refreshVersions.set(modelId, version);
    return version;
  }

  function invalidateRestore(key: string) {
    restoreVersions.set(key, (restoreVersions.get(key) ?? 0) + 1);
    inFlightRestores.delete(key);
  }

  function schedulePoll(modelId: ModelId, taskId: string, delayMs = options.pollIntervalMs) {
    const key = taskKey(modelId, taskId);
    if (disposed || timers.has(key) || inFlightVersions.has(key)) return;
    if (!pollVersions.has(key)) pollVersions.set(key, 0);
    const version = pollVersions.get(key) ?? 0;

    const timer = setTimeout(async () => {
      timers.delete(key);
      if (disposed) return;
      inFlightVersions.set(key, version);
      let nextDelay: number | null = null;
      try {
        const updated = await clientFor(modelId).get(taskId);
        if (disposed || pollVersions.get(key) !== version) return;
        clearFailure(key);
        storeTask(modelId, updated);
        if (!isTerminal(updated)) nextDelay = options.pollIntervalMs;
      } catch {
        if (disposed || pollVersions.get(key) !== version) return;
        const failureCount = (failures.get(key) ?? 0) + 1;
        failures.set(key, failureCount);
        syncConnectionState();
        nextDelay = Math.min(options.pollIntervalMs * 2 ** failureCount, maxRetryDelayMs);
      } finally {
        if (inFlightVersions.get(key) === version) inFlightVersions.delete(key);
        const current = getTask(modelId, taskId);
        if (!disposed && pollVersions.get(key) === version && current && !isTerminal(current) && nextDelay !== null) {
          schedulePoll(modelId, taskId, nextDelay);
        }
      }
    }, delayMs);
    timers.set(key, timer);
  }

  function track(modelId: ModelId, task: TaskSummary) {
    invalidateRefresh(modelId);
    const key = taskKey(modelId, task.task_id);
    invalidateRestore(key);
    storeTask(modelId, task);
    if (isTerminal(task)) clearPollingState(key);
    else schedulePoll(modelId, task.task_id);
  }

  async function submit(modelId: ModelId, request: BaseModelRequest) {
    const create = clientFor(modelId).create;
    if (!create) throw new Error(`Task client for ${modelId} does not support create`);
    const created = await create(request);
    invalidateRefresh(modelId);
    track(modelId, created);
    selectedTaskKey.value = taskKey(modelId, created.task_id);
    return created;
  }

  async function refreshModel(modelId: ModelId) {
    const list = clientFor(modelId).list;
    if (!list) throw new Error(`Task client for ${modelId} does not support list`);
    const refreshVersion = invalidateRefresh(modelId);
    const refreshed = await list();
    if (disposed || refreshVersions.get(modelId) !== refreshVersion) return refreshed;
    const refreshedIds = new Set(refreshed.map(({ task_id }) => task_id));

    for (const oldTask of tasksByModel[modelId]) {
      const key = taskKey(modelId, oldTask.task_id);
      clearPollingState(key);
      invalidateRestore(key);
    }
    tasksByModel[modelId] = refreshed;
    for (const task of refreshed) {
      if (!isTerminal(task)) schedulePoll(modelId, task.task_id);
    }

    if (selectedTaskKey.value?.startsWith(`${modelId}:`)) {
      const selectedTaskId = selectedTaskKey.value.slice(modelId.length + 1);
      if (!refreshedIds.has(selectedTaskId)) selectedTaskKey.value = null;
    }
    return refreshed;
  }

  function setVisibleModel(modelId: ModelId) {
    visibleModel = modelId;
  }

  function select(modelId: ModelId, taskId: string) {
    selectedTaskKey.value = taskKey(modelId, taskId);
  }

  async function remove(modelId: ModelId, taskId: string) {
    const deleteTask = clientFor(modelId).delete;
    if (!deleteTask) throw new Error(`Task client for ${modelId} does not support delete`);
    await deleteTask(taskId);

    invalidateRefresh(modelId);
    const key = taskKey(modelId, taskId);
    clearPollingState(key);
    invalidateRestore(key);
    const index = tasksByModel[modelId].findIndex(({ task_id }) => task_id === taskId);
    if (index !== -1) tasksByModel[modelId].splice(index, 1);
    if (selectedTaskKey.value === key) selectedTaskKey.value = null;
  }

  async function restoreRequest(modelId: ModelId, taskId: string): Promise<BaseModelRequest | null> {
    const task = getTask(modelId, taskId);
    if (!task) return null;
    if (task.request) return structuredClone(toRaw(task.request));

    const key = taskKey(modelId, taskId);
    let detailPromise = inFlightRestores.get(key);
    if (!detailPromise) {
      if (!restoreVersions.has(key)) restoreVersions.set(key, 0);
      const version = restoreVersions.get(key) ?? 0;
      detailPromise = clientFor(modelId).get(taskId).then((detailed) => {
        if (disposed || restoreVersions.get(key) !== version || !getTask(modelId, taskId)) return null;
        storeTask(modelId, detailed);
        return detailed;
      });
      inFlightRestores.set(key, detailPromise);
    }

    try {
      const detailed = await detailPromise;
      return detailed?.request ? structuredClone(toRaw(detailed.request)) : null;
    } finally {
      if (inFlightRestores.get(key) === detailPromise) inFlightRestores.delete(key);
    }
  }

  function dispose() {
    if (disposed) return;
    disposed = true;
    for (const modelId of MODEL_IDS) invalidateRefresh(modelId);
    for (const timer of timers.values()) clearTimeout(timer);
    timers.clear();
    failures.clear();
    inFlightVersions.clear();
    pollVersions.clear();
    restoreVersions.clear();
    inFlightRestores.clear();
    syncConnectionState();
  }

  return {
    tasksByModel: readonly(tasksByModel),
    selectedTaskKey: readonly(selectedTaskKey),
    connectionInterrupted: readonly(connectionInterrupted),
    submit,
    track,
    refreshModel,
    setVisibleModel,
    getTask,
    select,
    remove,
    restoreRequest,
    dispose
  };
}
