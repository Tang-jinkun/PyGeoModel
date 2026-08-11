<template>
  <section class="map-pick-bar" data-map-pick-bar role="toolbar" :aria-label="`Picking ${targetLabel}`">
    <span>Picking {{ targetLabel }}</span>
    <div>
      <button v-if="target === 'route'" type="button" data-action="undo-map-pick" @click="emit('undo')"><ElIcon><RefreshLeft /></ElIcon></button>
      <button v-if="target === 'route'" type="button" data-action="finish-map-pick" @click="emit('finish')"><ElIcon><Check /></ElIcon></button>
      <button type="button" data-action="cancel-map-pick" @click="emit('cancel')"><ElIcon><Close /></ElIcon></button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Check, Close, RefreshLeft } from "@element-plus/icons-vue";
import { ElIcon } from "element-plus";
import { computed } from "vue";

import type { MapPickTarget } from "../../map/mapPickPolicy";

const props = defineProps<{ target: MapPickTarget }>();
const emit = defineEmits<{ cancel: []; undo: []; finish: [] }>();
const targetLabel = computed(() => ({ point: "location", target: "target", route: "route", start: "start", end: "end", threat: "threat" }[props.target]));
</script>

<style scoped>
.map-pick-bar{position:absolute;z-index:4;top:12px;left:50%;display:flex;min-width:260px;align-items:center;justify-content:space-between;gap:14px;padding:6px 8px 6px 12px;border:1px solid var(--wb-border);border-radius:8px;background:#fff;color:var(--wb-fg);box-shadow:0 8px 24px rgb(0 0 0 / 14%);font-size:13px;font-weight:600;transform:translateX(-50%)}.map-pick-bar>div{display:flex;gap:3px}.map-pick-bar button{display:grid;width:28px;height:28px;place-items:center;border:0;border-radius:5px;background:transparent;color:var(--wb-fg-2);cursor:pointer}.map-pick-bar button:hover{background:var(--wb-surface)}
</style>
