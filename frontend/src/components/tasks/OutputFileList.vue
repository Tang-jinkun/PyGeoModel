<template>
  <p v-if="!files.length" class="output-file-list__empty">暂无输出文件</p>
  <ul v-else class="output-file-list">
    <li v-for="file in files" :key="`${file.kind}:${file.filename}`">
      <span>{{ file.label || file.filename }}</span>
      <a :href="file.download_url || file.url" download>
        <ElIcon><Download /></ElIcon>
        <span class="sr-only">下载{{ file.label || file.filename }}</span>
      </a>
    </li>
  </ul>
</template>

<script setup lang="ts">
import { Download } from "@element-plus/icons-vue";
import { ElIcon } from "element-plus";

import type { OutputFile } from "../../models/shared";

defineProps<{
  files: readonly OutputFile[];
}>();
</script>

<style scoped>
.output-file-list,
.output-file-list__empty {
  margin: 0;
}

.output-file-list__empty {
  color: #64748b;
  font-size: 12px;
}

.output-file-list {
  padding: 0;
  list-style: none;
}

.output-file-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 42px;
  border-bottom: 1px solid #e2e8f0;
  color: #334155;
  font-size: 12px;
}

.output-file-list li > span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.output-file-list a {
  display: grid;
  width: 28px;
  height: 28px;
  flex: 0 0 auto;
  place-items: center;
  color: #1d4ed8;
  border-radius: 4px;
}

.output-file-list a:hover {
  background: #eff6ff;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  clip-path: inset(50%);
}
</style>
