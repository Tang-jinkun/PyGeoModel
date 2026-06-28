const API_BASE = import.meta.env.VITE_API_BASE ?? "";

const DEFAULT_COVERAGE_REQUEST: CoverageRequest = {
  dem_id: "",
  radar: {
    lon: 105.123456,
    lat: 35.123456,
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
    output_simplify_tolerance_m: 30
  },
  reserved_radar_params: {}
};

export interface DemMetadata {
  dem_id: string;
  filename: string;
  crs: string;
  bounds: number[];
  resolution: number[];
  width: number;
  height: number;
  nodata: number | null;
  file_size_bytes?: number | null;
  uploaded_at?: string | null;
}

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
  | "output_manifest_json";

export interface CoverageTaskSummary {
  task_id: string;
  dem_id?: string | null;
  status: "pending" | "running" | "finished" | "failed";
  progress: number;
  message: string;
  created_at?: string | null;
  updated_at?: string | null;
  metrics?: {
    theoretical_area_m2: number;
    visible_area_m2: number;
    blocked_area_m2: number;
    blocked_ratio: number;
  } | null;
  outputs?: {
    viewshed_tif?: string | null;
    visible_geojson?: string | null;
    blocked_geojson?: string | null;
    range_geojson?: string | null;
    model_metadata_json?: string | null;
    output_manifest_json?: string | null;
  } | null;
  output_files: CoverageOutputFile[];
  model?: {
    target_epsg: number;
    radar_projected_xy: number[];
    projected_dem_bounds: number[];
    projected_dem_resolution_m: number[];
    max_range_m: number;
    scan_mode: string;
    azimuth_deg: number;
    beam_width_deg: number;
    simplify_tolerance_m: number;
    gdal_viewshed_command: string[];
  } | null;
  warnings: string[];
}

export interface CoverageTaskStatus extends CoverageTaskSummary {
  request?: CoverageRequest | null;
}

export interface CoverageTaskDeleteResult {
  task_id: string;
  deleted_task_record: boolean;
  deleted_output_dir: boolean;
}

export interface CoverageRequest {
  dem_id: string;
  radar: {
    lon: number;
    lat: number;
    height_m: number;
  };
  target: {
    height_m: number;
  };
  coverage: {
    max_range_m: number;
    scan_mode: "omni" | "sector";
    azimuth_deg: number;
    beam_width_deg: number;
  };
  advanced: {
    use_curvature: boolean;
    curvature_coeff: number;
    output_simplify_tolerance_m: number;
  };
  reserved_radar_params?: Record<string, number | null>;
}

export async function uploadDem(file: File): Promise<DemMetadata> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${API_BASE}/api/dem/upload`, {
    method: "POST",
    body: form
  });
  return handleResponse(response);
}

export async function listDems(): Promise<DemMetadata[]> {
  const response = await fetch(`${API_BASE}/api/dem`);
  return handleResponse(response);
}

export async function createCoverageTask(payload: CoverageRequest): Promise<CoverageTaskStatus> {
  const response = await fetch(`${API_BASE}/api/radar/coverage`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });
  return normalizeCoverageTaskStatus(await handleResponse(response));
}

export async function listCoverageTasks(): Promise<CoverageTaskSummary[]> {
  const response = await fetch(`${API_BASE}/api/radar/coverage`);
  const payload = await handleResponse(response);
  return Array.isArray(payload) ? payload.map(normalizeCoverageTaskSummary) : [];
}

export async function getCoverageTask(taskId: string): Promise<CoverageTaskStatus> {
  const response = await fetch(`${API_BASE}/api/radar/coverage/${taskId}`);
  return normalizeCoverageTaskStatus(await handleResponse(response));
}

export async function deleteCoverageTask(taskId: string): Promise<CoverageTaskDeleteResult> {
  const response = await fetch(`${API_BASE}/api/radar/coverage/${taskId}`, {
    method: "DELETE"
  });
  return handleResponse(response);
}

export function resolveAssetUrl(path?: string | null): string | null {
  if (!path) {
    return null;
  }
  if (/^(https?:|blob:|data:)/.test(path)) {
    return path;
  }
  const normalizedBase = API_BASE.endsWith("/") ? API_BASE.slice(0, -1) : API_BASE;
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${normalizedBase}${normalizedPath}`;
}

async function handleResponse<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const message = payload?.detail?.message ?? payload?.detail ?? response.statusText;
    throw new Error(message);
  }
  return payload as T;
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
      output_simplify_tolerance_m: numberOr(
        advanced.output_simplify_tolerance_m,
        fallback.advanced.output_simplify_tolerance_m
      )
    },
    reserved_radar_params: normalizeReservedRadarParams(payload.reserved_radar_params)
  };
}

function normalizeCoverageTaskStatus(payload: unknown): CoverageTaskStatus {
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
    warnings: normalizeWarnings(task.warnings)
  };
}

function normalizeMetrics(payload: unknown): CoverageTaskSummary["metrics"] {
  if (!isRecord(payload)) {
    return null;
  }
  return {
    theoretical_area_m2: numberOr(payload.theoretical_area_m2, 0),
    visible_area_m2: numberOr(payload.visible_area_m2, 0),
    blocked_area_m2: numberOr(payload.blocked_area_m2, 0),
    blocked_ratio: numberOr(payload.blocked_ratio, 0)
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
    output_manifest_json: nullableString(payload.output_manifest_json)
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
    target_epsg: numberOr(payload.target_epsg, 0),
    radar_projected_xy: numberArray(payload.radar_projected_xy),
    projected_dem_bounds: numberArray(payload.projected_dem_bounds),
    projected_dem_resolution_m: numberArray(payload.projected_dem_resolution_m),
    max_range_m: numberOr(payload.max_range_m, 0),
    scan_mode: stringOr(payload.scan_mode, ""),
    azimuth_deg: numberOr(payload.azimuth_deg, 0),
    beam_width_deg: numberOr(payload.beam_width_deg, 360),
    simplify_tolerance_m: numberOr(payload.simplify_tolerance_m, 0),
    gdal_viewshed_command: Array.isArray(payload.gdal_viewshed_command)
      ? payload.gdal_viewshed_command.filter((item): item is string => typeof item === "string")
      : []
  };
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
    advanced: { ...request.advanced },
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
    "output_manifest_json"
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

function booleanOr(value: unknown, fallback: boolean) {
  return typeof value === "boolean" ? value : fallback;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
