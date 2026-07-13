import { ref } from "vue";

import { deleteDem, listDems, uploadDem, type DemMetadata } from "../api/dem";

export function useDemManager() {
  const dems = ref<DemMetadata[]>([]);
  const selectedDem = ref<string | null>(null);
  const loading = ref(false);
  const uploading = ref(false);

  async function load() {
    loading.value = true;
    try {
      dems.value = await listDems();
    } finally {
      loading.value = false;
    }
  }

  function select(demId: string | null) {
    selectedDem.value = demId;
  }

  async function upload(file: File) {
    uploading.value = true;
    try {
      const uploaded = await uploadDem(file);
      const index = dems.value.findIndex(({ dem_id }) => dem_id === uploaded.dem_id);
      if (index === -1) dems.value = [...dems.value, uploaded];
      else dems.value.splice(index, 1, uploaded);
      return uploaded;
    } finally {
      uploading.value = false;
    }
  }

  async function remove(demId: string) {
    const result = await deleteDem(demId);
    if (!result.deleted) return result;

    dems.value = dems.value.filter(({ dem_id }) => dem_id !== demId);
    if (selectedDem.value === demId) selectedDem.value = null;
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
