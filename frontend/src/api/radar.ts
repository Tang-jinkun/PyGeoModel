import { requestJson } from "./http";
import type {
  BeamClipProfile as RadarBeamClipProfile,
  RadarAdvancedInput,
  RadarDiagnostics,
  RadarMetrics,
  RadarModelMetadata,
  RadarRequest
} from "../models/radar/types";

export type BeamClipProfile = RadarBeamClipProfile;

const DEFAULT_COVERAGE_REQUEST: CoverageRequest = {
  dem_id: "",
  radar: {
    lon: 79.80513693057287,
    lat: 31.4827708959419,
    height_m: 10
  },
  target: {
    height_m: 0
  },
  coverage: {
    max_range_m: 50000,
    scan_mode: "omni",
    azimuth_deg: 90,
    beam_width_deg: 120
  },
  advanced: {
    use_curvature: true,
    curvature_coeff: 0.75,
    output_simplify_tolerance_m: 30,
    voxel_grid_size: 128,
    voxel_vertical_levels: 16,
    voxel_max_height_m: 3000,
    min_elevation_deg: -8,
    max_elevation_deg: 24,
    vertical_beam_width_deg: 32,
    visual_dome_mode: true,
    height_layers_m: []
  },
  reserved_radar_params: {}
};

export interface CoverageOutputFile {
  kind: CoverageOutputKind;
  label: string;
  url: string;
  download_url: string;
  filename: string;
  media_type: string;
  size_bytes?: number | null;
  exists: boolean;
}

export type CoverageOutputKind =
  | "viewshed_tif"
  | "visible_geojson"
  | "blocked_geojson"
  | "range_geojson"
  | "model_metadata_json"
  | "output_manifest_json"
  | "min_visible_height_tif"
  | "voxel_manifest_json"
  | "voxel_points_bin"
  | "clipped_volume_manifest_json"
  | "clipped_volume_cells_bin"
  | "height_layers_manifest_json"
  | "scene_glb"
  | "radar_platform_glb";

export interface CoverageTaskSummary {
  task_id: string;
  dem_id?: string | null;
  status: "pending" | "running" | "finished" | "failed";
  progress: number;
  message: string;
  created_at?: string | null;
  updated_at?: string | null;
  metrics?: RadarMetrics | null;
  outputs?: {
    viewshed_tif?: string | null;
    visible_geojson?: string | null;
    blocked_geojson?: string | null;
    range_geojson?: string | null;
    model_metadata_json?: string | null;
    output_manifest_json?: string | null;
    min_visible_height_tif?: string | null;
    voxel_manifest_json?: string | null;
    voxel_points_bin?: string | null;
    clipped_volume_manifest_json?: string | null;
    clipped_volume_cells_bin?: string | null;
    height_layers_manifest_json?: string | null;
    scene_glb?: string | null;
    radar_platform_glb?: string | null;
  } | null;
  output_files: CoverageOutputFile[];
  model?: RadarModelMetadata | null;
  diagnostics?: RadarDiagnostics | null;
  warnings: string[];
}

export interface CoverageTaskStatus extends CoverageTaskSummary {
  request?: CoverageRequest | null;
}

export interface CoverageProfileSample {
  distance_m: number;
  lon: number;
  lat: number;
  terrain_m: number;
  line_of_sight_m: number;
  clearance_m: number;
}

export interface CoverageProfileResult {
  task_id: string;
  target_lon: number;
  target_lat: number;
  distance_m: number;
  azimuth_deg: number;
  elevation_deg: number;
  radar_ground_m: number;
  target_ground_m: number;
  radar_altitude_m: number;
  target_altitude_m: number;
  blocked: boolean;
  obstruction_distance_m?: number | null;
  obstruction_lon?: number | null;
  obstruction_lat?: number | null;
  obstruction_clearance_m?: number | null;
  min_required_target_height_m: number;
  required_height_delta_m: number;
  reason: string;
  samples: CoverageProfileSample[];
}

export interface FusionMetrics {
  task_count: number;
  union_visible_area_m2: number;
  overlap_visible_area_m2: number;
  union_theoretical_area_m2: number;
  blind_area_m2: number;
  overlap_ratio: number;
  blind_ratio: number;
}

export interface FusionResult {
  task_ids: string[];
  metrics: FusionMetrics;
  visible_union_geojson: GeoJSON.FeatureCollection;
  overlap_geojson: GeoJSON.FeatureCollection;
  blind_geojson: GeoJSON.FeatureCollection;
  warnings: string[];
}

export interface CoverageTaskDeleteResult {
  task_id: string;
  deleted_task_record: boolean;
  deleted_output_dir: boolean;
}

export type AdvancedInput = RadarAdvancedInput;
export type CoverageRequest = RadarRequest;

export async function createCoverageTask(payload: CoverageRequest): Promise<CoverageTaskStatus> {
  return normalizeCoverageTaskStatus(await requestJson("/api/radar/coverage", {
    method: "POST",
    body: JSON.stringify(payload)
  }));
}

export async function listCoverageTasks(): Promise<CoverageTaskSummary[]> {
  const payload = await requestJson<unknown>("/api/radar/coverage");
  return Array.isArray(payload) ? payload.map(normalizeCoverageTaskSummary) : [];
}

export async function getCoverageTask(taskId: string): Promise<CoverageTaskStatus> {
  return normalizeCoverageTaskStatus(await requestJson(`/api/radar/coverage/${taskId}`));
}

export async function getCoverageProfile(taskId: string, lon: number, lat: number): Promise<CoverageProfileResult> {
  const params = new URLSearchParams({
    lon: String(lon),
    lat: String(lat),
    samples: "180"
  });
  return requestJson<CoverageProfileResult>(`/api/radar/coverage/${taskId}/profile?${params.toString()}`);
}

export async function createFusionAnalysis(taskIds: string[]): Promise<FusionResult> {
  return requestJson<FusionResult>("/api/radar/fusion", {
    method: "POST",
    body: JSON.stringify({ task_ids: taskIds })
  });
}

export async function deleteCoverageTask(taskId: string): Promise<CoverageTaskDeleteResult> {
  return requestJson(`/api/radar/coverage/${taskId}`, { method: "DELETE" });
}

export function defaultCoverageRequest(): CoverageRequest {
  return cloneCoverageRequest(DEFAULT_COVERAGE_REQUEST);
}

export function normalizeCoverageRequest(payload: unknown, fallback: CoverageRequest = DEFAULT_COVERAGE_REQUEST): CoverageRequest | null {
  if (!isRecord(payload)) {
    return null;
  }
  const radar = isRecord(payload.radar) ? payload.radar : {};
  const target = isRecord(payload.target) ? payload.target : {};
  const coverage = isRecord(payload.coverage) ? payload.coverage : {};
  const advanced = isRecord(payload.advanced) ? payload.advanced : {};
  const scanMode =
    coverage.scan_mode === "omni" || coverage.scan_mode === "sector" ? coverage.scan_mode : fallback.coverage.scan_mode;

  return {
    dem_id: stringOr(payload.dem_id, fallback.dem_id),
    radar: {
      lon: numberOr(radar.lon, fallback.radar.lon),
      lat: numberOr(radar.lat, fallback.radar.lat),
      height_m: numberOr(radar.height_m, fallback.radar.height_m)
    },
    target: {
      height_m: numberOr(target.height_m, fallback.target.height_m)
    },
    coverage: {
      max_range_m: numberOr(coverage.max_range_m, fallback.coverage.max_range_m),
      scan_mode: scanMode,
      azimuth_deg: numberOr(coverage.azimuth_deg, fallback.coverage.azimuth_deg),
      beam_width_deg: numberOr(coverage.beam_width_deg, fallback.coverage.beam_width_deg)
    },
    advanced: {
      use_curvature: booleanOr(advanced.use_curvature, fallback.advanced.use_curvature),
      curvature_coeff: numberOr(advanced.curvature_coeff, fallback.advanced.curvature_coeff),
      output_simplify_tolerance_m: nullableNumberOr(
        advanced.output_simplify_tolerance_m,
        fallback.advanced.output_simplify_tolerance_m
      ),
      voxel_grid_size: numberOr(advanced.voxel_grid_size, fallback.advanced.voxel_grid_size),
      voxel_vertical_levels: numberOr(advanced.voxel_vertical_levels, fallback.advanced.voxel_vertical_levels),
      voxel_max_height_m: numberOr(advanced.voxel_max_height_m, fallback.advanced.voxel_max_height_m),
      min_elevation_deg: numberOr(advanced.min_elevation_deg, fallback.advanced.min_elevation_deg),
      max_elevation_deg: numberOr(advanced.max_elevation_deg, fallback.advanced.max_elevation_deg),
      vertical_beam_width_deg: numberOr(
        advanced.vertical_beam_width_deg,
        numberOr(advanced.max_elevation_deg, fallback.advanced.max_elevation_deg) -
          numberOr(advanced.min_elevation_deg, fallback.advanced.min_elevation_deg)
      ),
      visual_dome_mode: booleanOr(advanced.visual_dome_mode, fallback.advanced.visual_dome_mode),
      height_layers_m: Array.isArray(advanced.height_layers_m) ? advanced.height_layers_m.filter((item): item is number => typeof item === "number") : fallback.advanced.height_layers_m
    },
    reserved_radar_params: normalizeReservedRadarParams(payload.reserved_radar_params)
  };
}

export function normalizeCoverageTaskStatus(payload: unknown): CoverageTaskStatus {
  const summary = normalizeCoverageTaskSummary(payload);
  const requestFallback = {
    ...DEFAULT_COVERAGE_REQUEST,
    dem_id: summary.dem_id ?? DEFAULT_COVERAGE_REQUEST.dem_id
  };
  const request = isRecord(payload) ? normalizeCoverageRequest(payload.request, requestFallback) : null;
  return {
    ...summary,
    request
  };
}

function normalizeCoverageTaskSummary(payload: unknown): CoverageTaskSummary {
  const task = isRecord(payload) ? payload : {};
  const status = normalizeTaskStatus(task.status);
  const outputs = normalizeOutputs(task.outputs);
  const explicitOutputFiles = Array.isArray(task.output_files) ? task.output_files.map(normalizeOutputFile).filter(isOutputFile) : [];
  return {
    task_id: stringOr(task.task_id, ""),
    dem_id: nullableString(task.dem_id),
    status,
    progress: clampProgress(task.progress, status),
    message: stringOr(task.message, ""),
    created_at: nullableString(task.created_at),
    updated_at: nullableString(task.updated_at),
    metrics: normalizeMetrics(task.metrics),
    outputs,
    output_files: explicitOutputFiles.length ? explicitOutputFiles : deriveOutputFilesFromOutputs(outputs),
    model: normalizeModel(task.model),
    diagnostics: normalizeDiagnostics(task.diagnostics),
    warnings: normalizeWarnings(task.warnings)
  };
}

function normalizeMetrics(payload: unknown): CoverageTaskSummary["metrics"] {
  if (!isRecord(payload)) {
    return null;
  }
  const theoreticalAreaM2 = numberOr(payload.theoretical_area_m2, 0);
  return {
    requested_theoretical_area_m2: numberOr(payload.requested_theoretical_area_m2, theoreticalAreaM2),
    theoretical_area_m2: theoreticalAreaM2,
    unknown_area_m2: numberOr(payload.unknown_area_m2, 0),
    visible_area_m2: numberOr(payload.visible_area_m2, 0),
    blocked_area_m2: numberOr(payload.blocked_area_m2, 0),
    blocked_ratio: numberOr(payload.blocked_ratio, 0),
    terrain_visible_area_m2: numberOr(payload.terrain_visible_area_m2, 0),
    beam_eligible_area_m2: numberOr(payload.beam_eligible_area_m2, 0),
    radar_equation_limited_area_m2: numberOr(payload.radar_equation_limited_area_m2, 0)
  };
}

function normalizeDiagnostics(payload: unknown): CoverageTaskSummary["diagnostics"] {
  if (!isRecord(payload)) {
    return null;
  }
  return {
    radar_equation_active: booleanOr(payload.radar_equation_active, false),
    radar_equation_max_range_m: typeof payload.radar_equation_max_range_m === "number" ? payload.radar_equation_max_range_m : null,
    effective_max_range_m: numberOr(payload.effective_max_range_m, 0),
    terrain_blocked_area_m2: numberOr(payload.terrain_blocked_area_m2, 0),
    elevation_limited_area_m2: numberOr(payload.elevation_limited_area_m2, 0),
    radar_equation_limited_area_m2: numberOr(payload.radar_equation_limited_area_m2, 0),
    notes: normalizeWarnings(payload.notes)
  };
}

function normalizeOutputs(payload: unknown): CoverageTaskSummary["outputs"] {
  if (!isRecord(payload)) {
    return null;
  }
  return {
    viewshed_tif: nullableString(payload.viewshed_tif),
    visible_geojson: nullableString(payload.visible_geojson),
    blocked_geojson: nullableString(payload.blocked_geojson),
    range_geojson: nullableString(payload.range_geojson),
    model_metadata_json: nullableString(payload.model_metadata_json),
    output_manifest_json: nullableString(payload.output_manifest_json),
    min_visible_height_tif: nullableString(payload.min_visible_height_tif),
    voxel_manifest_json: nullableString(payload.voxel_manifest_json),
    voxel_points_bin: nullableString(payload.voxel_points_bin),
    clipped_volume_manifest_json: nullableString(payload.clipped_volume_manifest_json),
    clipped_volume_cells_bin: nullableString(payload.clipped_volume_cells_bin),
    height_layers_manifest_json: nullableString(payload.height_layers_manifest_json),
    scene_glb: nullableString(payload.scene_glb),
    radar_platform_glb: nullableString(payload.radar_platform_glb)
  };
}

function normalizeOutputFile(payload: unknown): Partial<CoverageOutputFile> {
  const file = isRecord(payload) ? payload : {};
  return {
    kind: normalizeOutputKind(file.kind),
    label: stringOr(file.label, stringOr(file.kind, "输出文件")),
    url: stringOr(file.url, ""),
    download_url: stringOr(file.download_url, ""),
    filename: stringOr(file.filename, ""),
    media_type: stringOr(file.media_type, "application/octet-stream"),
    size_bytes: typeof file.size_bytes === "number" ? file.size_bytes : null,
    exists: Boolean(file.exists)
  };
}

function deriveOutputFilesFromOutputs(outputs: CoverageTaskSummary["outputs"]): CoverageOutputFile[] {
  if (!outputs) {
    return [];
  }
  const specs: Array<{ kind: CoverageOutputKind; label: string; media_type: string; filename: string }> = [
    {
      kind: "viewshed_tif",
      label: "视域栅格",
      media_type: "image/tiff",
      filename: "viewshed.tif"
    },
    {
      kind: "visible_geojson",
      label: "可探测区",
      media_type: "application/geo+json",
      filename: "visible.geojson"
    },
    {
      kind: "blocked_geojson",
      label: "遮挡区",
      media_type: "application/geo+json",
      filename: "blocked.geojson"
    },
    {
      kind: "range_geojson",
      label: "理论范围",
      media_type: "application/geo+json",
      filename: "range.geojson"
    },
    {
      kind: "model_metadata_json",
      label: "模型元数据",
      media_type: "application/json",
      filename: "model_metadata.json"
    },
    {
      kind: "output_manifest_json",
      label: "输出清单",
      media_type: "application/json",
      filename: "output_manifest.json"
    },
    {
      kind: "min_visible_height_tif",
      label: "最低可见高度",
      media_type: "image/tiff",
      filename: "min_visible_height.tif"
    },
    {
      kind: "voxel_manifest_json",
      label: "体素清单",
      media_type: "application/json",
      filename: "voxel_manifest.json"
    },
    {
      kind: "voxel_points_bin",
      label: "体素点云",
      media_type: "application/octet-stream",
      filename: "voxel_points.bin"
    },
    {
      kind: "clipped_volume_manifest_json",
      label: "裁切波束清单",
      media_type: "application/json",
      filename: "clipped_volume_manifest.json"
    },
    {
      kind: "clipped_volume_cells_bin",
      label: "裁切波束体",
      media_type: "application/octet-stream",
      filename: "clipped_volume_cells.bin"
    },
    {
      kind: "height_layers_manifest_json",
      label: "高度层清单",
      media_type: "application/json",
      filename: "height_layers_manifest.json"
    },
    {
      kind: "scene_glb",
      label: "Radar Maximum Detection Domain GLB",
      media_type: "model/gltf-binary",
      filename: "radar_detection_domain.glb"
    },
    {
      kind: "radar_platform_glb",
      label: "Radar Platform GLB",
      media_type: "model/gltf-binary",
      filename: "radar_platform.glb"
    }
  ];
  return specs.flatMap((spec) => {
    const url = outputs[spec.kind];
    if (!url) {
      return [];
    }
    return [
      {
        ...spec,
        url,
        download_url: url,
        size_bytes: null,
        exists: true
      }
    ];
  });
}

function isOutputFile(file: Partial<CoverageOutputFile>): file is CoverageOutputFile {
  return Boolean(file.kind && file.label && file.url && file.download_url && file.filename);
}

function normalizeModel(payload: unknown): CoverageTaskSummary["model"] {
  if (!isRecord(payload)) {
    return null;
  }
  return {
    coverage_contract_version: numberOr(payload.coverage_contract_version, 1),
    target_epsg: numberOr(payload.target_epsg, 0),
    radar_projected_xy: numberArray(payload.radar_projected_xy),
    projected_dem_bounds: numberArray(payload.projected_dem_bounds),
    projected_dem_resolution_m: numberArray(payload.projected_dem_resolution_m),
    dem_coverage_ratio: numberOr(payload.dem_coverage_ratio, 1),
    max_range_m: numberOr(payload.max_range_m, 0),
    scan_mode: stringOr(payload.scan_mode, ""),
    azimuth_deg: numberOr(payload.azimuth_deg, 0),
    beam_width_deg: numberOr(payload.beam_width_deg, 360),
    simplify_tolerance_m: numberOr(payload.simplify_tolerance_m, 0),
    voxel_grid_size: numberOr(payload.voxel_grid_size, 128),
    voxel_vertical_levels: numberOr(payload.voxel_vertical_levels, 16),
    voxel_max_height_m: numberOr(payload.voxel_max_height_m, 3000),
    min_elevation_deg: numberOr(payload.min_elevation_deg, 0),
    max_elevation_deg: numberOr(payload.max_elevation_deg, 32),
    vertical_beam_width_deg: numberOr(
      payload.vertical_beam_width_deg,
      numberOr(payload.max_elevation_deg, 32) - numberOr(payload.min_elevation_deg, 0)
    ),
    visual_dome_mode: booleanOr(payload.visual_dome_mode, true),
    height_layers_m: numberArray(payload.height_layers_m),
    radar_equation_active: booleanOr(payload.radar_equation_active, false),
    radar_equation_max_range_m: typeof payload.radar_equation_max_range_m === "number" ? payload.radar_equation_max_range_m : null,
    effective_max_range_m: numberOr(payload.effective_max_range_m, numberOr(payload.max_range_m, 0)),
    beam_clip_profile: normalizeBeamClipProfile(payload.beam_clip_profile),
    range_basis: payload.range_basis === "radar_equation" ? "radar_equation" : "nominal",
    reference_rcs_m2: numberOr(payload.reference_rcs_m2, 1),
    scene3d: isRecord(payload.scene3d) ? payload.scene3d : null,
    gdal_viewshed_command: Array.isArray(payload.gdal_viewshed_command)
      ? payload.gdal_viewshed_command.filter((item): item is string => typeof item === "string")
      : []
  };
}

function normalizeBeamClipProfile(payload: unknown): BeamClipProfile | null {
  if (!isRecord(payload)) {
    return null;
  }
  const azimuthStepDeg = numberOr(payload.azimuth_step_deg, 0);
  const radiusM = numberArray(payload.radius_m);
  if (azimuthStepDeg <= 0 || !radiusM.length) {
    return null;
  }
  return { azimuth_step_deg: azimuthStepDeg, radius_m: radiusM };
}

function normalizeReservedRadarParams(payload: unknown): Record<string, number | null> {
  if (!isRecord(payload)) {
    return {};
  }
  const normalized: Record<string, number | null> = {};
  for (const [key, value] of Object.entries(payload)) {
    if (value == null || typeof value === "number") {
      normalized[key] = value == null ? null : value;
    }
  }
  return normalized;
}

function cloneCoverageRequest(request: CoverageRequest): CoverageRequest {
  return {
    dem_id: request.dem_id,
    radar: { ...request.radar },
    target: { ...request.target },
    coverage: { ...request.coverage },
    advanced: { ...request.advanced, height_layers_m: [...(request.advanced.height_layers_m ?? [])] },
    reserved_radar_params: { ...(request.reserved_radar_params ?? {}) }
  };
}

function normalizeTaskStatus(value: unknown): CoverageTaskSummary["status"] {
  return value === "running" || value === "finished" || value === "failed" ? value : "pending";
}

function normalizeOutputKind(value: unknown): CoverageOutputKind | undefined {
  const kinds: CoverageOutputKind[] = [
    "viewshed_tif",
    "visible_geojson",
    "blocked_geojson",
    "range_geojson",
    "model_metadata_json",
    "output_manifest_json",
    "min_visible_height_tif",
    "voxel_manifest_json",
    "voxel_points_bin",
    "clipped_volume_manifest_json",
    "clipped_volume_cells_bin",
    "height_layers_manifest_json",
    "scene_glb",
    "radar_platform_glb"
  ];
  return kinds.find((kind) => kind === value);
}

function clampProgress(value: unknown, status: CoverageTaskSummary["status"] = "pending") {
  const fallback = status === "finished" ? 100 : 0;
  return Math.min(100, Math.max(0, Math.round(numberOr(value, fallback))));
}

function normalizeWarnings(value: unknown) {
  if (typeof value === "string") {
    return [value];
  }
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function numberArray(value: unknown) {
  return Array.isArray(value) ? value.filter((item): item is number => typeof item === "number") : [];
}

function nullableString(value: unknown) {
  return typeof value === "string" ? value : null;
}

function stringOr(value: unknown, fallback: string) {
  return typeof value === "string" ? value : fallback;
}

function numberOr(value: unknown, fallback: number) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function nullableNumberOr(value: unknown, fallback: number | null) {
  return value === null || (typeof value === "number" && Number.isFinite(value)) ? value : fallback;
}

function booleanOr(value: unknown, fallback: boolean) {
  return typeof value === "boolean" ? value : fallback;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
