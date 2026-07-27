export type RadarPreviewTaskStatus = "pending" | "running" | "finished" | "failed" | null;

export function shouldShowRadarPreview(_status: RadarPreviewTaskStatus): boolean {
  return false;
}
