const API_BASE = import.meta.env.VITE_API_BASE ?? "";

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
  kind: string;
  label: string;
  url: string;
  download_url: string;
  filename: string;
  media_type: string;
  size_bytes?: number | null;
  exists: boolean;
}

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
  return handleResponse(response);
}

export async function listCoverageTasks(): Promise<CoverageTaskSummary[]> {
  const response = await fetch(`${API_BASE}/api/radar/coverage`);
  return handleResponse(response);
}

export async function getCoverageTask(taskId: string): Promise<CoverageTaskStatus> {
  const response = await fetch(`${API_BASE}/api/radar/coverage/${taskId}`);
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
