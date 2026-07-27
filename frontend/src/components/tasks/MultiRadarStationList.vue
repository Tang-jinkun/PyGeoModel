<template>
  <section class="multi-radar-stations">
    <div class="multi-radar-stations__filters">
      <input v-model="query" data-station-search type="search" placeholder="Search stations" aria-label="Search stations">
      <select v-model="status" aria-label="Filter station status">
        <option value="all">All</option>
        <option value="finished">Finished</option>
        <option value="failed">Failed</option>
      </select>
    </div>
    <ul>
      <li v-for="station in filteredStations" :key="station.radar_id" :data-station-id="station.radar_id">
        <button type="button" class="multi-radar-stations__focus" :aria-label="`Focus ${label(station)}`" @click="emit('focus', station.radar_id)">
          {{ label(station) }}
        </button>
        <span :data-status="station.status">{{ station.status }}</span>
        <button
          type="button"
          :aria-label="`${detailedStationIds.includes(station.radar_id) ? 'Hide' : 'Show'} ${label(station)} detail`"
          @click="toggleDetail(station.radar_id)"
        >
          {{ detailedStationIds.includes(station.radar_id) ? "Hide scan" : "Show scan" }}
        </button>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";

import type { MultiRadarStationSummary } from "../../models/multiRadar/types";

const props = defineProps<{
  stations: MultiRadarStationSummary[];
  detailedStationIds: string[];
}>();
const emit = defineEmits<{
  focus: [radarId: string];
  "show-detail": [radarId: string];
  "hide-detail": [radarId: string];
}>();
const query = ref("");
const status = ref<"all" | "finished" | "failed">("all");
const filteredStations = computed(() => {
  const needle = query.value.trim().toLowerCase();
  return props.stations.filter((station) => {
    const matchesQuery = !needle || `${station.radar_id} ${station.name ?? ""}`.toLowerCase().includes(needle);
    return matchesQuery && (status.value === "all" || station.status === status.value);
  });
});

function label(station: MultiRadarStationSummary) {
  return station.name || station.radar_id;
}

function toggleDetail(radarId: string) {
  if (props.detailedStationIds.includes(radarId)) emit("hide-detail", radarId);
  else emit("show-detail", radarId);
}
</script>

<style scoped>
.multi-radar-stations { display: grid; gap: 8px; min-width: 0; }
.multi-radar-stations__filters { display: grid; grid-template-columns: minmax(0, 1fr) 96px; gap: 6px; }
.multi-radar-stations input, .multi-radar-stations select { min-width: 0; height: 30px; border: 1px solid #cbd5e1; border-radius: 4px; padding: 0 8px; font: inherit; }
.multi-radar-stations ul { display: grid; gap: 4px; margin: 0; padding: 0; list-style: none; max-height: 260px; overflow: auto; }
.multi-radar-stations li { display: grid; grid-template-columns: minmax(0, 1fr) 54px 66px; align-items: center; gap: 6px; min-height: 34px; padding: 0 4px; border-bottom: 1px solid #e2e8f0; }
.multi-radar-stations button { min-width: 0; border: 0; background: transparent; color: #2563eb; cursor: pointer; font: inherit; text-align: left; }
.multi-radar-stations li > button:last-child { text-align: right; }
.multi-radar-stations span { color: #64748b; font-size: 11px; }
.multi-radar-stations span[data-status="failed"] { color: #dc2626; }
</style>
