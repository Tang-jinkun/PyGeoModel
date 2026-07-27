<template>
  <section class="workbench-data-pane">
    <div class="data-actions">
      <label class="upload-btn"><input type="file" accept=".tif,.tiff" @change="chooseFile">导入 DEM</label>
      <button type="button" aria-label="刷新 DEM 列表" @click="emit('refresh')"><ElIcon><Refresh /></ElIcon></button>
    </div>
    <details open class="data-group">
      <summary>地形数据<span>{{ dems.length }}</span></summary>
      <div v-for="dem in dems" :key="dem.dem_id" class="dem-row" :class="{ 'is-selected': dem.dem_id === modelValue }" :data-dem-id="dem.dem_id" role="button" tabindex="0" @click="emit('update:modelValue', dem.dem_id)" @keydown.enter="emit('update:modelValue', dem.dem_id)">
        <ElIcon><FolderOpened /></ElIcon><span>{{ dem.filename }}</span><small v-if="dem.dem_id === modelValue">当前</small>
        <button type="button" aria-label="删除 DEM" @click.stop="emit('delete', dem.dem_id)"><ElIcon><Delete /></ElIcon></button>
      </div>
      <p v-if="!dems.length && !loading" class="empty-state">尚未导入 DEM</p>
      <p v-if="loading" class="empty-state">正在加载数据</p>
    </details>
  </section>
</template>

<script setup lang="ts">
import { Delete, FolderOpened, Refresh } from "@element-plus/icons-vue";
import { ElIcon } from "element-plus";

type DemRow = { dem_id: string; filename: string };
const props = defineProps<{ dems: DemRow[]; modelValue: string | null; loading: boolean; uploading: boolean }>();
const emit = defineEmits<{ "update:modelValue": [demId: string]; upload: [file: File]; delete: [demId: string]; refresh: [] }>();
function chooseFile(event: Event) { const file = (event.target as HTMLInputElement).files?.[0]; if (file) emit("upload", file); }
void props;
</script>

<style scoped>
.workbench-data-pane{padding:4px}.data-actions{display:flex;gap:8px;margin:4px 0 12px}.upload-btn,.data-actions>button{display:grid;height:32px;place-items:center;border:1px solid var(--wb-border);border-radius:8px;background:#fff;color:var(--wb-fg-2);font-size:12px;cursor:pointer}.upload-btn{padding:0 12px}.upload-btn input{position:absolute;width:1px;height:1px;opacity:0}.data-actions>button{width:32px}.data-group summary{display:flex;gap:6px;padding:8px 4px;color:var(--wb-fg-2);font-size:12px;font-weight:600;list-style:none}.data-group summary::before{content:">";color:var(--wb-meta);transform:rotate(90deg)}.data-group summary span{margin-left:auto;color:var(--wb-meta);font-weight:400}.dem-row{display:grid;width:100%;grid-template-columns:18px minmax(0,1fr) auto 24px;gap:8px;align-items:center;min-height:36px;padding:4px 6px 4px 18px;border:0;border-bottom:1px solid var(--wb-border-soft);background:transparent;color:var(--wb-fg);font:inherit;text-align:left;cursor:pointer}.dem-row:hover,.dem-row.is-selected{background:var(--wb-surface)}.dem-row.is-selected{color:var(--wb-accent);font-weight:600}.dem-row span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.dem-row small{color:var(--wb-meta);font-size:11px}.dem-row button{display:grid;width:24px;height:24px;place-items:center;border:0;border-radius:6px;background:transparent;color:var(--wb-meta)}.empty-state{margin:0;padding:20px 8px;color:var(--wb-meta);font-size:12px;text-align:center}
</style>
