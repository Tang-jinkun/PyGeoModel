<template>
  <div
    class="scene-glb-row"
    data-scene-glb-row
    :data-scene-glb-kind="file.kind"
    :title="`任务 ${state.taskId}`"
  >
    <span class="scene-glb-row__swatch" aria-hidden="true" />
    <div class="scene-glb-row__identity">
      <strong>{{ file.label }}</strong>
      <span :data-state="state.status">任务 {{ shortTaskId }} · {{ stateText }}</span>
    </div>
    <ElSwitch
      data-scene-glb-toggle
      :model-value="switchOn"
      :disabled="previewTooLarge"
      :aria-label="`显示${file.label}`"
      @change="emit('visibility', Boolean($event))"
    />
    <ElTooltip content="定位三维结果" placement="top" :show-after="300">
      <button
        type="button"
        class="scene-glb-row__focus"
        data-scene-glb-focus
        aria-label="定位三维结果"
        :disabled="state.status !== 'visible'"
        @click="emit('focus')"
      >
        <ElIcon><Location /></ElIcon>
      </button>
    </ElTooltip>
  </div>
</template>

<script setup lang="ts">
import { Location } from "@element-plus/icons-vue";
import { ElIcon, ElSwitch, ElTooltip } from "element-plus";
import { computed } from "vue";

import type { SceneGlbOverlayState } from "../../composables/useMapWorkspace";
import { SCENE_GLB_PREVIEW_MAX_BYTES } from "../../map/sceneGlbAsset";
import type { OutputFile } from "../../models/shared";

const props = defineProps<{
  file: OutputFile;
  state: SceneGlbOverlayState;
}>();

const emit = defineEmits<{
  visibility: [visible: boolean];
  focus: [];
}>();

const shortTaskId = computed(() => props.state.taskId.slice(-8));
const switchOn = computed(() => (
  props.state.status === "loading" || props.state.status === "visible"
));
const previewTooLarge = computed(() => (
  typeof props.file.size_bytes === "number"
  && props.file.size_bytes > SCENE_GLB_PREVIEW_MAX_BYTES
));
const stateText = computed(() => {
  if (previewTooLarge.value) return "文件超过预览上限";
  if (props.state.status === "error") return props.state.error || "三维结果加载失败";
  if (props.state.status === "visible") return "已叠加到地形";
  if (props.state.status === "loading") {
    const progress = props.state.progress;
    if (progress?.total && progress.total > 0) {
      const percent = Math.min(100, Math.max(0, Math.round(
        (progress.loaded / progress.total) * 100
      )));
      return `正在加载 ${percent}%`;
    }
    return "正在加载";
  }
  return "未加载";
});
</script>

<style scoped>
.scene-glb-row {
  display: grid;
  grid-template-columns: 10px minmax(0, 1fr) 42px 30px;
  align-items: center;
  gap: 8px;
  min-width: 0;
  min-height: 48px;
  border-top: 1px solid #e2e8f0;
}

.scene-glb-row__swatch {
  width: 10px;
  height: 10px;
  background: #0f9f78;
  border: 1px solid #08745a;
  border-radius: 2px;
}

.scene-glb-row[data-scene-glb-kind="radar_platform_glb"] .scene-glb-row__swatch {
  background: #d99a24;
  border-color: #9a6812;
}

.scene-glb-row__identity {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.scene-glb-row__identity strong,
.scene-glb-row__identity span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.scene-glb-row__identity strong {
  color: #27364a;
  font-size: 12px;
}

.scene-glb-row__identity span {
  color: #64748b;
  font-size: 11px;
}

.scene-glb-row__identity span[data-state="error"] {
  color: #dc2626;
}

.scene-glb-row__focus {
  display: grid;
  width: 28px;
  height: 28px;
  padding: 0;
  place-items: center;
  color: #475569;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 4px;
  cursor: pointer;
}

.scene-glb-row__focus:hover:not(:disabled) {
  color: #166534;
  background: #ecfdf5;
  border-color: #a7f3d0;
}

.scene-glb-row__focus:disabled {
  cursor: default;
  opacity: 0.35;
}
</style>
