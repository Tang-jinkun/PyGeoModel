<template>
  <aside class="control-panel">
    <div class="panel-header">
      <h1>PyGeoModel</h1>
      <span>DEM 雷达地形遮挡分析</span>
    </div>

    <el-form label-position="top" size="small">
      <el-form-item label="DEM 文件">
        <el-upload
          drag
          :auto-upload="false"
          :show-file-list="false"
          :on-change="onFileChange"
          accept=".tif,.tiff"
        >
          <div class="upload-label">{{ demLabel }}</div>
        </el-upload>
      </el-form-item>

      <div v-if="dem" class="metadata">
        <div><strong>CRS</strong><span>{{ dem.crs }}</span></div>
        <div><strong>Size</strong><span>{{ dem.width }} × {{ dem.height }}</span></div>
        <div><strong>Resolution</strong><span>{{ dem.resolution.map((v) => v.toFixed(2)).join(" / ") }}</span></div>
        <div><strong>File</strong><span>{{ formatFileSize(dem.file_size_bytes) }}</span></div>
        <div><strong>Tasks</strong><span>{{ dem.task_count }} 个关联任务</span></div>
      </div>

      <el-form-item v-if="demList.length" label="已上传 DEM">
        <el-select :model-value="dem?.dem_id" filterable placeholder="选择历史 DEM" @change="selectDem">
          <el-option
            v-for="item in demList"
            :key="item.dem_id"
            :label="item.filename"
            :value="item.dem_id"
          />
        </el-select>
      </el-form-item>

      <div v-if="dem" class="dem-actions">
        <span>{{ dem.active_task_count ? `${dem.active_task_count} 个任务正在使用` : deleteDemHint }}</span>
        <el-popconfirm
          title="删除该 DEM 文件？"
          confirm-button-text="删除"
          cancel-button-text="取消"
          @confirm="$emit('deleteDem', dem.dem_id)"
        >
          <template #reference>
            <el-button
              size="small"
              type="danger"
              :loading="deletingDemId === dem.dem_id"
              :disabled="!canDeleteDem"
            >
              删除 DEM
            </el-button>
          </template>
        </el-popconfirm>
      </div>

      <div class="form-grid">
        <el-form-item label="经度">
          <el-input-number v-model="model.radar.lon" :precision="6" :step="0.001" controls-position="right" />
        </el-form-item>
        <el-form-item label="纬度">
          <el-input-number v-model="model.radar.lat" :precision="6" :step="0.001" controls-position="right" />
        </el-form-item>
      </div>

      <div class="form-grid">
        <el-form-item label="雷达高度 m">
          <el-input-number v-model="model.radar.height_m" :min="0" controls-position="right" />
        </el-form-item>
        <el-form-item label="目标高度 m">
          <el-input-number v-model="model.target.height_m" :min="0" controls-position="right" />
        </el-form-item>
      </div>

      <el-form-item label="最大探测半径 m">
        <el-input-number v-model="model.coverage.max_range_m" :min="1" :max="100000" :step="1000" controls-position="right" />
      </el-form-item>

      <el-form-item label="扫描模式">
        <el-segmented v-model="model.coverage.scan_mode" :options="scanOptions" />
      </el-form-item>

      <div class="form-grid">
        <el-form-item label="方位角 °">
          <el-input-number
            v-model="model.coverage.azimuth_deg"
            :min="0"
            :max="359.99"
            :disabled="model.coverage.scan_mode === 'omni'"
            controls-position="right"
          />
        </el-form-item>
        <el-form-item label="波束宽度 °">
          <el-input-number
            v-model="model.coverage.beam_width_deg"
            :min="1"
            :max="360"
            :disabled="model.coverage.scan_mode === 'omni'"
            controls-position="right"
          />
        </el-form-item>
      </div>

      <div class="form-grid">
        <el-form-item label="曲率折射">
          <el-switch v-model="model.advanced.use_curvature" />
        </el-form-item>
        <el-form-item label="曲率系数">
          <el-input-number
            v-model="model.advanced.curvature_coeff"
            :min="0"
            :max="1"
            :step="0.05"
            :disabled="!model.advanced.use_curvature"
            controls-position="right"
          />
        </el-form-item>
      </div>

      <el-button type="primary" class="run-button" :loading="busy" :disabled="!dem" @click="$emit('run')">
        开始计算
      </el-button>

      <section class="task-history">
        <div class="task-history-header">
          <h2>历史任务</h2>
          <el-button size="small" :loading="taskListLoading" @click="$emit('refreshTasks')">刷新</el-button>
        </div>
        <div v-if="taskList.length" class="task-list">
          <article
            v-for="item in taskList"
            :key="item.task_id"
            class="task-item"
            :class="{ active: item.task_id === selectedTaskId }"
          >
            <div class="task-main">
              <span class="task-status" :data-status="item.status">{{ statusLabel(item.status) }}</span>
              <strong>{{ shortTaskId(item.task_id) }}</strong>
              <span>{{ formatTaskTime(item.created_at) }}</span>
            </div>
            <div class="task-meta">
              <span>{{ item.dem_id ?? "无 DEM" }}</span>
              <span>{{ taskCoverageLabel(item) }}</span>
              <span>{{ taskMetricLabel(item) }}</span>
            </div>
            <el-progress
              v-if="item.status === 'pending' || item.status === 'running'"
              :percentage="item.progress"
              :show-text="false"
              :stroke-width="5"
            />
            <p v-if="item.status === 'failed'" class="task-message">{{ item.message || "计算失败" }}</p>
            <div class="task-actions">
              <el-button
                size="small"
                :disabled="busy || !!deletingTaskId || item.status !== 'finished'"
                :loading="loadingTaskId === item.task_id"
                @click="selectTask(item.task_id)"
              >
                加载结果
              </el-button>
              <el-button
                size="small"
                :disabled="busy || !!deletingTaskId"
                :loading="restoringTaskId === item.task_id"
                @click="$emit('restoreTask', item.task_id)"
              >
                恢复参数
              </el-button>
              <el-popconfirm
                title="删除任务记录和输出文件？"
                confirm-button-text="删除"
                cancel-button-text="取消"
                @confirm="$emit('deleteTask', item.task_id)"
              >
                <template #reference>
                  <el-button
                    size="small"
                    type="danger"
                    :loading="deletingTaskId === item.task_id"
                    :disabled="!canDeleteTask(item)"
                  >
                    删除
                  </el-button>
                </template>
              </el-popconfirm>
            </div>
          </article>
        </div>
        <div v-else class="empty-history">暂无历史任务</div>
      </section>
    </el-form>
  </aside>
</template>

<script setup lang="ts">
import type { UploadFile } from "element-plus";
import { computed } from "vue";

import type { CoverageRequest, CoverageTaskSummary, DemMetadata } from "../api/client";

const props = defineProps<{
  model: CoverageRequest;
  dem: DemMetadata | null;
  demList: DemMetadata[];
  taskList: CoverageTaskSummary[];
  selectedTaskId: string | null;
  taskListLoading: boolean;
  loadingTaskId: string | null;
  restoringTaskId: string | null;
  deletingTaskId: string | null;
  deletingDemId: string | null;
  busy: boolean;
}>();

const emit = defineEmits<{
  upload: [file: File];
  selectDem: [demId: string];
  selectTask: [taskId: string];
  restoreTask: [taskId: string];
  deleteTask: [taskId: string];
  deleteDem: [demId: string];
  refreshTasks: [];
  run: [];
}>();

const scanOptions = [
  { label: "全向", value: "omni" },
  { label: "扇区", value: "sector" }
];

const demLabel = computed(() => props.dem?.filename ?? "点击或拖拽上传 GeoTIFF DEM");
const canDeleteDem = computed(() => Boolean(props.dem && !props.busy && !props.deletingDemId && props.dem.task_count === 0));
const deleteDemHint = computed(() => {
  if (!props.dem) {
    return "";
  }
  return props.dem.task_count > 0 ? "存在历史任务引用，不能删除" : "未被任务引用，可删除";
});

function onFileChange(uploadFile: UploadFile) {
  const raw = uploadFile.raw;
  if (raw) {
    emit("upload", raw);
  }
}

function selectDem(demId: string) {
  emit("selectDem", demId);
}

function selectTask(taskId: string) {
  emit("selectTask", taskId);
}

function formatFileSize(value?: number | null) {
  if (value == null) {
    return "-";
  }
  if (value > 1024 * 1024) {
    return `${(value / 1024 / 1024).toFixed(1)} MB`;
  }
  return `${(value / 1024).toFixed(1)} KB`;
}

function shortTaskId(taskId: string) {
  return taskId.replace(/^task_/, "").slice(-8);
}

function formatTaskTime(value?: string | null) {
  return value ? new Date(value).toLocaleString() : "-";
}

function outputCount(task: CoverageTaskSummary) {
  return task.output_files?.filter((item) => item.exists).length ?? 0;
}

function taskCoverageLabel(task: CoverageTaskSummary) {
  const files = outputCount(task);
  if (task.status === "finished") {
    return `${files} 个文件`;
  }
  return `${task.progress}%`;
}

function taskMetricLabel(task: CoverageTaskSummary) {
  if (task.metrics) {
    return `遮挡 ${formatRatio(task.metrics.blocked_ratio)}`;
  }
  return task.updated_at ? `更新 ${formatTaskTime(task.updated_at)}` : task.message || "-";
}

function statusLabel(status: CoverageTaskSummary["status"]) {
  const labels = {
    pending: "排队",
    running: "运行",
    finished: "完成",
    failed: "失败"
  };
  return labels[status] ?? status;
}

function canDeleteTask(task: CoverageTaskSummary) {
  if (props.busy || props.deletingTaskId) {
    return false;
  }
  return task.status === "finished" || task.status === "failed";
}

function formatRatio(value?: number | null) {
  if (value == null) {
    return "-";
  }
  return `${(value * 100).toFixed(1)}%`;
}
</script>
