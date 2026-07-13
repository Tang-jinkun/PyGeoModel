import { clipProfileFromBounds, resolveBeamRenderRange } from "../../map/beamClipProfile";
import type { TaskSummary } from "../shared";
import type {
  BeamClipProfile,
  RadarDiagnostics,
  RadarMetrics,
  RadarModelMetadata,
  RadarRequest
} from "./types";

export type RadarTask = TaskSummary<
  RadarRequest,
  RadarMetrics,
  RadarModelMetadata,
  RadarDiagnostics
>;

export interface RadarLayerPlan {
  taskId: string;
  request: RadarRequest;
  clipProfile: BeamClipProfile | null;
  coverageContractVersion: number;
  outputUrls: Record<string, string>;
}

export type RadarLayerKind = "voxel" | "clipped" | "height";

export interface RadarLayerAdapterDependencies<VoxelData, ClippedData, HeightData> {
  renderVolume(plan: RadarLayerPlan): void;
  removeVolume(): void;
  loadVoxel(plan: RadarLayerPlan): Promise<VoxelData>;
  renderVoxel(data: VoxelData, plan: RadarLayerPlan): void;
  removeVoxel(): void;
  loadClipped(plan: RadarLayerPlan): Promise<ClippedData>;
  renderClipped(data: ClippedData, plan: RadarLayerPlan): void;
  removeClipped(): void;
  loadHeightLayers(plan: RadarLayerPlan): Promise<HeightData>;
  renderHeightLayers(data: HeightData, plan: RadarLayerPlan): void;
  removeHeightLayers(): void;
}

export interface RadarLayerAdapter {
  readonly activeTaskId: string | null;
  readonly radarVisible: boolean;
  readonly errors: Partial<Record<RadarLayerKind, Error>>;
  showTask(task: RadarTask, demBounds: number[]): Promise<void>;
  setRadarVisible(visible: boolean): void;
  clear(): void;
  dispose(): void;
}

interface LayerCache<VoxelData, ClippedData, HeightData> {
  voxel?: VoxelData;
  clipped?: ClippedData;
  height?: HeightData;
  voxelPending?: PendingLoad;
  clippedPending?: PendingLoad;
  heightPending?: PendingLoad;
}

interface PendingLoad {
  version: number;
  promise: Promise<void>;
}

export function resolveRadarLayerPlan(
  task: RadarTask,
  demBounds: number[]
): RadarLayerPlan | null {
  if (task.status !== "finished" || !task.request) return null;

  const renderRangeM = resolveBeamRenderRange(
    task.request.coverage.max_range_m,
    task.model?.effective_max_range_m
  );
  const request = cloneRadarRequest(task.request, renderRangeM);
  const clipProfile = task.model?.beam_clip_profile
    ?? clipProfileFromBounds(demBounds, request.radar, renderRangeM);

  return {
    taskId: task.task_id,
    request,
    clipProfile,
    coverageContractVersion: task.model?.coverage_contract_version ?? 1,
    outputUrls: resolveOutputUrls(task)
  };
}

export function createRadarLayerAdapter<VoxelData, ClippedData, HeightData>(
  dependencies: RadarLayerAdapterDependencies<VoxelData, ClippedData, HeightData>
): RadarLayerAdapter {
  const cache = new Map<string, LayerCache<VoxelData, ClippedData, HeightData>>();
  const versions: Record<RadarLayerKind, number> = { voxel: 0, clipped: 0, height: 0 };
  let activePlan: RadarLayerPlan | null = null;
  let visible = true;
  let disposed = false;
  let layerErrors: Partial<Record<RadarLayerKind, Error>> = {};

  function invalidateLoads() {
    versions.voxel++;
    versions.clipped++;
    versions.height++;
  }

  function removeVisibleLayers() {
    dependencies.removeVolume();
    dependencies.removeVoxel();
    dependencies.removeClipped();
    dependencies.removeHeightLayers();
  }

  function renderCached(plan: RadarLayerPlan) {
    const entry = cache.get(plan.taskId);
    dependencies.renderVolume(plan);
    if (entry?.voxel !== undefined) dependencies.renderVoxel(entry.voxel, plan);
    if (entry?.clipped !== undefined) dependencies.renderClipped(entry.clipped, plan);
    if (entry?.height !== undefined) dependencies.renderHeightLayers(entry.height, plan);
  }

  function isCurrent(kind: RadarLayerKind, version: number, taskId: string) {
    return !disposed && versions[kind] === version && activePlan?.taskId === taskId;
  }

  function loadVoxel(plan: RadarLayerPlan, entry: LayerCache<VoxelData, ClippedData, HeightData>) {
    if (entry.voxel !== undefined) return undefined;
    const version = versions.voxel;
    if (entry.voxelPending?.version === version) return entry.voxelPending.promise;
    if (!plan.outputUrls.voxel_manifest_json || !plan.outputUrls.voxel_points_bin) return undefined;
    delete layerErrors.voxel;
    let pending!: Promise<void>;
    pending = (async () => {
      try {
        const data = await dependencies.loadVoxel(plan);
        if (!isCurrent("voxel", version, plan.taskId)) return;
        entry.voxel = data;
        if (visible) dependencies.renderVoxel(data, plan);
      } catch (error) {
        if (isCurrent("voxel", version, plan.taskId)) layerErrors.voxel = asError(error);
      } finally {
        if (entry.voxelPending?.promise === pending) delete entry.voxelPending;
      }
    })();
    entry.voxelPending = { version, promise: pending };
    return pending;
  }

  function loadClipped(plan: RadarLayerPlan, entry: LayerCache<VoxelData, ClippedData, HeightData>) {
    if (entry.clipped !== undefined) return undefined;
    const version = versions.clipped;
    if (entry.clippedPending?.version === version) return entry.clippedPending.promise;
    if (!plan.outputUrls.clipped_volume_manifest_json || !plan.outputUrls.clipped_volume_cells_bin) return undefined;
    delete layerErrors.clipped;
    let pending!: Promise<void>;
    pending = (async () => {
      try {
        const data = await dependencies.loadClipped(plan);
        if (!isCurrent("clipped", version, plan.taskId)) return;
        entry.clipped = data;
        if (visible) dependencies.renderClipped(data, plan);
      } catch (error) {
        if (isCurrent("clipped", version, plan.taskId)) layerErrors.clipped = asError(error);
      } finally {
        if (entry.clippedPending?.promise === pending) delete entry.clippedPending;
      }
    })();
    entry.clippedPending = { version, promise: pending };
    return pending;
  }

  function loadHeight(plan: RadarLayerPlan, entry: LayerCache<VoxelData, ClippedData, HeightData>) {
    if (entry.height !== undefined) return undefined;
    const version = versions.height;
    if (entry.heightPending?.version === version) return entry.heightPending.promise;
    if (!plan.outputUrls.height_layers_manifest_json) return undefined;
    delete layerErrors.height;
    let pending!: Promise<void>;
    pending = (async () => {
      try {
        const data = await dependencies.loadHeightLayers(plan);
        if (!isCurrent("height", version, plan.taskId)) return;
        entry.height = data;
        if (visible) dependencies.renderHeightLayers(data, plan);
      } catch (error) {
        if (isCurrent("height", version, plan.taskId)) layerErrors.height = asError(error);
      } finally {
        if (entry.heightPending?.promise === pending) delete entry.heightPending;
      }
    })();
    entry.heightPending = { version, promise: pending };
    return pending;
  }

  async function showTask(task: RadarTask, demBounds: number[]) {
    if (disposed) return;
    const plan = resolveRadarLayerPlan(task, demBounds);
    if (!plan) {
      clear();
      return;
    }

    const previousPlan = activePlan;
    const planChanged = !previousPlan || !areRadarLayerPlansEqual(previousPlan, plan);
    if (planChanged) {
      invalidateLoads();
      removeVisibleLayers();
      layerErrors = {};
      if (previousPlan?.taskId === plan.taskId) cache.delete(plan.taskId);
    }
    activePlan = plan;
    const entry = cache.get(plan.taskId) ?? {};
    cache.set(plan.taskId, entry);

    if (visible && planChanged) renderCached(plan);
    await Promise.all([
      loadVoxel(plan, entry),
      loadClipped(plan, entry),
      loadHeight(plan, entry)
    ]);
  }

  function setRadarVisible(nextVisible: boolean) {
    if (disposed || visible === nextVisible) return;
    visible = nextVisible;
    if (!visible) {
      removeVisibleLayers();
    } else if (activePlan) {
      renderCached(activePlan);
    }
  }

  function clear() {
    if (disposed) return;
    invalidateLoads();
    activePlan = null;
    layerErrors = {};
    removeVisibleLayers();
  }

  function dispose() {
    if (disposed) return;
    clear();
    cache.clear();
    disposed = true;
  }

  return {
    get activeTaskId() {
      return activePlan?.taskId ?? null;
    },
    get radarVisible() {
      return visible;
    },
    get errors() {
      return { ...layerErrors };
    },
    showTask,
    setRadarVisible,
    clear,
    dispose
  };
}

function areRadarLayerPlansEqual(left: RadarLayerPlan, right: RadarLayerPlan) {
  return left.taskId === right.taskId
    && left.coverageContractVersion === right.coverageContractVersion
    && JSON.stringify(left.request) === JSON.stringify(right.request)
    && JSON.stringify(left.clipProfile) === JSON.stringify(right.clipProfile)
    && JSON.stringify(left.outputUrls) === JSON.stringify(right.outputUrls);
}

function cloneRadarRequest(source: RadarRequest, maxRangeM: number): RadarRequest {
  return {
    dem_id: source.dem_id,
    radar: { ...source.radar },
    target: { ...source.target },
    coverage: { ...source.coverage, max_range_m: maxRangeM },
    advanced: {
      ...source.advanced,
      height_layers_m: [...source.advanced.height_layers_m]
    },
    reserved_radar_params: source.reserved_radar_params
      ? { ...source.reserved_radar_params }
      : undefined
  };
}

function resolveOutputUrls(task: RadarTask): Record<string, string> {
  return Object.fromEntries(
    task.output_files
      .filter((file) => file.exists && (file.download_url || file.url))
      .map((file) => [file.kind, file.download_url || file.url])
  );
}

function asError(error: unknown) {
  return error instanceof Error ? error : new Error(String(error));
}
