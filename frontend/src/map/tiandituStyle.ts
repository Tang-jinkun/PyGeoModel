export interface TianDiTuStyle {
  version: 8;
  sources: Record<string, { type: "raster"; tiles: string[]; tileSize: number }>;
  layers: Array<{ id: string; type: "raster"; source: string }>;
}

const endpoints = ["t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7"];
const tileProxyVersion = "2";

export function createTiandituStyle(): TianDiTuStyle {
  return {
    version: 8,
    sources: {
      tianditu_vector: rasterSource("vec"),
      tianditu_annotation: rasterSource("cva")
    },
    layers: [
      { id: "tianditu_vector", type: "raster", source: "tianditu_vector" },
      { id: "tianditu_annotation", type: "raster", source: "tianditu_annotation" }
    ]
  };
}

function rasterSource(layer: "vec" | "cva") {
  return {
    type: "raster" as const,
    tiles: endpoints.map((endpoint) => `/PyGeoModel/tianditu/${endpoint}/${layer}_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=${layer}&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&PROXY_VERSION=${tileProxyVersion}`),
    tileSize: 256
  };
}
