<template>
  <section v-if="task" class="result-panel" :data-status="task.status">
    <header class="result-header">
      <div class="result-heading">
        <strong>任务结果</strong>
        <span :title="task.task_id">{{ shortTaskId }}</span>
      </div>
      <span class="result-status" :data-status="task.status">{{ statusLabel }}</span>
      <button v-if="task.request" class="link-button" type="button" @click="$emit('restoreRequest', task.request)">
        恢复参数
      </button>
    </header>

    <div class="result-progress" :aria-label="`进度 ${progressValue}%`">
      <span :style="{ width: `${progressValue}%` }"></span>
    </div>

    <div class="result-summary">
      <div>
        <strong>进度</strong>
        <span>{{ progressValue }}%</span>
      </div>
      <div>
        <strong>DEM</strong>
        <span :title="task.dem_id ?? ''">{{ task.dem_id ?? "-" }}</span>
      </div>
      <div>
        <strong>更新时间</strong>
        <span>{{ updatedTime }}</span>
      </div>
    </div>

    <p v-if="task.message" class="result-message">
      {{ task.message }}
    </p>

    <section class="result-section">
      <h2>覆盖结果</h2>
      <div class="metric-grid">
        <div v-for="item in metricItems" :key="item.label" class="metric-item">
          <strong>{{ item.label }}</strong>
          <span>{{ item.value }}</span>
        </div>
      </div>
    </section>

    <section class="result-section">
      <h2>结果文件</h2>
      <div v-if="downloadGroups.length" class="download-groups">
        <div v-for="group in downloadGroups" :key="group.title" class="download-group">
          <strong>{{ group.title }}</strong>
          <a
            v-for="file in group.files"
            :key="`${file.kind}-${file.download_url}`"
            :href="resolveAssetUrl(file.download_url) ?? file.download_url"
            :download="file.filename"
            :title="file.filename"
            target="_blank"
            rel="noreferrer"
          >
            <span>{{ file.label }}</span>
            <small>{{ formatFileSize(file.size_bytes) }}</small>
          </a>
        </div>
      </div>
      <p v-else class="empty-result">暂无可下载文件</p>
    </section>

    <section class="result-section">
      <h2>模型参数</h2>
      <div class="model-grid">
        <div v-for="item in modelItems" :key="item.label">
          <strong>{{ item.label }}</strong>
          <span>{{ item.value }}</span>
        </div>
      </div>
    </section>

    <section class="result-section">
      <h2>诊断</h2>
      <div class="metric-grid">
        <div v-for="item in diagnosticItems" :key="item.label" class="metric-item">
          <strong>{{ item.label }}</strong>
          <span>{{ item.value }}</span>
        </div>
      </div>
      <div v-if="warningItems.length" class="warning-box">
        <strong>{{ warningItems.length }} 条警告</strong>
        <ul>
          <li v-for="warning in warningItems" :key="warning">{{ warning }}</li>
        </ul>
      </div>
      <p v-else class="empty-result">无警告</p>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed } from "vue";

import { resolveAssetUrl, type CoverageOutputFile, type CoverageTaskStatus } from "../api/client";

const props = defineProps<{
  task: CoverageTaskStatus | null;
}>();

defineEmits<{
  restoreRequest: [request: NonNullable<CoverageTaskStatus["request"]>];
}>();

const statusLabels: Record<CoverageTaskStatus["status"], string> = {
  pending: "排队中",
  running: "计算中",
  finished: "已完成",
  failed: "失败"
};

const downloadOrder: Record<string, number> = {
  visible_geojson: 1,
  blocked_geojson: 2,
  range_geojson: 3,
  viewshed_tif: 4,
  model_metadata_json: 5,
  output_manifest_json: 6
};

const shortTaskId = computed(() => {
  const taskId = props.task?.task_id;
  if (!taskId) {
    return "-";
  }
  return taskId.length > 12 ? `${taskId.slice(0, 8)}...${taskId.slice(-4)}` : taskId;
});

const statusLabel = computed(() => {
  const status = props.task?.status;
  return status ? statusLabels[status] : "-";
});

const progressValue = computed(() => Math.min(100, Math.max(0, Math.round(props.task?.progress ?? 0))));
const updatedTime = computed(() => formatDateTime(props.task?.updated_at ?? props.task?.created_at));
const warningItems = computed(() => (Array.isArray(props.task?.warnings) ? props.task.warnings : []));

const metricItems = computed(() => [
  {
    label: "理论面积",
    value: formatArea(props.task?.metrics?.theoretical_area_m2)
  },
  {
    label: "可探测面积",
    value: formatArea(props.task?.metrics?.visible_area_m2)
  },
  {
    label: "遮挡面积",
    value: formatArea(props.task?.metrics?.blocked_area_m2)
  },
  {
    label: "遮挡比例",
    value: formatRatio(props.task?.metrics?.blocked_ratio)
  },
  {
    label: "地形可见",
    value: formatArea(props.task?.metrics?.terrain_visible_area_m2)
  },
  {
    label: "俯仰可用",
    value: formatArea(props.task?.metrics?.beam_eligible_area_m2)
  }
]);

const modelItems = computed(() => [
  {
    label: "模型 EPSG",
    value: props.task?.model?.target_epsg ? `EPSG:${props.task.model.target_epsg}` : "-"
  },
  {
    label: "扫描模式",
    value: formatScanMode(props.task?.model?.scan_mode ?? props.task?.request?.coverage?.scan_mode)
  },
  {
    label: "最大距离",
    value: formatDistance(props.task?.model?.max_range_m ?? props.task?.request?.coverage?.max_range_m)
  },
  {
    label: "有效距离",
    value: formatDistance(props.task?.model?.effective_max_range_m ?? props.task?.diagnostics?.effective_max_range_m)
  },
  {
    label: "方位角",
    value: formatAngle(props.task?.model?.azimuth_deg ?? props.task?.request?.coverage?.azimuth_deg)
  },
  {
    label: "波束宽度",
    value: formatAngle(props.task?.model?.beam_width_deg ?? props.task?.request?.coverage?.beam_width_deg)
  },
  {
    label: "俯仰范围",
    value: formatElevationRange()
  },
  {
    label: "波束显示",
    value: (props.task?.model?.visual_dome_mode ?? props.task?.request?.advanced?.visual_dome_mode) ? "展示穹顶" : "真实俯仰"
  },
  {
    label: "雷达方程",
    value: formatRadarEquationStatus()
  },
  {
    label: "输出简化",
    value: formatDistance(props.task?.model?.simplify_tolerance_m ?? props.task?.request?.advanced?.output_simplify_tolerance_m)
  }
]);

const downloadableFiles = computed(() =>
  [...(props.task?.output_files?.filter((item) => item.exists) ?? [])].sort(
    (a, b) => (downloadOrder[a.kind] ?? 99) - (downloadOrder[b.kind] ?? 99)
  )
);

const downloadGroups = computed(() => {
  const groups = [
    {
      title: "地图图层",
      files: downloadableFiles.value.filter((file) => getFileGroup(file) === "layer")
    },
    {
      title: "栅格结果",
      files: downloadableFiles.value.filter((file) => getFileGroup(file) === "raster")
    },
    {
      title: "元数据",
      files: downloadableFiles.value.filter((file) => getFileGroup(file) === "metadata")
    }
  ];
  return groups.filter((group) => group.files.length);
});

const diagnosticItems = computed(() => [
  {
    label: "地形遮挡",
    value: formatArea(props.task?.diagnostics?.terrain_blocked_area_m2)
  },
  {
    label: "俯仰限制",
    value: formatArea(props.task?.diagnostics?.elevation_limited_area_m2)
  },
  {
    label: "能量限制",
    value: formatArea(props.task?.diagnostics?.radar_equation_limited_area_m2)
  }
]);

function getFileGroup(file: CoverageOutputFile) {
  if (file.kind.includes("geojson") || file.media_type.includes("geo+json")) {
    return "layer";
  }
  if (file.kind.includes("tif") || file.media_type.includes("tiff")) {
    return "raster";
  }
  return "metadata";
}

function formatArea(value?: number | null) {
  if (value == null) {
    return "-";
  }
  if (value > 1_000_000) {
    return `${(value / 1_000_000).toFixed(2)} km²`;
  }
  return `${value.toFixed(0)} m²`;
}

function formatRatio(value?: number | null) {
  if (value == null) {
    return "-";
  }
  return `${(value * 100).toFixed(1)}%`;
}

function formatDistance(value?: number | null) {
  if (value == null) {
    return "-";
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)} km`;
  }
  return `${value.toFixed(0)} m`;
}

function formatAngle(value?: number | null) {
  if (value == null) {
    return "-";
  }
  return `${value.toFixed(1)}°`;
}

function formatElevationRange() {
  const minValue = props.task?.model?.min_elevation_deg ?? props.task?.request?.advanced?.min_elevation_deg;
  const maxValue = props.task?.model?.max_elevation_deg ?? props.task?.request?.advanced?.max_elevation_deg;
  if (minValue == null || maxValue == null) {
    return "-";
  }
  return `${minValue.toFixed(1)}° ~ ${maxValue.toFixed(1)}°`;
}

function formatRadarEquationStatus() {
  const active = props.task?.model?.radar_equation_active ?? props.task?.diagnostics?.radar_equation_active;
  if (!active) {
    return "未启用";
  }
  const range = props.task?.model?.radar_equation_max_range_m ?? props.task?.diagnostics?.radar_equation_max_range_m;
  return range ? `启用，${formatDistance(range)}` : "启用";
}

function formatScanMode(value?: string | null) {
  if (!value) {
    return "-";
  }
  return value === "omni" ? "全向" : "扇区";
}

function formatDateTime(value?: string | null) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function formatFileSize(value?: number | null) {
  if (value == null) {
    return "";
  }
  if (value < 1024) {
    return `${value} B`;
  }
  if (value > 1024 * 1024) {
    return `${(value / 1024 / 1024).toFixed(1)} MB`;
  }
  return `${(value / 1024).toFixed(1)} KB`;
}
</script>
