<template>
  <section v-if="availableLayers.length" class="radar-layer-controls" aria-label="Radar 3D layers">
    <header>Radar layers</header>
    <label v-for="layer in availableLayers" :key="layer.kind" class="radar-layer-row">
      <input
        type="checkbox"
        :checked="layer.visible"
        :data-layer-visible="layer.kind"
        :aria-label="`Show ${layer.label}`"
        @change="updateVisibility(layer.kind, $event)"
      />
      <i :style="{ backgroundColor: layer.color }" aria-hidden="true"></i>
      <span>{{ layer.label }}</span>
      <input
        type="range"
        min="0"
        max="1"
        step="0.05"
        :value="layer.opacity"
        :data-layer-opacity="layer.kind"
        :aria-label="`${layer.label} opacity`"
        @input="updateOpacity(layer.kind, $event)"
      />
    </label>
    <label v-if="heightOptions.length" class="radar-height-select">
      <span>Height layer</span>
      <select data-height-select :value="selectedHeightM ?? ''" @change="selectHeight">
        <option v-for="option in heightOptions" :key="option.heightM" :value="option.heightM">
          {{ option.label }}
        </option>
      </select>
    </label>
  </section>
</template>

<script setup lang="ts">
import { computed } from "vue";

export type RadarControlKind = "volume" | "boundary" | "clipped" | "voxel" | "height";
export interface RadarControlLayer {
  kind: RadarControlKind;
  label: string;
  color: string;
  visible: boolean;
  opacity: number;
  available: boolean;
}
export interface RadarHeightOption { heightM: number; label: string }

const props = defineProps<{
  layers: RadarControlLayer[];
  heightOptions: RadarHeightOption[];
  selectedHeightM: number | null;
}>();
const emit = defineEmits<{
  "update-layer": [kind: RadarControlKind, patch: { visible?: boolean; opacity?: number }];
  "select-height": [heightM: number];
}>();
const availableLayers = computed(() => props.layers.filter(({ available }) => available));

function updateVisibility(kind: RadarControlKind, event: Event) {
  emit("update-layer", kind, { visible: (event.target as HTMLInputElement).checked });
}

function updateOpacity(kind: RadarControlKind, event: Event) {
  emit("update-layer", kind, { opacity: Number((event.target as HTMLInputElement).value) });
}

function selectHeight(event: Event) {
  emit("select-height", Number((event.target as HTMLSelectElement).value));
}
</script>

<style scoped>
.radar-layer-controls { position:absolute; z-index:4; top:10px; left:10px; display:grid; width:260px; overflow:hidden; color:#303133; background:#fff; border:1px solid #dcdfe6; border-radius:6px; box-shadow:0 2px 8px rgb(0 0 0 / 14%); }.radar-layer-controls header { padding:8px 10px; border-bottom:1px solid #ebeef5; font-size:13px; font-weight:700; }.radar-layer-row { display:grid; grid-template-columns:16px 10px minmax(0,1fr) 72px; align-items:center; gap:7px; min-height:34px; padding:5px 10px; border-bottom:1px solid #f0f2f5; font-size:13px; }.radar-layer-row i { width:10px; height:10px; border-radius:2px; }.radar-layer-row input[type="range"] { width:72px; margin:0; accent-color:#2563eb; }.radar-layer-row input[type="checkbox"] { width:14px; height:14px; margin:0; accent-color:#2563eb; }.radar-height-select { display:grid; grid-template-columns:auto minmax(0,1fr); align-items:center; gap:8px; padding:7px 10px; font-size:13px; }.radar-height-select select { min-width:0; height:28px; padding:0 6px; background:#fff; border:1px solid #dcdfe6; border-radius:4px; } @media(max-width:600px){.radar-layer-controls{width:min(240px,calc(100% - 20px));}.radar-layer-row{grid-template-columns:16px 10px minmax(0,1fr) 64px}.radar-layer-row input[type="range"]{width:64px}}
</style>
