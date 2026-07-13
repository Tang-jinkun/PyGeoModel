<template>
  <main
    class="workspace-shell"
    :data-parameters-open="effectiveParametersOpen"
    :data-results-open="effectiveResultsOpen"
  >
    <div class="workspace-shell__header">
      <slot
        name="header"
        :parameters-open="effectiveParametersOpen"
        :results-open="effectiveResultsOpen"
        :open-history="openHistory"
        :toggle-parameters="toggleParameters"
        :toggle-results="toggleResults"
      >
        <AppHeader
          :dem-label="demLabel"
          :connected="connected"
          :parameters-open="effectiveParametersOpen"
          :results-open="effectiveResultsOpen"
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
      :data-open="effectiveParametersOpen"
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
      :data-open="effectiveResultsOpen"
      aria-label="Task results"
    >
      <slot name="results"></slot>
    </aside>

    <button
      v-if="isNarrow && activeDrawer"
      type="button"
      class="workspace-shell__scrim"
      aria-label="Close open panel"
      @click="closeActiveDrawer"
    ></button>
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

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

defineSlots<{
  header(props: {
    parametersOpen: boolean;
    resultsOpen: boolean;
    openHistory: () => void;
    toggleParameters: () => void;
    toggleResults: () => void;
  }): unknown;
  navigation(props: {
    modelId: ModelId;
    selectModel: (modelId: ModelId) => void;
  }): unknown;
  parameters(): unknown;
  map(): unknown;
  results(): unknown;
}>();

const parametersOpen = ref(true);
const resultsOpen = ref(true);
const activeDrawer = ref<"parameters" | "results" | null>(null);
const isNarrow = ref(false);
const effectiveParametersOpen = computed(() => (
  isNarrow.value ? activeDrawer.value === "parameters" : parametersOpen.value
));
const effectiveResultsOpen = computed(() => (
  isNarrow.value ? activeDrawer.value === "results" : resultsOpen.value
));
let narrowMediaQuery: MediaQueryList | null = null;

onMounted(() => {
  if (typeof window === "undefined" || !window.matchMedia) return;

  narrowMediaQuery = window.matchMedia("(max-width: 800px)");
  isNarrow.value = narrowMediaQuery.matches;
  narrowMediaQuery.addEventListener("change", handleNarrowChange);
});

onBeforeUnmount(() => {
  narrowMediaQuery?.removeEventListener("change", handleNarrowChange);
});

function selectModel(modelId: ModelId) {
  emit("select-model", modelId);
}

function openHistory() {
  emit("open-history");
}

function toggleParameters() {
  if (isNarrow.value) {
    activeDrawer.value = activeDrawer.value === "parameters" ? null : "parameters";
  } else {
    parametersOpen.value = !parametersOpen.value;
  }
  emit("toggle-parameters");
}

function toggleResults() {
  if (isNarrow.value) {
    activeDrawer.value = activeDrawer.value === "results" ? null : "results";
  } else {
    resultsOpen.value = !resultsOpen.value;
  }
  emit("toggle-results");
}

function closeActiveDrawer() {
  activeDrawer.value = null;
}

function handleNarrowChange(event: MediaQueryListEvent) {
  isNarrow.value = event.matches;
  if (!event.matches) activeDrawer.value = null;
}
</script>
