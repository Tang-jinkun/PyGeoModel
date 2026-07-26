export interface TianDiTuStyle {
  version: 8;
  sources: Record<string, { type: "raster"; tiles: string[]; tileSize: number }>;
  layers: Array<{ id: string; type: "raster"; source: string }>;
}

const endpoints = ["t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7"];

export function createTiandituStyle(token: string): TianDiTuStyle {
  return {
    version: 8,
    sources: {
      tianditu_vector: rasterSource("vec", token),
      tianditu_annotation: rasterSource("cva", token)
    },
    layers: [
      { id: "tianditu_vector", type: "raster", source: "tianditu_vector" },
      { id: "tianditu_annotation", type: "raster", source: "tianditu_annotation" }
    ]
  };
}

function rasterSource(layer: "vec" | "cva", token: string) {
  return {
    type: "raster" as const,
    tiles: endpoints.map((endpoint) => `https://${endpoint}.tianditu.gov.cn/${layer}_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=${layer}&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&tk=${encodeURIComponent(token)}`),
    tileSize: 256
  };
}
