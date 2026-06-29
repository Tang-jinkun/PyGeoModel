<template>
  <section v-if="loading || profile" class="profile-panel" :data-blocked="profile?.blocked ?? false">
    <header class="profile-header">
      <div>
        <strong>剖面分析</strong>
        <span>{{ profile ? profile.reason : "采样中" }}</span>
      </div>
      <button class="profile-close" type="button" aria-label="关闭剖面" @click="$emit('close')">x</button>
    </header>

    <div v-if="loading" class="profile-loading">正在读取地形剖面...</div>

    <template v-else-if="profile">
      <div class="profile-status">
        <strong>{{ profile.blocked ? "存在遮挡" : "视线可达" }}</strong>
        <span v-if="profile.blocked">最低目标高度还需增加 {{ formatDistance(profile.required_height_delta_m) }}</span>
        <span v-else>当前目标高度满足这条剖面视线</span>
      </div>

      <div class="profile-metrics">
        <div>
          <strong>距离</strong>
          <span>{{ formatDistance(profile.distance_m) }}</span>
        </div>
        <div>
          <strong>方位</strong>
          <span>{{ formatAngle(profile.azimuth_deg) }}</span>
        </div>
        <div>
          <strong>俯仰</strong>
          <span>{{ formatAngle(profile.elevation_deg) }}</span>
        </div>
        <div>
          <strong>最低目标高</strong>
          <span>{{ formatDistance(profile.min_required_target_height_m) }}</span>
        </div>
      </div>

      <div class="profile-chart-wrap">
        <svg class="profile-chart" viewBox="0 0 360 150" role="img" aria-label="地形剖面">
          <line x1="28" y1="124" x2="344" y2="124" class="profile-axis" />
          <polyline :points="terrainPoints" class="profile-terrain" />
          <polyline :points="sightPoints" class="profile-sight" />
          <circle
            v-if="obstructionPoint"
            :cx="obstructionPoint.x"
            :cy="obstructionPoint.y"
            r="4.5"
            class="profile-obstruction-dot"
          />
        </svg>
        <div class="profile-legend">
          <span><i class="terrain"></i>地形</span>
          <span><i class="sight"></i>视线</span>
          <span v-if="profile.blocked"><i class="blocked"></i>遮挡点</span>
        </div>
      </div>

      <div v-if="profile.blocked" class="profile-obstruction">
        <strong>最严重遮挡</strong>
        <span>
          {{ formatDistance(profile.obstruction_distance_m) }} 处，净空
          {{ formatSignedDistance(profile.obstruction_clearance_m) }}
        </span>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed } from "vue";

import type { CoverageProfileResult } from "../api/client";

const props = defineProps<{
  profile: CoverageProfileResult | null;
  loading: boolean;
}>();

defineEmits<{
  close: [];
}>();

const chart = {
  left: 28,
  right: 344,
  top: 16,
  bottom: 124
};

const yDomain = computed(() => {
  const samples = props.profile?.samples ?? [];
  const values = samples.flatMap((sample) => [sample.terrain_m, sample.line_of_sight_m]);
  if (!values.length) {
    return { min: 0, max: 1 };
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const padding = Math.max(10, (max - min) * 0.12);
  return { min: min - padding, max: max + padding };
});

const terrainPoints = computed(() => toPolyline("terrain_m"));
const sightPoints = computed(() => toPolyline("line_of_sight_m"));

const obstructionPoint = computed(() => {
  const profile = props.profile;
  if (!profile?.blocked || profile.obstruction_distance_m == null) {
    return null;
  }
  const sample = profile.samples.reduce((closest, current) => {
    if (!closest) {
      return current;
    }
    return Math.abs(current.distance_m - profile.obstruction_distance_m!) <
      Math.abs(closest.distance_m - profile.obstruction_distance_m!)
      ? current
      : closest;
  }, null as CoverageProfileResult["samples"][number] | null);
  return sample ? toPoint(sample.distance_m, sample.terrain_m) : null;
});

function toPolyline(key: "terrain_m" | "line_of_sight_m") {
  return (props.profile?.samples ?? [])
    .map((sample) => {
      const point = toPoint(sample.distance_m, sample[key]);
      return `${point.x.toFixed(1)},${point.y.toFixed(1)}`;
    })
    .join(" ");
}

function toPoint(distanceM: number, value: number) {
  const profile = props.profile;
  const xRatio = profile?.distance_m ? distanceM / profile.distance_m : 0;
  const domain = yDomain.value;
  const yRatio = (value - domain.min) / Math.max(1, domain.max - domain.min);
  return {
    x: chart.left + xRatio * (chart.right - chart.left),
    y: chart.bottom - yRatio * (chart.bottom - chart.top)
  };
}

function formatDistance(value?: number | null) {
  if (value == null || !Number.isFinite(value)) {
    return "-";
  }
  if (Math.abs(value) >= 1000) {
    return `${(value / 1000).toFixed(2)} km`;
  }
  return `${value.toFixed(1)} m`;
}

function formatSignedDistance(value?: number | null) {
  if (value == null || !Number.isFinite(value)) {
    return "-";
  }
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${formatDistance(value)}`;
}

function formatAngle(value?: number | null) {
  if (value == null || !Number.isFinite(value)) {
    return "-";
  }
  return `${value.toFixed(1)}°`;
}
</script>
