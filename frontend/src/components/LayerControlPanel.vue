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
        <el-select
          v-if="layer.key === 'heightLayer' && heightLayers.length"
          :model-value="selectedHeightM"
          size="small"
          placeholder="选择高度层"
          @change="(value: number) => $emit('selectHeightLayer', value)"
        >
          <el-option
            v-for="item in heightLayers"
            :key="item.heightM"
            :label="item.label"
            :value="item.heightM"
          />
        </el-select>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from "vue";

interface LayerControlState {
  key: string;
  label: string;
  description: string;
  color: string;
  visible: boolean;
  opacity: number;
  available: boolean;
}

interface HeightLayerState {
  heightM: number;
  label: string;
}

const props = defineProps<{
  layers: LayerControlState[];
  heightLayers?: HeightLayerState[];
  selectedHeightM?: number | null;
}>();

const emit = defineEmits<{
  updateLayer: [key: string, patch: Partial<Pick<LayerControlState, "visible" | "opacity">>];
  selectHeightLayer: [heightM: number];
  focusResult: [];
}>();

const availableLayers = computed(() => props.layers.filter((layer) => layer.available));
const heightLayers = computed(() => props.heightLayers ?? []);
const selectedHeightM = computed(() => props.selectedHeightM ?? null);

function updateLayer(key: string, patch: Partial<Pick<LayerControlState, "visible" | "opacity">>) {
  emit("updateLayer", key, patch);
}

function sliderValue(value: number | number[]) {
  return Array.isArray(value) ? value[0] : value;
}
</script>
