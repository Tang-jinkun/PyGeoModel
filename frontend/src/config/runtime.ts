export interface RuntimeConfig {
  apiBaseUrl: string;
}

declare global {
  interface Window {
    __PYGEOMODEL_RUNTIME_CONFIG__?: Partial<RuntimeConfig>;
  }
}

export function normalizeApiBase(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  if (trimmed.startsWith("//")) throw new Error("Protocol-relative API bases are not supported");
  const absolute = /^https?:\/\//.test(trimmed);
  if (!trimmed.startsWith("/") && !absolute) throw new Error("Invalid API base URL");
  const parsed = new URL(trimmed, window.location.origin);
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") throw new Error("Invalid API base URL");
  if (parsed.username || parsed.password || parsed.search || parsed.hash) throw new Error("Invalid API base URL");
  const pathname = parsed.pathname.replace(/\/+$/, "");
  if (pathname.endsWith("/api")) throw new Error("PYGEOMODEL_API_BASE_URL must exclude /api");
  return absolute ? `${parsed.origin}${pathname}` : pathname;
}

export function getRuntimeConfig(buildFallback = import.meta.env.VITE_API_BASE ?? ""): RuntimeConfig {
  return {
    apiBaseUrl: normalizeApiBase(
      window.__PYGEOMODEL_RUNTIME_CONFIG__?.apiBaseUrl ?? buildFallback
    )
  };
}
