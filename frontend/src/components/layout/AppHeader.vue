<template>
  <header class="app-header">
    <div class="app-header__identity">
      <strong>PyGeoModel</strong>
      <span>GIS Workbench</span>
    </div>

    <div class="app-header__context">
      <span class="app-header__dem" :title="demLabel">
        <ElIcon aria-hidden="true"><MapLocation /></ElIcon>
        <span>{{ demLabel }}</span>
      </span>
      <span
        class="app-header__connection"
        :data-status="connected ? 'connected' : 'offline'"
        role="status"
      >
        <i aria-hidden="true"></i>
        {{ connected ? "Connected" : "Offline" }}
      </span>
    </div>

    <div class="app-header__actions" aria-label="Workspace controls">
      <ElTooltip content="Toggle parameters" placement="bottom" :show-after="300">
        <button
          type="button"
          class="icon-button"
          aria-label="Toggle parameters"
          aria-controls="workspace-parameters"
          :aria-expanded="parametersOpen"
          data-action="toggle-parameters"
          @click="emit('toggle-parameters')"
        >
          <ElIcon><Operation /></ElIcon>
        </button>
      </ElTooltip>
      <ElTooltip content="Task history" placement="bottom" :show-after="300">
        <button
          type="button"
          class="icon-button"
          aria-label="Open task history"
          data-action="open-history"
          @click="emit('open-history')"
        >
          <ElIcon><Clock /></ElIcon>
        </button>
      </ElTooltip>
      <ElTooltip content="Toggle results" placement="bottom" :show-after="300">
        <button
          type="button"
          class="icon-button"
          aria-label="Toggle results"
          aria-controls="workspace-results"
          :aria-expanded="resultsOpen"
          data-action="toggle-results"
          @click="emit('toggle-results')"
        >
          <ElIcon><DataAnalysis /></ElIcon>
        </button>
      </ElTooltip>
    </div>
  </header>
</template>

<script setup lang="ts">
import { Clock, DataAnalysis, MapLocation, Operation } from "@element-plus/icons-vue";
import { ElIcon, ElTooltip } from "element-plus";

withDefaults(defineProps<{
  demLabel?: string;
  connected?: boolean;
  parametersOpen?: boolean;
  resultsOpen?: boolean;
}>(), {
  demLabel: "No DEM selected",
  connected: true,
  parametersOpen: false,
  resultsOpen: false
});

const emit = defineEmits<{
  "open-history": [];
  "toggle-parameters": [];
  "toggle-results": [];
}>();
</script>
