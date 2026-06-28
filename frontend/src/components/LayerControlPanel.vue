<template>
  <section v-if="availableLayers.length" class="layer-panel">
    <header class="layer-panel-header">
      <strong>图层</strong>
      <button class="link-button" type="button" @click="$emit('focusResult')">定位结果</button>
    </header>

    <div class="layer-list">
      <article v-for="layer in availableLayers" :key="layer.key" class="layer-item">
        <div class="layer-main">
          <span class="layer-swatch" :style="{ backgroundColor: layer.color }"></span>
          <div>
            <strong>{{ layer.label }}</strong>
            <span>{{ layer.description }}</span>
          </div>
          <el-switch
            :model-value="layer.visible"
            size="small"
            @update:model-value="(value: boolean) => updateLayer(layer.key, { visible: value })"
          />
        </div>
        <el-slider
          :model-value="Math.round(layer.opacity * 100)"
          :min="0"
          :max="80"
          :step="5"
          :show-tooltip="false"
          size="small"
          @input="(value: number | number[]) => updateLayer(layer.key, { opacity: sliderValue(value) / 100 })"
        />
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from "vue";

import type { ResultLayerKey } from "../map/mapLayers";

interface LayerControlState {
  key: ResultLayerKey;
  label: string;
  description: string;
  color: string;
  visible: boolean;
  opacity: number;
  available: boolean;
}

const props = defineProps<{
  layers: LayerControlState[];
}>();

const emit = defineEmits<{
  updateLayer: [key: ResultLayerKey, patch: Partial<Pick<LayerControlState, "visible" | "opacity">>];
  focusResult: [];
}>();

const availableLayers = computed(() => props.layers.filter((layer) => layer.available));

function updateLayer(key: ResultLayerKey, patch: Partial<Pick<LayerControlState, "visible" | "opacity">>) {
  emit("updateLayer", key, patch);
}

function sliderValue(value: number | number[]) {
  return Array.isArray(value) ? value[0] : value;
}
</script>
