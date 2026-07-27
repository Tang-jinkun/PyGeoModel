import { beforeEach, describe, expect, it, vi } from "vitest";

import type { RadarRequest } from "../models/radar/types";
import { addOrUpdateRadarVolume, removeRadarVolume } from "./radarVolumeLayer";

const radarRequest: RadarRequest = {
  dem_id: "dem-a",
  radar: {
    lon: 79.8,
    lat: 31.4,
    height_m: 12
  },
  target: {
    height_m: 5
  },
  coverage: {
    max_range_m: 25_000,
    scan_mode: "sector",
    azimuth_deg: 90,
    beam_width_deg: 30
  },
  advanced: {
    use_curvature: false,
    curvature_coeff: 0,
    output_simplify_tolerance_m: null,
    voxel_grid_size: 25,
    voxel_vertical_levels: 10,
    voxel_max_height_m: 1_000,
    min_elevation_deg: 0,
    max_elevation_deg: 32,
    vertical_beam_width_deg: 12,
    visual_dome_mode: false,
    height_layers_m: []
  }
};

describe("radarVolumeLayer", () => {
  beforeEach(() => {
    removeRadarVolume(new RadarMap({ layers: [] }).asMap());
  });

  it("does not throw before style load and still clears the active radar volume state", () => {
    const mountedMap = new RadarMap({ layers: [{ id: "radar-volume-layer" }] });
    addOrUpdateRadarVolume(mountedMap.asMap(), radarRequest);

    const preStyleMap = new RadarMap(undefined);
    expect(() => removeRadarVolume(preStyleMap.asMap())).not.toThrow();

    addOrUpdateRadarVolume(mountedMap.asMap(), radarRequest);

    expect(mountedMap.removeLayer).toHaveBeenCalledWith("radar-volume-layer");
    expect(mountedMap.addLayer).toHaveBeenCalledTimes(2);
  });
});

class RadarMap {
  layers = new Map<string, { id: string }>();

  constructor(private readonly style: { layers?: Array<{ id: string }> } | undefined) {}

  getLayer = vi.fn((id: string) => this.layers.get(id));
  addLayer = vi.fn((layer: { id: string }) => {
    this.layers.set(layer.id, layer);
  });
  removeLayer = vi.fn((id: string) => {
    this.layers.delete(id);
  });
  getStyle = vi.fn(() => this.style as never);

  asMap() {
    return this as never;
  }
}
