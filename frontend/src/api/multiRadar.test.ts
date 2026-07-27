import { describe, expect, it, vi } from "vitest";

const { requestJson } = vi.hoisted(() => ({ requestJson: vi.fn() }));
vi.mock("./http", () => ({ requestJson }));

import { createMultiRadarTask, findMultiRadarOutputPath, getMultiRadarOutputs } from "./multiRadar";

describe("multi-radar API client", () => {
  it("posts a batch request to the multi-coverage endpoint", async () => {
    requestJson.mockResolvedValueOnce({ task_id: "multi_task_a", status: "pending", dem_id: "dem_a", radars: [] });

    await createMultiRadarTask({
      dem_id: "dem_a",
      radars: [
        { radar_id: "north", radar: { lon: 79, lat: 31.5, height_m: 20 }, coverage: { max_range_m: 1000 } },
        { radar_id: "south", radar: { lon: 79.1, lat: 31.5, height_m: 20 }, coverage: { max_range_m: 1000 } }
      ]
    });

    expect(requestJson).toHaveBeenCalledWith(
      "/api/radar/multi-coverage",
      expect.objectContaining({ method: "POST" })
    );
  });

  it("posts cooperative presentation mode", async () => {
    requestJson.mockResolvedValueOnce({ task_id: "multi_task_a", status: "pending", dem_id: "dem_a", radars: [] });

    await createMultiRadarTask({
      dem_id: "dem_a",
      presentation_mode: "cooperative_3d",
      radars: [
        { radar_id: "north", radar: { lon: 79, lat: 31.5, height_m: 20 }, coverage: { max_range_m: 1000 } },
        { radar_id: "south", radar: { lon: 79.1, lat: 31.5, height_m: 20 }, coverage: { max_range_m: 1000 } },
        { radar_id: "east", radar: { lon: 79.05, lat: 31.55, height_m: 20 }, coverage: { max_range_m: 1000 } }
      ]
    });

    expect(requestJson).toHaveBeenCalledWith(
      "/api/radar/multi-coverage",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining('"presentation_mode":"cooperative_3d"')
      })
    );
  });

  it("loads canonical output descriptors from the live outputs endpoint", async () => {
    requestJson.mockResolvedValueOnce([]);

    await getMultiRadarOutputs("multi_task_a");

    expect(requestJson).toHaveBeenCalledWith("/api/radar/multi-coverage/multi_task_a/outputs");
  });

  it("keeps a canonical output path unresolved for the HTTP client", () => {
    expect(findMultiRadarOutputPath([{
      kind: "visible_union_geojson",
      filename: "visible_union.geojson",
      label: "Visible Union GeoJSON",
      media_type: "application/geo+json",
      required: true,
      exists: true,
      download_path: "/api/radar/multi-coverage/multi_task_a/outputs/visible_union_geojson"
    }], "visible_union_geojson")).toBe(
      "/api/radar/multi-coverage/multi_task_a/outputs/visible_union_geojson"
    );
  });
});
