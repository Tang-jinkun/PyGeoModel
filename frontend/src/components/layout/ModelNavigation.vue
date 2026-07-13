<template>
  <nav class="model-navigation" aria-label="Analysis models">
    <ElTooltip
      v-for="modelId in MODEL_IDS"
      :key="modelId"
      :content="MODEL_REGISTRY[modelId].label"
      placement="right"
      :show-after="300"
    >
      <button
        type="button"
        class="model-navigation__item"
        :class="{ 'is-active': modelId === modelValue }"
        :aria-label="MODEL_REGISTRY[modelId].label"
        :aria-current="modelId === modelValue ? 'page' : undefined"
        :data-model-id="modelId"
        @click="emit('update:modelValue', modelId)"
      >
        <ElIcon class="model-navigation__icon" :size="20">
          <component :is="MODEL_ICONS[modelId]" />
        </ElIcon>
        <span class="model-navigation__label">{{ MODEL_REGISTRY[modelId].label }}</span>
      </button>
    </ElTooltip>
  </nav>
</template>

<script setup lang="ts">
import {
  Aim,
  Compass,
  Guide,
  Location,
  Position,
  Van,
  View
} from "@element-plus/icons-vue";
import { ElIcon, ElTooltip } from "element-plus";
import type { Component } from "vue";

import { MODEL_IDS, MODEL_REGISTRY, type ModelId } from "../../models/registry";

defineProps<{
  modelValue: ModelId;
}>();

const emit = defineEmits<{
  "update:modelValue": [modelId: ModelId];
}>();

const MODEL_ICONS: Record<ModelId, Component> = {
  radar: Aim,
  uav: Position,
  watchpost: View,
  artillery: Location,
  reconVehicle: Van,
  mobility: Guide,
  airCorridor: Compass
};
</script>
