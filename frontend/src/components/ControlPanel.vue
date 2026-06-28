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
    </el-form>
  </aside>
</template>

<script setup lang="ts">
import type { UploadFile } from "element-plus";
import { computed } from "vue";

import type { CoverageRequest, DemMetadata } from "../api/client";

const props = defineProps<{
  model: CoverageRequest;
  dem: DemMetadata | null;
  busy: boolean;
}>();

const emit = defineEmits<{
  upload: [file: File];
  run: [];
}>();

const scanOptions = [
  { label: "全向", value: "omni" },
  { label: "扇区", value: "sector" }
];

const demLabel = computed(() => props.dem?.filename ?? "点击或拖拽上传 GeoTIFF DEM");

function onFileChange(uploadFile: UploadFile) {
  const raw = uploadFile.raw;
  if (raw) {
    emit("upload", raw);
  }
}
</script>
