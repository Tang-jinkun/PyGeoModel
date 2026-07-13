<template>
  <section class="threat-editor" aria-label="Threat coordinates">
    <ul class="threat-editor__list">
      <li v-for="threat in modelValue" :key="threat.id" :data-threat="threat.id">
        <span class="threat-editor__name">{{ threat.properties?.name ?? threat.id }}</span>
        <input
          data-field="longitude"
          aria-label="Threat longitude"
          type="number"
          min="-180"
          max="180"
          step="any"
          :value="threat.coordinate[0]"
          @input="update(threat.id, 0, $event)"
        />
        <input
          data-field="latitude"
          aria-label="Threat latitude"
          type="number"
          min="-90"
          max="90"
          step="any"
          :value="threat.coordinate[1]"
          @input="update(threat.id, 1, $event)"
        />
        <ElTooltip content="Remove threat" :show-after="300">
          <ElButton
            circle
            :icon="Delete"
            :data-action="`remove-threat-${threat.id}`"
            :aria-label="`Remove threat ${threat.id}`"
            @click="remove(threat.id)"
          />
        </ElTooltip>
      </li>
    </ul>
    <div v-if="editing" class="spatial-editor-toolbar" role="toolbar" aria-label="Threat editing commands">
      <ElTooltip content="Finish editing" :show-after="300">
        <ElButton circle :icon="Check" data-action="finish-editing" aria-label="Finish editing" @click="emit('finish')" />
      </ElTooltip>
      <ElTooltip content="Undo edit" :show-after="300">
        <ElButton circle :icon="RefreshLeft" data-action="undo-editing" aria-label="Undo edit" @click="emit('undo')" />
      </ElTooltip>
      <ElTooltip content="Clear threats" :show-after="300">
        <ElButton circle :icon="Delete" data-action="clear-editing" aria-label="Clear threats" @click="emit('clear')" />
      </ElTooltip>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Check, Delete, RefreshLeft } from "@element-plus/icons-vue";
import { ElButton, ElTooltip } from "element-plus";
import { toRaw } from "vue";

import type { SpatialCoordinate, SpatialDraftAction, SpatialThreat } from "../../map/spatialInput";

const props = withDefaults(defineProps<{
  modelValue: SpatialThreat[];
  editing?: boolean;
}>(), { editing: false });

const emit = defineEmits<{
  "update:modelValue": [threats: SpatialThreat[]];
  "spatial-edit": [action: SpatialDraftAction];
  finish: [];
  undo: [];
  clear: [];
}>();

function update(id: string, axis: 0 | 1, event: Event) {
  const threat = props.modelValue.find((candidate) => candidate.id === id);
  if (!threat) return;
  const coordinate: SpatialCoordinate = [...threat.coordinate];
  coordinate[axis] = Number((event.target as HTMLInputElement).value);
  if (!isValidCoordinate(coordinate)) return;
  emit("update:modelValue", props.modelValue.map((candidate) => ({
    ...candidate,
    coordinate: candidate.id === id ? coordinate : [...candidate.coordinate],
    properties: candidate.properties === undefined ? undefined : structuredClone(toRaw(candidate.properties))
  })));
  emit("spatial-edit", { type: "update-threat", id, coordinate });
}

function remove(id: string) {
  emit("update:modelValue", props.modelValue.filter((threat) => threat.id !== id).map((threat) => ({
    ...threat,
    coordinate: [...threat.coordinate],
    properties: threat.properties === undefined ? undefined : structuredClone(toRaw(threat.properties))
  })));
  emit("spatial-edit", { type: "remove-threat", id });
}

function isValidCoordinate([longitude, latitude]: SpatialCoordinate) {
  return Number.isFinite(longitude) && longitude >= -180 && longitude <= 180
    && Number.isFinite(latitude) && latitude >= -90 && latitude <= 90;
}
</script>

<style scoped>
.threat-editor {
  display: grid;
  gap: 8px;
}

.threat-editor__list {
  display: grid;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.threat-editor__list li {
  display: grid;
  grid-template-columns: minmax(70px, auto) repeat(2, minmax(0, 1fr)) 32px;
  align-items: center;
  gap: 6px;
}

.threat-editor__name {
  min-width: 0;
  overflow: hidden;
  color: #606266;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
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
</style>
