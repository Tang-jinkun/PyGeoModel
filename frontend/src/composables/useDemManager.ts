import { ref } from "vue";

import { deleteDem, listDems, uploadDem, type DemMetadata } from "../api/dem";

export interface DemWorkspaceSync {
  setDemForAll(demId: string | null): void;
}

export function useDemManager(workspace: DemWorkspaceSync) {
  const dems = ref<DemMetadata[]>([]);
  const selectedDem = ref<string | null>(null);
  const loading = ref(false);
  const uploading = ref(false);
  let pendingLoads = 0;
  let pendingUploads = 0;
  let latestLoadGeneration = 0;
  let mutationGeneration = 0;
  let selectionGeneration = 0;

  async function load() {
    const loadGeneration = ++latestLoadGeneration;
    const mutationGenerationAtStart = mutationGeneration;
    pendingLoads++;
    loading.value = true;
    try {
      const loaded = await listDems();
      if (loadGeneration === latestLoadGeneration && mutationGenerationAtStart === mutationGeneration) {
        dems.value = loaded;
      }
      return loaded;
    } finally {
      pendingLoads--;
      loading.value = pendingLoads > 0;
    }
  }

  function select(demId: string | null) {
    selectionGeneration++;
    selectedDem.value = demId;
    workspace.setDemForAll(demId);
  }

  async function upload(file: File) {
    const selectionGenerationAtStart = selectionGeneration;
    pendingUploads++;
    uploading.value = true;
    try {
      const uploaded = await uploadDem(file);
      mutationGeneration++;
      const index = dems.value.findIndex(({ dem_id }) => dem_id === uploaded.dem_id);
      if (index === -1) dems.value = [...dems.value, uploaded];
      else dems.value.splice(index, 1, uploaded);
      if (selectionGenerationAtStart === selectionGeneration) select(uploaded.dem_id);
      return uploaded;
    } finally {
      pendingUploads--;
      uploading.value = pendingUploads > 0;
    }
  }

  async function remove(demId: string) {
    const result = await deleteDem(demId);
    if (!result.deleted) return result;

    mutationGeneration++;
    dems.value = dems.value.filter(({ dem_id }) => dem_id !== demId);
    if (selectedDem.value === demId) select(null);
    return result;
  }

  return {
    dems,
    selectedDem,
    loading,
    uploading,
    load,
    select,
    upload,
    remove
  };
}
