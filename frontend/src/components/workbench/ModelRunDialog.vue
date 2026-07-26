<template>
  <div v-if="open" class="model-run-dialog__backdrop" @mousedown.self="emit('update:open', false)">
    <section class="model-run-dialog" role="dialog" aria-modal="true" :aria-label="`${definition.label} configuration`" :data-model-run-dialog="modelId">
      <header>
        <div><span>Model configuration</span><h1>{{ definition.label }}</h1></div>
        <button type="button" aria-label="Close configuration" @click="emit('update:open', false)"><ElIcon><Close /></ElIcon></button>
      </header>
      <nav v-if="modelId === 'radar'" class="mode-tabs" role="tablist" aria-label="Radar analysis mode">
        <button type="button" data-radar-mode="single" role="tab" :aria-selected="radarMode === 'single'" @click="radarMode = 'single'">Single radar</button>
        <button type="button" data-radar-mode="multi" role="tab" :aria-selected="radarMode === 'multi'" @click="radarMode = 'multi'">Multi-radar</button>
      </nav>
      <div class="model-run-dialog__body">
        <details open><summary>Input data</summary><ModelInputSlots :slots="slots" :selections="inputs" :assets="assets" :show-validation="showValidation" @update:selections="emit('update:inputs', $event)" /></details>
        <details v-if="radarMode === 'single'" data-model-parameters open><summary>Spatial inputs and parameters</summary><ModelParameterFields :model-id="modelId" :model-value="request" @update:model-value="emit('update:request', $event)" @activate-map-tool="emit('activate-map-tool', $event)" /></details>
        <MultiRadarStationEditor
          v-else
          ref="stationEditor"
          :stations="multiStations"
          :presentation-mode="multiPresentationMode"
          :show-validation="showValidation"
          @update:stations="multiStations = $event"
          @update:presentation-mode="multiPresentationMode = $event"
        />
      </div>
      <footer>
        <button type="button" class="cancel" @click="emit('update:open', false)">Cancel</button>
        <button type="button" class="run" data-action="run-analysis" :disabled="submitting" @click="submit">{{ submitting ? "Running" : "Run analysis" }}</button>
      </footer>
    </section>
  </div>
</template>

<script setup lang="ts">
import { Close } from "@element-plus/icons-vue";
import { ElIcon } from "element-plus";
import { computed, ref, toRaw, watch } from "vue";

import { applyInputSelections, type InputSlotDefinition, type ModelInputSelections } from "../../models/inputSlots";
import { getModelDefinition, type ModelId } from "../../models/registry";
import type { MultiRadarStationInput } from "../../models/multiRadar/types";
import type { RadarRequest } from "../../models/radar/types";
import type { BaseModelRequest } from "../../models/shared";
import ModelInputSlots from "./ModelInputSlots.vue";
import ModelParameterFields from "./ModelParameterFields.vue";
import MultiRadarStationEditor from "./MultiRadarStationEditor.vue";

type MapTool = "point" | "route" | "start" | "end" | "threat";
type MultiRadarPresentationMode = "aggregate" | "cooperative_3d";
export type ModelRunSubmission =
  | { request: BaseModelRequest; inputs: ModelInputSelections; multiRadar?: never }
  | { inputs: ModelInputSelections; multiRadar: { stations: MultiRadarStationInput[]; presentationMode: MultiRadarPresentationMode } };

const props = defineProps<{ open: boolean; modelId: ModelId; request: BaseModelRequest; inputs: ModelInputSelections; slots: readonly InputSlotDefinition[]; assets: readonly { dem_id: string; filename: string }[]; submitting: boolean }>();
const emit = defineEmits<{ "update:open": [open: boolean]; "update:request": [request: BaseModelRequest]; "update:inputs": [inputs: ModelInputSelections]; "activate-map-tool": [tool: MapTool]; submit: [submission: ModelRunSubmission] }>();
const showValidation = ref(false);
const definition = computed(() => getModelDefinition(props.modelId));
const radarMode = ref<"single" | "multi">("single");
const multiStations = ref<MultiRadarStationInput[]>(defaultStations());
const multiPresentationMode = ref<MultiRadarPresentationMode>("aggregate");
const stationEditor = ref<InstanceType<typeof MultiRadarStationEditor> | null>(null);

watch(() => props.open, (open, wasOpen) => {
  if (open && !wasOpen) {
    radarMode.value = "single";
    showValidation.value = false;
  }
});

function submit() {
  showValidation.value = true;
  if (props.slots.some((slot) => slot.required && !props.inputs[slot.key]?.length)) return;
  if (props.modelId === "radar" && radarMode.value === "multi") {
    if (!stationEditor.value?.isValid) return;
    emit("submit", {
      inputs: props.inputs,
      multiRadar: {
        stations: structuredClone(toRaw(multiStations.value)),
        presentationMode: multiPresentationMode.value
      }
    });
    return;
  }
  emit("submit", { request: applyInputSelections(props.request, props.inputs), inputs: props.inputs });
}

function defaultStations(): MultiRadarStationInput[] {
  const request = getModelDefinition("radar").createDefaultRequest();
  return [createStation(request, "R1", 0, 0), createStation(request, "R2", 0.08, 0.05)];
}

function createStation(request: RadarRequest, radarId: string, longitudeOffset: number, latitudeOffset: number): MultiRadarStationInput {
  const source = structuredClone(request);
  return {
    radar_id: radarId,
    name: `Station ${radarId}`,
    radar: { ...source.radar, lon: source.radar.lon + longitudeOffset, lat: source.radar.lat + latitudeOffset },
    target: { ...source.target },
    coverage: { ...source.coverage },
    advanced: source.advanced,
    reserved_radar_params: source.reserved_radar_params
  };
}
</script>

<style scoped>
.model-run-dialog__backdrop{position:fixed;z-index:20;inset:0;display:grid;place-items:center;padding:24px;background:rgb(20 24 31 / 34%)}.model-run-dialog{display:grid;width:min(760px,100%);max-height:min(760px,calc(100vh - 48px));grid-template-rows:auto auto minmax(0,1fr) auto;border:1px solid var(--wb-border);border-radius:8px;background:#fff;box-shadow:0 24px 64px rgb(0 0 0 / 22%)}header{display:flex;align-items:flex-start;justify-content:space-between;padding:20px 22px;border-bottom:1px solid var(--wb-border-soft)}header span{color:var(--wb-meta);font-size:12px}h1{margin:3px 0 0;color:var(--wb-fg);font-size:20px;letter-spacing:0}header button{display:grid;width:32px;height:32px;place-items:center;border:0;border-radius:6px;background:transparent;color:var(--wb-fg-2);cursor:pointer}.mode-tabs{display:flex;gap:18px;padding:0 22px;border-bottom:1px solid var(--wb-border-soft)}.mode-tabs button{height:38px;padding:0;border:0;border-bottom:2px solid transparent;background:transparent;color:var(--wb-muted);font:inherit;font-size:13px;cursor:pointer}.mode-tabs button[aria-selected="true"]{border-bottom-color:var(--wb-accent);color:var(--wb-accent);font-weight:600}.model-run-dialog__body{overflow:auto;padding:8px 22px 18px}.model-run-dialog__body>details{padding:12px 0;border-bottom:1px solid var(--wb-border-soft)}.model-run-dialog__body summary{padding:5px 0 12px;color:var(--wb-fg);font-size:14px;font-weight:600;list-style:none}.model-run-dialog__body summary::before{display:inline-block;margin-right:6px;color:var(--wb-meta);content:">";transform:rotate(90deg)}footer{display:flex;justify-content:flex-end;gap:8px;padding:14px 22px;border-top:1px solid var(--wb-border-soft)}footer button{height:36px;padding:0 16px;border-radius:6px;font-weight:600;cursor:pointer}.cancel{border:1px solid var(--wb-border);background:#fff;color:var(--wb-fg-2)}.run{border:1px solid var(--wb-accent);background:var(--wb-accent);color:#fff}.run:disabled{cursor:wait;opacity:.6}
</style>
