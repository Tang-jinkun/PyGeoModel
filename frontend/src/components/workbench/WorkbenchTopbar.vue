<template>
  <div class="workbench-topbar">
    <div class="workbench-topbar__brand">
      <strong>PyGeoModel</strong>
      <span>地理分析工作台</span>
    </div>
    <div class="workbench-topbar__project">
      <span>/</span>
      <span>综合地理分析</span>
    </div>
    <div class="workbench-topbar__search">
      <input
        :value="search"
        type="search"
        placeholder="搜索模型、任务或数据"
        aria-label="Global search"
        @input="emitSearch"
      >
    </div>
    <div class="workbench-topbar__actions">
      <span class="workbench-topbar__chip">
        <ElIcon><Picture /></ElIcon>{{ demLabel }}
      </span>
      <span class="workbench-topbar__chip">
        <i :data-connected="connected" />{{ connected ? "服务已连接" : "服务连接中断" }}
      </span>
      <ElTooltip content="设置" placement="bottom" :show-after="300">
        <button type="button" aria-label="Settings"><ElIcon><Setting /></ElIcon></button>
      </ElTooltip>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Picture, Setting } from "@element-plus/icons-vue";
import { ElIcon, ElTooltip } from "element-plus";

defineProps<{
  demLabel: string;
  connected: boolean;
  search: string;
}>();

const emit = defineEmits<{
  "update:search": [query: string];
}>();

function emitSearch(event: Event) {
  emit("update:search", (event.target as HTMLInputElement).value);
}
</script>

<style scoped>
.workbench-topbar { display: flex; min-width: 0; height: 100%; align-items: center; gap: 20px; padding: 0 12px 0 16px; color: var(--wb-fg); }
.workbench-topbar__brand, .workbench-topbar__project, .workbench-topbar__actions, .workbench-topbar__chip { display: flex; align-items: center; }
.workbench-topbar__brand { gap: 8px; white-space: nowrap; }
.workbench-topbar__brand strong { font-family: "SF Pro Display", "Helvetica Neue", Arial, sans-serif; font-size: 17px; font-weight: 600; }
.workbench-topbar__brand span { color: var(--wb-muted); font-size: 12px; }
.workbench-topbar__project { gap: 8px; color: var(--wb-fg-2); font-size: 14px; white-space: nowrap; }
.workbench-topbar__project span:first-child { color: var(--wb-border); }
.workbench-topbar__search { display: flex; flex: 1; min-width: 0; justify-content: center; }
.workbench-topbar__search input { width: min(380px, 100%); height: 32px; padding: 0 16px; color: var(--wb-fg); background: var(--wb-surface); border: 1px solid var(--wb-border-soft); border-radius: 980px; outline: 0; }
.workbench-topbar__search input:focus { background: var(--wb-bg); border-color: var(--wb-accent); box-shadow: 0 0 0 4px rgb(0 113 227 / 25%); }
.workbench-topbar__actions { flex: none; gap: 8px; }
.workbench-topbar__chip { max-width: 220px; height: 28px; gap: 6px; padding: 0 12px; overflow: hidden; color: var(--wb-fg-2); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; background: var(--wb-surface); border-radius: 980px; }
.workbench-topbar__chip .el-icon { flex: none; }
.workbench-topbar__chip i { width: 7px; height: 7px; flex: none; background: #dc2626; border-radius: 50%; }
.workbench-topbar__chip i[data-connected="true"] { background: #16a34a; }
.workbench-topbar__actions button { display: grid; width: 32px; height: 32px; padding: 0; place-items: center; color: var(--wb-muted); background: transparent; border: 0; border-radius: 8px; cursor: pointer; }
.workbench-topbar__actions button:hover { color: var(--wb-fg); background: var(--wb-surface); }
@media (max-width: 1279px) { .workbench-topbar__project { display: none; } }
@media (max-width: 820px) { .workbench-topbar { gap: 8px; } .workbench-topbar__brand span, .workbench-topbar__actions .workbench-topbar__chip { display: none; } }
</style>
