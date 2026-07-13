import { computed, reactive, ref, toRaw } from "vue";

import { getModelDefinition, MODEL_IDS, type ModelId, type ModelRequestMap } from "../models/registry";

export type ModelDrafts = { [K in ModelId]: ModelRequestMap[K] };
export type ActiveDraft = {
  [K in ModelId]: { modelId: K; request: ModelRequestMap[K] };
}[ModelId];

function cloneRequest<Request>(request: Request): Request {
  return structuredClone(toRaw(request));
}

function createDrafts(): ModelDrafts {
  return {
    radar: getModelDefinition("radar").createDefaultRequest(),
    uav: getModelDefinition("uav").createDefaultRequest(),
    watchpost: getModelDefinition("watchpost").createDefaultRequest(),
    artillery: getModelDefinition("artillery").createDefaultRequest(),
    reconVehicle: getModelDefinition("reconVehicle").createDefaultRequest(),
    mobility: getModelDefinition("mobility").createDefaultRequest(),
    airCorridor: getModelDefinition("airCorridor").createDefaultRequest()
  };
}

export function useModelWorkspace(initialModel: ModelId = "radar") {
  const drafts = reactive(createDrafts());
  const selectedModel = ref<ModelId>(initialModel);
  const currentDraft = computed<ActiveDraft>({
    get: () => activeDraftFor(selectedModel.value, drafts),
    set: (draft) => {
      replaceActiveDraft(drafts, draft);
      selectedModel.value = draft.modelId;
    }
  });

  function selectModel(modelId: ModelId) {
    selectedModel.value = modelId;
  }

  function setDemForAll(demId: string | null) {
    for (const modelId of MODEL_IDS) drafts[modelId].dem_id = demId ?? "";
  }

  function restoreRequest<K extends ModelId>(modelId: K, request: ModelRequestMap[K]) {
    replaceDraft(drafts, modelId, request);
  }

  return {
    drafts,
    selectedModel,
    currentDraft,
    selectModel,
    setDemForAll,
    restoreRequest
  };
}

function activeDraftFor(modelId: ModelId, drafts: ModelDrafts): ActiveDraft {
  switch (modelId) {
    case "radar":
      return { modelId, request: drafts.radar };
    case "uav":
      return { modelId, request: drafts.uav };
    case "watchpost":
      return { modelId, request: drafts.watchpost };
    case "artillery":
      return { modelId, request: drafts.artillery };
    case "reconVehicle":
      return { modelId, request: drafts.reconVehicle };
    case "mobility":
      return { modelId, request: drafts.mobility };
    case "airCorridor":
      return { modelId, request: drafts.airCorridor };
  }
}

function replaceDraft<K extends ModelId>(drafts: ModelDrafts, modelId: K, request: ModelRequestMap[K]) {
  drafts[modelId] = cloneRequest(request);
}

function replaceActiveDraft(drafts: ModelDrafts, draft: ActiveDraft) {
  switch (draft.modelId) {
    case "radar":
      replaceDraft(drafts, "radar", draft.request);
      return;
    case "uav":
      replaceDraft(drafts, "uav", draft.request);
      return;
    case "watchpost":
      replaceDraft(drafts, "watchpost", draft.request);
      return;
    case "artillery":
      replaceDraft(drafts, "artillery", draft.request);
      return;
    case "reconVehicle":
      replaceDraft(drafts, "reconVehicle", draft.request);
      return;
    case "mobility":
      replaceDraft(drafts, "mobility", draft.request);
      return;
    case "airCorridor":
      replaceDraft(drafts, "airCorridor", draft.request);
      return;
  }
}
