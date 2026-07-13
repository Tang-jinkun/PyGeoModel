import { computed, reactive, ref, toRaw } from "vue";

import { getModelDefinition, MODEL_IDS, type ModelId, type ModelRequestMap } from "../models/registry";

export type ModelDrafts = { [K in ModelId]: ModelRequestMap[K] };

function cloneRequest<Request>(request: Request): Request {
  return structuredClone(toRaw(request));
}

function createDrafts(): ModelDrafts {
  const drafts = {} as ModelDrafts;
  for (const modelId of MODEL_IDS) {
    Reflect.set(drafts, modelId, getModelDefinition(modelId).createDefaultRequest());
  }
  return drafts;
}

export function useModelWorkspace(initialModel: ModelId = "radar") {
  const drafts = reactive(createDrafts()) as ModelDrafts;
  const selectedModel = ref<ModelId>(initialModel);
  const currentDraft = computed<ModelRequestMap[ModelId]>({
    get: () => drafts[selectedModel.value],
    set: (request) => {
      Reflect.set(drafts, selectedModel.value, cloneRequest(request));
    }
  });

  function selectModel(modelId: ModelId) {
    selectedModel.value = modelId;
  }

  function setDemForAll(demId: string | null) {
    for (const modelId of MODEL_IDS) drafts[modelId].dem_id = demId ?? "";
  }

  function restoreRequest<K extends ModelId>(modelId: K, request: ModelRequestMap[K]) {
    Reflect.set(drafts, modelId, cloneRequest(request));
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
