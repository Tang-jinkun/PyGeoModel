<template>
  <section class="multi-radar-panel">
    <header><span>Batch coverage</span><strong>{{ task?.status ?? "idle" }}</strong></header>
    <div class="multi-radar-panel__modes" role="radiogroup" aria-label="Batch presentation mode">
      <label>
        <input v-model="presentationMode" data-presentation-mode="cooperative_3d" type="radio" value="cooperative_3d">
        Cooperative 3D
      </label>
      <label>
        <input v-model="presentationMode" data-presentation-mode="aggregate" type="radio" value="aggregate">
        Aggregate
      </label>
    </div>
    <textarea v-model="radarsJson" aria-label="Radar object array" spellcheck="false" />
    <button type="button" :disabled="submitting || !demId" @click="submit">Run batch</button>
    <MultiRadarStationList
      v-if="task"
      :stations="task.stations"
      :detailed-station-ids="detailedStationIds"
      @focus="emit('focus-station', $event)"
      @show-detail="showDetail"
      @hide-detail="emit('hide-detail', $event)"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";

import { createMultiRadarTask, getMultiRadarTask, requestMultiRadarDetail } from "../api/multiRadar";
import type { CoverageTaskStatus } from "../api/radar";
import type { MultiRadarStationInput, MultiRadarTask, MultiRadarRequest } from "../models/multiRadar/types";
import MultiRadarStationList from "./tasks/MultiRadarStationList.vue";

const props = defineProps<{ demId: string; detailedStationIds: string[] }>();
const emit = defineEmits<{
  "show-aggregate": [task: MultiRadarTask];
  "show-detail": [stationId: string, task: CoverageTaskStatus | null];
  "hide-detail": [stationId: string];
  "focus-station": [stationId: string];
  error: [error: unknown];
}>();
const task = ref<MultiRadarTask | null>(null);
const submitting = ref(false);
const radarsJson = ref("[]");
const presentationMode = ref<NonNullable<MultiRadarRequest["presentation_mode"]>>("cooperative_3d");
let pollTimer: number | null = null;

watch(task, (next) => {
  if (next && (next.status === "finished" || next.status === "partial")) emit("show-aggregate", next);
  if (!next || ["finished", "partial", "failed"].includes(next.status)) stopPolling();
});
onBeforeUnmount(stopPolling);

async function submit() {
  try {
    const parsed = JSON.parse(radarsJson.value) as MultiRadarStationInput[];
    if (!Array.isArray(parsed) || parsed.length < 2) throw new Error("Provide at least two radar objects.");
    if (presentationMode.value === "cooperative_3d" && (parsed.length < 3 || parsed.length > 5)) {
      throw new Error("Cooperative 3D requires three to five radar objects.");
    }
    submitting.value = true;
    task.value = await createMultiRadarTask({
      dem_id: props.demId,
      radars: parsed,
      presentation_mode: presentationMode.value
    });
    startPolling();
  } catch (error) {
    emit("error", error);
  } finally {
    submitting.value = false;
  }
}

function startPolling() {
  stopPolling();
  pollTimer = window.setInterval(async () => {
    if (!task.value) return;
    try { task.value = await getMultiRadarTask(task.value.task_id); }
    catch (error) { emit("error", error); stopPolling(); }
  }, 1000);
}

function stopPolling() {
  if (pollTimer != null) window.clearInterval(pollTimer);
  pollTimer = null;
}

async function showDetail(stationId: string) {
  if (!task.value) return;
  if (task.value.request?.presentation_mode === "cooperative_3d") {
    emit("show-detail", stationId, null);
    return;
  }
  try {
    const detailTask = await requestMultiRadarDetail(task.value.task_id, stationId);
    emit("show-detail", stationId, detailTask);
  } catch (error) {
    emit("error", error);
  }
}
</script>

<style scoped>
.multi-radar-panel { display: grid; gap: 8px; border-top: 1px solid #dbe3ec; padding-top: 12px; }
.multi-radar-panel header { display: flex; justify-content: space-between; font-size: 12px; color: #475569; }
.multi-radar-panel__modes { display: inline-flex; justify-self: start; overflow: hidden; border: 1px solid #cbd5e1; border-radius: 4px; }
.multi-radar-panel__modes label { display: grid; min-height: 28px; padding: 0 8px; place-items: center; color: #475569; cursor: pointer; font-size: 11px; }
.multi-radar-panel__modes label + label { border-left: 1px solid #cbd5e1; }
.multi-radar-panel__modes input { position: absolute; opacity: 0; pointer-events: none; }
.multi-radar-panel__modes label:has(input:checked) { color: #fff; background: #2563eb; }
.multi-radar-panel textarea { min-height: 84px; resize: vertical; border: 1px solid #cbd5e1; border-radius: 4px; padding: 8px; font: 11px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace; }
.multi-radar-panel > button { justify-self: start; min-height: 30px; border: 1px solid #2563eb; border-radius: 4px; background: #2563eb; color: #fff; padding: 0 10px; cursor: pointer; }
.multi-radar-panel > button:disabled { opacity: .55; cursor: not-allowed; }
</style>
