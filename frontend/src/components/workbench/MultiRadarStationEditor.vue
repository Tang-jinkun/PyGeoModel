<template>
  <section class="multi-radar-station-editor" data-multi-radar-editor>
    <div class="multi-radar-station-editor__mode" role="radiogroup" aria-label="Multi-radar presentation mode">
      <label><input :checked="presentationMode === 'aggregate'" type="radio" value="aggregate" @change="emit('update:presentationMode', 'aggregate')"><span>Aggregate coverage</span></label>
      <label><input :checked="presentationMode === 'cooperative_3d'" type="radio" value="cooperative_3d" @change="emit('update:presentationMode', 'cooperative_3d')"><span>Cooperative 3D</span></label>
    </div>

    <article v-for="(station, index) in stations" :key="station.radar_id" class="station-editor-row" :data-station-id="station.radar_id">
      <header><strong>Station {{ index + 1 }}</strong><button type="button" :aria-label="`Remove ${station.radar_id}`" @click="removeStation(index)"><ElIcon><Delete /></ElIcon></button></header>
      <div class="station-editor-row__fields">
        <label><span>Radar ID</span><input :value="station.radar_id" @input="updateText(index, 'radar_id', $event)"></label>
        <label><span>Name</span><input :value="station.name ?? ''" @input="updateText(index, 'name', $event)"></label>
        <label><span>Longitude</span><input type="number" :value="station.radar.lon" @input="updateNumber(index, 'radar.lon', $event)"></label>
        <label><span>Latitude</span><input type="number" :value="station.radar.lat" @input="updateNumber(index, 'radar.lat', $event)"></label>
        <label><span>Radar height</span><input type="number" :value="station.radar.height_m" @input="updateNumber(index, 'radar.height_m', $event)"></label>
        <label><span>Target height</span><input type="number" :value="station.target?.height_m ?? 0" @input="updateNumber(index, 'target.height_m', $event)"></label>
        <label><span>Max range</span><input type="number" :value="station.coverage.max_range_m" @input="updateNumber(index, 'coverage.max_range_m', $event)"></label>
      </div>
    </article>

    <button type="button" class="add-station" @click="addStation"><ElIcon><Plus /></ElIcon><span>Add station</span></button>
    <p v-if="showValidation && validationMessages.length" class="station-editor-validation" role="alert">{{ validationMessages.join(' ') }}</p>
  </section>
</template>

<script setup lang="ts">
import { Delete, Plus } from "@element-plus/icons-vue";
import { ElIcon } from "element-plus";
import { computed, toRaw } from "vue";

import type { MultiRadarStationInput } from "../../models/multiRadar/types";

type PresentationMode = "aggregate" | "cooperative_3d";

const props = defineProps<{
  stations: MultiRadarStationInput[];
  presentationMode: PresentationMode;
  showValidation: boolean;
}>();
const emit = defineEmits<{
  "update:stations": [stations: MultiRadarStationInput[]];
  "update:presentationMode": [mode: PresentationMode];
}>();

const validationMessages = computed(() => validateStations(props.stations, props.presentationMode));
const isValid = computed(() => validationMessages.value.length === 0);

function updateText(index: number, path: "radar_id" | "name", event: Event) {
  const next = cloneStations();
  if (path === "radar_id") next[index].radar_id = (event.target as HTMLInputElement).value.trim();
  else next[index].name = (event.target as HTMLInputElement).value || null;
  emit("update:stations", next);
}

function updateNumber(index: number, path: string, event: Event) {
  const value = (event.target as HTMLInputElement).valueAsNumber;
  if (!Number.isFinite(value)) return;
  const station = cloneStations()[index];
  if (path === "radar.lon") station.radar.lon = value;
  else if (path === "radar.lat") station.radar.lat = value;
  else if (path === "radar.height_m") station.radar.height_m = value;
  else if (path === "target.height_m") station.target = { ...(station.target ?? { height_m: 0 }), height_m: value };
  else station.coverage.max_range_m = value;
  emit("update:stations", cloneStationsWith(station, index));
}

function addStation() {
  const next = cloneStations();
  const source = next.at(-1);
  if (!source) return;
  const id = nextStationId(next);
  next.push({
    ...source,
    radar_id: id,
    name: `Station ${id}`,
    radar: { ...source.radar },
    target: source.target ? { ...source.target } : undefined,
    coverage: { ...source.coverage },
    advanced: source.advanced ? structuredClone(source.advanced) : undefined,
    reserved_radar_params: source.reserved_radar_params ? structuredClone(source.reserved_radar_params) : undefined
  });
  emit("update:stations", next);
}

function removeStation(index: number) {
  emit("update:stations", cloneStations().filter((_, stationIndex) => stationIndex !== index));
}

function cloneStations() {
  return structuredClone(toRaw(props.stations));
}

function cloneStationsWith(station: MultiRadarStationInput, index: number) {
  const next = cloneStations();
  next[index] = station;
  return next;
}

function nextStationId(stations: MultiRadarStationInput[]) {
  let index = stations.length + 1;
  while (stations.some(({ radar_id }) => radar_id === `R${index}`)) index += 1;
  return `R${index}`;
}

function validateStations(stations: MultiRadarStationInput[], presentationMode: PresentationMode) {
  const issues: string[] = [];
  if (stations.length < 2) issues.push("Add at least two radar stations.");
  const ids = stations.map(({ radar_id }) => radar_id.trim()).filter(Boolean);
  if (ids.length !== stations.length || new Set(ids).size !== ids.length) issues.push("Radar IDs must be unique.");
  if (presentationMode === "cooperative_3d" && (stations.length < 3 || stations.length > 5)) {
    issues.push("Cooperative 3D requires three to five stations.");
  }
  return issues;
}

defineExpose({ isValid });
</script>

<style scoped>
.multi-radar-station-editor{display:grid;gap:12px;padding:4px 0}.multi-radar-station-editor__mode{display:flex;gap:4px}.multi-radar-station-editor__mode label{position:relative}.multi-radar-station-editor__mode input{position:absolute;opacity:0}.multi-radar-station-editor__mode span{display:block;padding:7px 10px;border:1px solid var(--wb-border);border-radius:6px;color:var(--wb-fg-2);font-size:12px;cursor:pointer}.multi-radar-station-editor__mode input:checked+span{border-color:var(--wb-accent);background:var(--wb-accent);color:#fff}.station-editor-row{border:1px solid var(--wb-border-soft);border-radius:6px;padding:10px}.station-editor-row header{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}.station-editor-row strong{font-size:13px}.station-editor-row header button{display:grid;width:28px;height:28px;place-items:center;border:0;border-radius:5px;background:transparent;color:var(--wb-muted);cursor:pointer}.station-editor-row__fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.station-editor-row__fields label{display:grid;gap:4px;color:var(--wb-fg-2);font-size:11px}.station-editor-row__fields input{width:100%;height:30px;padding:0 7px;border:1px solid var(--wb-border);border-radius:5px;background:#fff;color:var(--wb-fg);font:inherit}.add-station{display:flex;align-items:center;justify-content:center;gap:5px;min-height:34px;border:1px dashed var(--wb-border);border-radius:6px;background:var(--wb-surface);color:var(--wb-accent);font:inherit;font-size:13px;cursor:pointer}.station-editor-validation{margin:0;color:#c33030;font-size:12px;line-height:1.5}@media (max-width:560px){.station-editor-row__fields{grid-template-columns:1fr}}
</style>
