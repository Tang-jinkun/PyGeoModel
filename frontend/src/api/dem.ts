import { requestJson, resolveMapAssetUrl } from "./http";

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
  source_type?: string | null;
  source_tile_count?: number | null;
  source_filenames?: string[];
}

export interface DemBatchStatus {
  batch_id: string;
  dem_id: string;
  label?: string | null;
  status: "uploading" | "validating" | "merging" | "ready" | "failed";
  filenames: string[];
  file_count: number;
  error?: string | null;
}

export interface DemBatchUploadResult {
  batch_id: string;
  filenames: string[];
  file_count: number;
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

export function createDemBatch(label?: string): Promise<DemBatchStatus> {
  return requestJson("/api/dem/batches", {
    method: "POST",
    body: JSON.stringify(label ? { label } : {})
  });
}

export function uploadDemBatchTiles(batchId: string, files: File[]): Promise<DemBatchUploadResult> {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  return requestJson(`/api/dem/batches/${batchId}/tiles`, { method: "POST", body: form });
}

export function completeDemBatch(batchId: string): Promise<DemBatchStatus> {
  return requestJson(`/api/dem/batches/${batchId}/complete`, { method: "POST" });
}

export function getDemBatch(batchId: string): Promise<DemBatchStatus> {
  return requestJson(`/api/dem/batches/${batchId}`);
}

export async function uploadDemBatch(files: File[], label?: string): Promise<DemMetadata> {
  if (files.length < 2) throw new Error("A DEM batch requires at least two TIF files.");
  const batch = await createDemBatch(label);
  await uploadDemBatchTiles(batch.batch_id, files);
  let status = await completeDemBatch(batch.batch_id);
  for (let attempt = 0; attempt < 120; attempt += 1) {
    if (status.status === "ready") return requestJson(`/api/dem/${status.dem_id}`);
    if (status.status === "failed") throw new Error(status.error ?? "DEM tile merge failed");
    await new Promise((resolve) => setTimeout(resolve, 250));
    status = await getDemBatch(batch.batch_id);
  }
  throw new Error("Timed out waiting for DEM tile merge");
}

export function listDems(): Promise<DemMetadata[]> {
  return requestJson("/api/dem");
}

export function deleteDem(demId: string): Promise<DemDeleteResult> {
  return requestJson(`/api/dem/${demId}`, { method: "DELETE" });
}

export function demTileUrlTemplate(demId: string): string {
  return resolveMapAssetUrl(`/api/dem/${demId}/tiles/{z}/{x}/{y}.png`);
}

export function demTerrainUrlTemplate(demId: string): string {
  return resolveMapAssetUrl(`/api/dem/${demId}/terrain/{z}/{x}/{y}.png`);
}
