import { requestJson, resolveAssetUrl } from "./http";

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
  task_count: number;
  active_task_count: number;
}

export interface DemDeleteResult {
  dem_id: string;
  deleted: boolean;
}

export async function uploadDem(file: File): Promise<DemMetadata> {
  const form = new FormData();
  form.append("file", file);
  return requestJson<DemMetadata>("/api/dem/upload", {
    method: "POST",
    body: form
  });
}

export function listDems(): Promise<DemMetadata[]> {
  return requestJson("/api/dem");
}

export function deleteDem(demId: string): Promise<DemDeleteResult> {
  return requestJson(`/api/dem/${demId}`, { method: "DELETE" });
}

export function demTileUrlTemplate(demId: string): string {
  return resolveAssetUrl(`/api/dem/${demId}/tiles/{z}/{x}/{y}.png`) ?? "";
}

export function demTerrainUrlTemplate(demId: string): string {
  return resolveAssetUrl(`/api/dem/${demId}/terrain/{z}/{x}/{y}.png`) ?? "";
}
