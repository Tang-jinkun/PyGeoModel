<template>
  <main class="workspace-shell">
    <div class="workspace-shell__header">
      <slot
        name="header"
        :parameters-open="openDrawer === 'parameters'"
        :results-open="openDrawer === 'results'"
        :open-history="openHistory"
        :toggle-parameters="toggleParameters"
        :toggle-results="toggleResults"
      >
        <AppHeader
          :dem-label="demLabel"
          :connected="connected"
          :parameters-open="openDrawer === 'parameters'"
          :results-open="openDrawer === 'results'"
          @open-history="openHistory"
          @toggle-parameters="toggleParameters"
          @toggle-results="toggleResults"
        />
      </slot>
    </div>

    <div class="workspace-shell__navigation">
      <slot name="navigation" :model-id="modelValue" :select-model="selectModel">
        <ModelNavigation :model-value="modelValue" @update:model-value="selectModel" />
      </slot>
    </div>

    <aside
      id="workspace-parameters"
      class="workspace-shell__parameters"
      data-region="parameters"
      :data-open="openDrawer === 'parameters'"
      aria-label="Model parameters"
    >
      <slot name="parameters"></slot>
    </aside>

    <section class="workspace-shell__map" aria-label="Map workspace">
      <slot name="map"></slot>
    </section>

    <aside
      id="workspace-results"
      class="workspace-shell__results"
      data-region="results"
      :data-open="openDrawer === 'results'"
      aria-label="Task results"
    >
      <slot name="results"></slot>
    </aside>

    <button
      v-if="openDrawer"
      type="button"
      class="workspace-shell__scrim"
      aria-label="Close open panel"
      @click="closeDrawers"
    ></button>
  </main>
</template>

<script setup lang="ts">
import { ref } from "vue";

import type { ModelId } from "../../models/registry";
import AppHeader from "./AppHeader.vue";
import ModelNavigation from "./ModelNavigation.vue";

withDefaults(defineProps<{
  modelValue?: ModelId;
  demLabel?: string;
  connected?: boolean;
}>(), {
  modelValue: "radar",
  demLabel: "No DEM selected",
  connected: true
});

const emit = defineEmits<{
  "select-model": [modelId: ModelId];
  "open-history": [];
  "toggle-parameters": [];
  "toggle-results": [];
}>();

const openDrawer = ref<"parameters" | "results" | null>(null);

function selectModel(modelId: ModelId) {
  emit("select-model", modelId);
}

function openHistory() {
  emit("open-history");
}

function toggleParameters() {
  openDrawer.value = openDrawer.value === "parameters" ? null : "parameters";
  emit("toggle-parameters");
}

function toggleResults() {
  openDrawer.value = openDrawer.value === "results" ? null : "results";
  emit("toggle-results");
}

function closeDrawers() {
  openDrawer.value = null;
}
</script>
