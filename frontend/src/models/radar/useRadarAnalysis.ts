import { readonly, ref, shallowRef } from "vue";

import {
  createFusionAnalysis,
  getCoverageProfile,
  type CoverageProfileResult,
  type FusionResult
} from "../../api/radar";
import type { TaskSummary } from "../shared";
import type {
  RadarDiagnostics,
  RadarMetrics,
  RadarModelMetadata,
  RadarRequest
} from "./types";

export type RadarAnalysisTask = TaskSummary<
  RadarRequest,
  RadarMetrics,
  RadarModelMetadata,
  RadarDiagnostics
>;

export interface RadarAnalysisProfileTarget {
  lon: number;
  lat: number;
  height_m: number;
}

export interface RadarProfileAnalysisState {
  task: RadarAnalysisTask;
  target: RadarAnalysisProfileTarget;
  result: CoverageProfileResult;
}

export interface RadarFusionAnalysisState {
  tasks: RadarAnalysisTask[];
  contractVersion: number;
  result: FusionResult;
}

export interface RadarAnalysisDeps {
  getProfile(taskId: string, lon: number, lat: number): Promise<CoverageProfileResult>;
  createFusion(taskIds: string[]): Promise<FusionResult>;
}

const defaultDeps: RadarAnalysisDeps = {
  getProfile: getCoverageProfile,
  createFusion: createFusionAnalysis
};

export function useRadarAnalysis(deps: RadarAnalysisDeps = defaultDeps) {
  const profile = shallowRef<RadarProfileAnalysisState | null>(null);
  const fusion = shallowRef<RadarFusionAnalysisState | null>(null);
  const profileLoading = ref(false);
  const fusionLoading = ref(false);
  const profileError = shallowRef<unknown>(null);
  const fusionError = shallowRef<unknown>(null);

  let disposed = false;
  let profileToken = 0;
  let fusionToken = 0;

  async function runProfile(
    task: RadarAnalysisTask,
    selectedTarget: Pick<RadarAnalysisProfileTarget, "lon" | "lat">
  ) {
    assertActive();
    if (task.status !== "finished") {
      throw assignProfileError(new Error("Profile analysis requires a finished radar task."));
    }
    if (!task.request) {
      throw assignProfileError(new Error("Profile analysis requires a stored radar request."));
    }

    const token = ++profileToken;
    profileLoading.value = true;
    profileError.value = null;

    const target: RadarAnalysisProfileTarget = {
      lon: selectedTarget.lon,
      lat: selectedTarget.lat,
      height_m: task.request.target.height_m
    };

    try {
      const result = await deps.getProfile(task.task_id, target.lon, target.lat);
      if (!disposed && token === profileToken) {
        profile.value = {
          task,
          target,
          result
        };
      }
      return result;
    } catch (error) {
      if (!disposed && token === profileToken) {
        profileError.value = error;
      }
      throw error;
    } finally {
      if (!disposed && token === profileToken) {
        profileLoading.value = false;
      }
    }
  }

  async function runFusion(tasks: RadarAnalysisTask[]) {
    assertActive();

    for (const task of tasks) {
      if (task.status !== "finished") {
        throw assignFusionError(new Error("Fusion analysis requires finished radar tasks only."));
      }
    }

    const uniqueTasks = uniqueByTaskId(tasks);
    if (uniqueTasks.length < 2) {
      throw assignFusionError(new Error("Fusion analysis requires at least two distinct finished radar tasks."));
    }

    const contractVersion = uniqueTasks[0].model?.coverage_contract_version ?? 1;
    const mixedContracts = uniqueTasks.some((task) => (task.model?.coverage_contract_version ?? 1) !== contractVersion);
    if (mixedContracts) {
      throw assignFusionError(new Error("Fusion analysis requires matching coverage contract versions."));
    }

    const token = ++fusionToken;
    fusionLoading.value = true;
    fusionError.value = null;

    try {
      const result = await deps.createFusion(uniqueTasks.map(({ task_id }) => task_id));
      if (!disposed && token === fusionToken) {
        fusion.value = {
          tasks: uniqueTasks,
          contractVersion,
          result
        };
      }
      return result;
    } catch (error) {
      if (!disposed && token === fusionToken) {
        fusionError.value = error;
      }
      throw error;
    } finally {
      if (!disposed && token === fusionToken) {
        fusionLoading.value = false;
      }
    }
  }

  function clearProfile() {
    profileToken++;
    profile.value = null;
    profileLoading.value = false;
    profileError.value = null;
  }

  function clearFusion() {
    fusionToken++;
    fusion.value = null;
    fusionLoading.value = false;
    fusionError.value = null;
  }

  function dispose() {
    if (disposed) {
      return;
    }
    disposed = true;
    clearProfile();
    clearFusion();
  }

  function assignProfileError(error: Error) {
    profileError.value = error;
    profileLoading.value = false;
    return error;
  }

  function assignFusionError(error: Error) {
    fusionError.value = error;
    fusionLoading.value = false;
    return error;
  }

  function assertActive() {
    if (disposed) {
      throw new Error("Radar analysis has been disposed.");
    }
  }

  return {
    profile: readonly(profile),
    fusion: readonly(fusion),
    profileLoading: readonly(profileLoading),
    fusionLoading: readonly(fusionLoading),
    profileError: readonly(profileError),
    fusionError: readonly(fusionError),
    runProfile,
    runFusion,
    clearProfile,
    clearFusion,
    dispose
  };
}

function uniqueByTaskId(tasks: RadarAnalysisTask[]) {
  const unique = new Map<string, RadarAnalysisTask>();
  for (const task of tasks) {
    if (!unique.has(task.task_id)) {
      unique.set(task.task_id, task);
    }
  }
  return [...unique.values()];
}
