<template>
  <section class="model-input-slots" aria-label="Input data">
    <label v-for="slot in slots" :key="slot.key" class="input-slot" :data-input-slot="slot.key">
      <span>{{ slot.label }}<em v-if="slot.required">*</em></span>
      <select
        :multiple="slot.multiple"
        :value="selections[slot.key] ?? []"
        @change="updateSlot(slot, $event)"
      >
        <option v-if="!slot.multiple" value="">Select a file</option>
        <option v-for="asset in compatibleAssets(slot)" :key="asset.dem_id" :value="asset.dem_id">{{ asset.filename }}</option>
      </select>
      <small v-if="showValidation && slot.required && !(selections[slot.key]?.length)">Required</small>
    </label>
  </section>
</template>

<script setup lang="ts">
import type { InputSlotDefinition, ModelInputSelections } from "../../models/inputSlots";

type Asset = { dem_id: string; filename: string };

const props = defineProps<{
  slots: readonly InputSlotDefinition[];
  selections: ModelInputSelections;
  assets: readonly Asset[];
  showValidation: boolean;
}>();
const emit = defineEmits<{ "update:selections": [selections: ModelInputSelections] }>();

function compatibleAssets(slot: InputSlotDefinition) {
  return slot.assetTypes.includes("dem") ? props.assets : [];
}

function updateSlot(slot: InputSlotDefinition, event: Event) {
  const selected = Array.from((event.target as HTMLSelectElement).selectedOptions, (option) => option.value)
    .filter(Boolean);
  emit("update:selections", {
    ...props.selections,
    [slot.key]: slot.multiple ? selected : selected.slice(0, 1)
  });
}
</script>

<style scoped>
.model-input-slots{display:grid;gap:12px}.input-slot{display:grid;gap:6px;color:var(--wb-fg-2);font-size:13px}.input-slot>span{display:flex;gap:3px;align-items:center}.input-slot em{color:#d73545;font-style:normal}.input-slot select{width:100%;height:34px;padding:0 9px;border:1px solid var(--wb-border);border-radius:6px;background:#fff;color:var(--wb-fg);font:inherit}.input-slot select[multiple]{height:88px;padding:5px}.input-slot small{color:#c33030;font-size:12px}
</style>
