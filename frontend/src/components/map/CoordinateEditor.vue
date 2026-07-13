<template>
  <section class="coordinate-editor" :aria-label="label">
    <span class="coordinate-editor__label">{{ label }}</span>
    <label>
      <span>Longitude</span>
      <input
        data-field="longitude"
        type="number"
        min="-180"
        max="180"
        step="any"
        :value="modelValue?.[0] ?? ''"
        @input="updateCoordinate(0, $event)"
      />
    </label>
    <label>
      <span>Latitude</span>
      <input
        data-field="latitude"
        type="number"
        min="-90"
        max="90"
        step="any"
        :value="modelValue?.[1] ?? ''"
        @input="updateCoordinate(1, $event)"
      />
    </label>
    <div v-if="editing" class="spatial-editor-toolbar" role="toolbar" aria-label="Coordinate editing commands">
      <ElTooltip content="Finish editing" :show-after="300">
        <ElButton circle :icon="Check" data-action="finish-editing" aria-label="Finish editing" @click="emit('finish')" />
      </ElTooltip>
      <ElTooltip content="Undo edit" :show-after="300">
        <ElButton circle :icon="RefreshLeft" data-action="undo-editing" aria-label="Undo edit" @click="emit('undo')" />
      </ElTooltip>
      <ElTooltip content="Clear coordinate" :show-after="300">
        <ElButton circle :icon="Delete" data-action="clear-editing" aria-label="Clear coordinate" @click="clear" />
      </ElTooltip>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Check, Delete, RefreshLeft } from "@element-plus/icons-vue";
import { ElButton, ElTooltip } from "element-plus";

import type { SpatialCoordinate, SpatialDraftAction } from "../../map/spatialInput";

const props = withDefaults(defineProps<{
  modelValue: SpatialCoordinate | null;
  label?: string;
  editing?: boolean;
}>(), {
  label: "Coordinate",
  editing: false
});

const emit = defineEmits<{
  "update:modelValue": [coordinate: SpatialCoordinate | null];
  "spatial-edit": [action: SpatialDraftAction];
  finish: [];
  undo: [];
  clear: [];
}>();

function updateCoordinate(axis: 0 | 1, event: Event) {
  const value = Number((event.target as HTMLInputElement).value);
  const next: SpatialCoordinate = props.modelValue ? [...props.modelValue] : [0, 0];
  next[axis] = value;
  if (!isValidCoordinate(next)) return;
  emit("update:modelValue", next);
  emit("spatial-edit", { type: "set-point", coordinate: next });
}

function clear() {
  emit("update:modelValue", null);
  emit("clear");
}

function isValidCoordinate([longitude, latitude]: SpatialCoordinate) {
  return Number.isFinite(longitude) && longitude >= -180 && longitude <= 180
    && Number.isFinite(latitude) && latitude >= -90 && latitude <= 90;
}
</script>

<style scoped>
.coordinate-editor {
  display: grid;
  grid-template-columns: minmax(80px, auto) repeat(2, minmax(0, 1fr)) auto;
  align-items: end;
  gap: 8px;
  min-width: 0;
}

.coordinate-editor__label,
label span {
  color: #606266;
  font-size: 12px;
}

label {
  display: grid;
  gap: 4px;
  min-width: 0;
}

input {
  min-width: 0;
  height: 30px;
  box-sizing: border-box;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  padding: 0 8px;
}

.spatial-editor-toolbar {
  display: flex;
  gap: 4px;
}

@media (max-width: 600px) {
  .coordinate-editor {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }

  .coordinate-editor__label,
  .spatial-editor-toolbar {
    grid-column: 1 / -1;
  }
}
</style>
