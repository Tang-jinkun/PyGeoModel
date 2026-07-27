import mapboxEngine from "mapbox-gl";
import maplibreEngine from "maplibre-gl";

export type MapEngineModule = typeof mapboxEngine;

export interface MapEngineConfig {
  name?: string;
  mapboxAccessToken?: string;
}

interface MapEngines {
  maplibre: MapEngineModule;
  mapbox: MapEngineModule;
}

export function selectMapEngine(config: MapEngineConfig, engines: MapEngines): MapEngineModule {
  const name = config.name?.trim() || "maplibre";
  if (name === "maplibre") return engines.maplibre;
  if (name !== "mapbox") {
    throw new Error('VITE_MAP_ENGINE must be "maplibre" or "mapbox"');
  }

  const token = config.mapboxAccessToken?.trim();
  if (!token) {
    throw new Error("VITE_MAPBOX_ACCESS_TOKEN is required when VITE_MAP_ENGINE=mapbox");
  }
  engines.mapbox.accessToken = token;
  return engines.mapbox;
}

const mapEngine = selectMapEngine(
  {
    name: import.meta.env.VITE_MAP_ENGINE,
    mapboxAccessToken: import.meta.env.VITE_MAPBOX_ACCESS_TOKEN
  },
  {
    maplibre: maplibreEngine as unknown as MapEngineModule,
    mapbox: mapboxEngine
  }
);

export default mapEngine;
