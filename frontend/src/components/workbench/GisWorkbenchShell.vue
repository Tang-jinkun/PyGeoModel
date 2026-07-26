<template>
  <main class="gis-workbench" :data-tasks-collapsed="collapsed">
    <header class="gis-workbench__topbar panel" data-workbench-region="topbar">
      <slot name="topbar" />
    </header>
    <aside class="gis-workbench__dock panel" data-workbench-region="dock">
      <slot name="dock" />
    </aside>
    <section class="gis-workbench__map" data-workbench-region="map">
      <slot name="map" />
    </section>
    <section class="gis-workbench__tasks panel" data-workbench-region="tasks">
      <div class="gis-workbench__task-command">
        <button
          type="button"
          class="gis-workbench__collapse"
          :aria-label="collapsed ? 'Expand task center' : 'Collapse task center'"
          @click="toggleTasks"
        >
          <ElIcon aria-hidden="true"><ArrowDown /></ElIcon>
        </button>
      </div>
      <slot name="tasks" :collapsed="collapsed" />
    </section>
    <footer class="gis-workbench__status panel" data-workbench-region="status">
      <slot name="status" />
    </footer>
  </main>
</template>

<script setup lang="ts">
import { ArrowDown } from "@element-plus/icons-vue";
import { ElIcon } from "element-plus";
import { computed, getCurrentInstance, ref } from "vue";

const props = defineProps<{
  tasksCollapsed?: boolean;
}>();

const emit = defineEmits<{
  "update:tasksCollapsed": [collapsed: boolean];
}>();

const localCollapsed = ref(false);
const vnodeProps = getCurrentInstance()?.vnode.props ?? {};
const isControlled = "tasksCollapsed" in vnodeProps || "tasks-collapsed" in vnodeProps;
const collapsed = computed(() => isControlled ? props.tasksCollapsed : localCollapsed.value);

function toggleTasks() {
  const next = !collapsed.value;
  if (!isControlled) localCollapsed.value = next;
  emit("update:tasksCollapsed", next);
}
</script>

<style scoped>
:global(:root) {
  --wb-bg: #ffffff;
  --wb-surface: #f5f5f7;
  --wb-surface-warm: #fbfbfd;
  --wb-fg: #1d1d1f;
  --wb-fg-2: #424245;
  --wb-muted: #6e6e73;
  --wb-meta: #86868b;
  --wb-border: #d2d2d7;
  --wb-border-soft: #e8e8ed;
  --wb-accent: #0071e3;
  --wb-radius-sm: 8px;
  --wb-radius-md: 12px;
  --wb-elev-ring: 0 0 0 1px var(--wb-border);
}

.gis-workbench {
  display: grid;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  gap: 8px;
  padding: 8px;
  overflow: hidden;
  background: var(--wb-surface);
  grid-template-areas:
    "top top top"
    "dock map"
    "tasks tasks"
    "status status";
  grid-template-columns: 292px minmax(360px, 1fr);
  grid-template-rows: 52px minmax(0, 1fr) auto 26px;
}

.gis-workbench[data-tasks-collapsed="true"] {
  grid-template-rows: 52px minmax(0, 1fr) 38px 26px;
}

.panel {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  background: var(--wb-bg);
  border-radius: var(--wb-radius-md);
  box-shadow: var(--wb-elev-ring);
}

.gis-workbench__topbar { grid-area: top; }
.gis-workbench__dock { grid-area: dock; }
.gis-workbench__map { grid-area: map; min-width: 0; min-height: 0; overflow: hidden; border-radius: var(--wb-radius-md); box-shadow: var(--wb-elev-ring); }
.gis-workbench__tasks { position: relative; grid-area: tasks; }
.gis-workbench__status { grid-area: status; }

.gis-workbench__task-command {
  position: absolute;
  z-index: 3;
  top: 3px;
  right: 8px;
}

.gis-workbench__collapse {
  display: grid;
  width: 32px;
  height: 32px;
  padding: 0;
  place-items: center;
  color: var(--wb-muted);
  background: transparent;
  border: 0;
  border-radius: var(--wb-radius-sm);
  cursor: pointer;
}

.gis-workbench__collapse:hover { color: var(--wb-fg); background: var(--wb-surface); }
.gis-workbench[data-tasks-collapsed="true"] .gis-workbench__collapse :deep(.el-icon) { transform: rotate(180deg); }

@media (max-width: 1279px) {
  .gis-workbench { grid-template-columns: 252px minmax(320px, 1fr); }
}

@media (max-width: 820px) {
  .gis-workbench {
    grid-template-areas:
      "top"
      "map"
      "tasks"
      "status";
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: 52px minmax(0, 1fr) auto 26px;
  }

  .gis-workbench__dock { display: none; }
}
</style>
