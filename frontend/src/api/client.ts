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
}

export interface CoverageTaskStatus {
  task_id: string;
  status: "pending" | "running" | "finished" | "failed";
  progress: number;
  message: string;
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
  } | null;
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

export async function getCoverageTask(taskId: string): Promise<CoverageTaskStatus> {
  const response = await fetch(`${API_BASE}/api/radar/coverage/${taskId}`);
  return handleResponse(response);
}

export function resolveAssetUrl(path?: string | null): string | null {
  if (!path) {
    return null;
  }
  if (path.startsWith("http")) {
    return path;
  }
  return `${API_BASE}${path}`;
}

async function handleResponse<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const message = payload?.detail?.message ?? payload?.detail ?? response.statusText;
    throw new Error(message);
  }
  return payload as T;
}
