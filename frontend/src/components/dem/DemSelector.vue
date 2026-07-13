<template>
  <section class="dem-selector" aria-label="Digital elevation models" :aria-busy="loading || uploading">
    <div class="dem-selector__commands">
      <label class="dem-selector__label" for="dem-selector-current">Active DEM</label>
      <select
        id="dem-selector-current"
        class="dem-selector__select"
        :value="modelValue ?? ''"
        :disabled="loading"
        @change="selectFromControl"
      >
        <option value="">No DEM selected</option>
        <option v-for="dem in dems" :key="dem.dem_id" :value="dem.dem_id">
          {{ dem.filename }}
        </option>
      </select>

      <input
        ref="fileInput"
        class="dem-selector__file-input"
        type="file"
        accept=".tif,.tiff,image/tiff"
        aria-label="Upload DEM file"
        @change="handleFile"
      />
      <ElTooltip content="Upload DEM" :show-after="300">
        <ElButton
          circle
          :icon="Upload"
          :loading="uploading"
          aria-label="Upload DEM"
          @click="fileInput?.click()"
        />
      </ElTooltip>
      <ElTooltip content="Refresh DEMs" :show-after="300">
        <ElButton
          circle
          :icon="Refresh"
          :loading="loading"
          data-action="refresh-dems"
          aria-label="Refresh DEMs"
          @click="emit('refresh')"
        />
      </ElTooltip>
    </div>

    <p v-if="!loading && dems.length === 0" class="dem-selector__empty">No DEMs uploaded</p>
    <ul v-else class="dem-selector__list" aria-label="Available DEMs">
      <li v-for="dem in dems" :key="dem.dem_id" class="dem-selector__item">
        <button
          type="button"
          class="dem-selector__details"
          :class="{ 'is-selected': dem.dem_id === modelValue }"
          :data-dem-id="dem.dem_id"
          :aria-pressed="dem.dem_id === modelValue"
          @click="emit('update:modelValue', dem.dem_id)"
        >
          <span class="dem-selector__filename">{{ dem.filename }}</span>
          <span class="dem-selector__metadata">
            {{ dem.crs }} | {{ dem.resolution.join(" x ") }} | {{ dem.active_task_count }} active task{{ dem.active_task_count === 1 ? "" : "s" }}
          </span>
        </button>
        <ElPopconfirm
          title="Delete this DEM?"
          confirm-button-text="Delete"
          @confirm="emit('delete', dem.dem_id)"
        >
          <template #reference>
            <ElTooltip content="Delete DEM" :show-after="300">
              <ElButton
                circle
                :icon="Delete"
                aria-label="Delete DEM"
                @click.stop
              />
            </ElTooltip>
          </template>
        </ElPopconfirm>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import { Delete, Refresh, Upload } from "@element-plus/icons-vue";
import { ElButton, ElPopconfirm, ElTooltip } from "element-plus";
import { ref } from "vue";

import type { DemMetadata } from "../../api/dem";

defineProps<{
  dems: DemMetadata[];
  modelValue: string | null;
  loading: boolean;
  uploading: boolean;
}>();

const emit = defineEmits<{
  "update:modelValue": [demId: string | null];
  upload: [file: File];
  delete: [demId: string];
  refresh: [];
}>();

const fileInput = ref<HTMLInputElement | null>(null);

function selectFromControl(event: Event) {
  const demId = (event.target as HTMLSelectElement).value;
  emit("update:modelValue", demId || null);
}

function handleFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const [file] = Array.from(input.files ?? []);
  if (file) emit("upload", file);
  input.value = "";
}
</script>

<style scoped>
.dem-selector {
  display: grid;
  gap: 8px;
  min-width: 0;
}

.dem-selector__commands {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 6px;
}

.dem-selector__label,
.dem-selector__metadata,
.dem-selector__empty {
  color: #606266;
  font-size: 12px;
}

.dem-selector__select {
  min-width: 0;
  min-height: 32px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  background: #ffffff;
  color: #303133;
  padding: 0 8px;
}

.dem-selector__file-input {
  display: none;
}

.dem-selector__empty {
  margin: 0;
  padding: 6px 0;
}

.dem-selector__list {
  display: grid;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.dem-selector__item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 4px;
  border-top: 1px solid #ebeef5;
  padding: 4px 0;
}

.dem-selector__details {
  display: grid;
  min-width: 0;
  gap: 2px;
  border: 0;
  background: transparent;
  color: #303133;
  padding: 2px 4px;
  text-align: left;
}

.dem-selector__details:hover,
.dem-selector__details:focus-visible,
.dem-selector__details.is-selected {
  background: #ecf5ff;
}

.dem-selector__filename,
.dem-selector__metadata {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dem-selector__filename {
  font-size: 13px;
}
</style>
