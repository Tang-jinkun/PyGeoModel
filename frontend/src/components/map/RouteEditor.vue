<template>
  <section class="route-editor" aria-label="Route waypoints">
    <ol class="route-editor__list">
      <li v-for="(point, index) in modelValue" :key="index" :data-waypoint="index">
        <span class="route-editor__index">{{ index + 1 }}</span>
        <input
          data-field="longitude"
          aria-label="Waypoint longitude"
          type="number"
          min="-180"
          max="180"
          step="any"
          :value="point[0]"
          @input="move(index, 0, $event)"
        />
        <input
          data-field="latitude"
          aria-label="Waypoint latitude"
          type="number"
          min="-90"
          max="90"
          step="any"
          :value="point[1]"
          @input="move(index, 1, $event)"
        />
        <ElTooltip content="Remove waypoint" :show-after="300">
          <ElButton
            circle
            :icon="Delete"
            :data-action="`remove-waypoint-${index}`"
            :aria-label="`Remove waypoint ${index + 1}`"
            @click="remove(index)"
          />
        </ElTooltip>
      </li>
    </ol>
    <div v-if="editing" class="spatial-editor-toolbar" role="toolbar" aria-label="Route editing commands">
      <ElTooltip content="Finish editing" :show-after="300">
        <ElButton circle :icon="Check" data-action="finish-editing" aria-label="Finish editing" @click="emit('finish')" />
      </ElTooltip>
      <ElTooltip content="Undo edit" :show-after="300">
        <ElButton circle :icon="RefreshLeft" data-action="undo-editing" aria-label="Undo edit" @click="emit('undo')" />
      </ElTooltip>
      <ElTooltip content="Clear route" :show-after="300">
        <ElButton circle :icon="Delete" data-action="clear-editing" aria-label="Clear route" @click="emit('clear')" />
      </ElTooltip>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Check, Delete, RefreshLeft } from "@element-plus/icons-vue";
import { ElButton, ElTooltip } from "element-plus";

import type { SpatialCoordinate, SpatialDraftAction } from "../../map/spatialInput";

const props = withDefaults(defineProps<{
  modelValue: SpatialCoordinate[];
  editing?: boolean;
}>(), { editing: false });

const emit = defineEmits<{
  "update:modelValue": [points: SpatialCoordinate[]];
  "spatial-edit": [action: SpatialDraftAction];
  finish: [];
  undo: [];
  clear: [];
}>();

function move(index: number, axis: 0 | 1, event: Event) {
  const coordinate: SpatialCoordinate = [...props.modelValue[index]];
  coordinate[axis] = Number((event.target as HTMLInputElement).value);
  if (!isValidCoordinate(coordinate)) return;
  const points = props.modelValue.map((point, pointIndex) => (
    pointIndex === index ? coordinate : [...point] as SpatialCoordinate
  ));
  emit("update:modelValue", points);
  emit("spatial-edit", { type: "move", index, coordinate });
}

function remove(index: number) {
  emit("update:modelValue", props.modelValue.filter((_, pointIndex) => pointIndex !== index).map((point) => [...point]));
  emit("spatial-edit", { type: "remove", index });
}

function isValidCoordinate([longitude, latitude]: SpatialCoordinate) {
  return Number.isFinite(longitude) && longitude >= -180 && longitude <= 180
    && Number.isFinite(latitude) && latitude >= -90 && latitude <= 90;
}
</script>

<style scoped>
.route-editor {
  display: grid;
  gap: 8px;
}

.route-editor__list {
  display: grid;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.route-editor__list li {
  display: grid;
  grid-template-columns: 24px repeat(2, minmax(0, 1fr)) 32px;
  align-items: center;
  gap: 6px;
}

.route-editor__index {
  color: #606266;
  font-size: 12px;
  text-align: center;
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
