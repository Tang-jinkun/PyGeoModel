import { getRuntimeConfig, normalizeApiBase, type RuntimeConfig } from "../config/runtime";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly payload: unknown
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await requestResponse(path, init);
  return await response.json() as T;
}

export async function requestResponse(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const isFormData = typeof FormData !== "undefined" && init.body instanceof FormData;
  if (init.body && !isFormData && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(resolveApiUrl(path), { ...init, headers });
  const payload = response.ok ? null : await response.clone().json().catch(() => null);
  if (!response.ok) {
    const detail = isRecord(payload) ? payload.detail : undefined;
    const message = isRecord(detail) && typeof detail.message === "string"
      ? detail.message
      : typeof detail === "string"
        ? detail
        : detail != null
          ? stringifyDetail(detail)
        : response.statusText;
    throw new ApiError(response.status, message, payload);
  }
  return response;
}

export async function requestGeoJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  return requestJson<T>(path, init);
}

export function resolveApiUrl(
  path: string,
  runtimeConfig: RuntimeConfig = getRuntimeConfig(),
  buildFallback = import.meta.env.VITE_API_BASE ?? ""
): string {
  if (path !== "/api" && !path.startsWith("/api/")) {
    throw new Error("API paths must begin with /api/");
  }
  const base = normalizeApiBase(runtimeConfig.apiBaseUrl || buildFallback);
  return `${base}${path}`;
}

export function resolveAssetUrl(path?: string | null): string | null {
  if (!path) {
    return null;
  }
  return resolveApiUrl(path);
}

export function resolveMapAssetUrl(path: string): string {
  const resolved = resolveAssetUrl(path);
  if (!resolved) throw new Error("Map asset URL is required");
  return new URL(resolved, window.location.origin).toString()
    .replaceAll("%7B", "{")
    .replaceAll("%7D", "}");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringifyDetail(detail: unknown): string {
  return JSON.stringify(detail) ?? String(detail);
}
