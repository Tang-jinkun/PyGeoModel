import { beforeEach, describe, expect, it, vi } from "vitest";

import { requestJson } from "./http";
import { uploadDemBatch } from "./dem";

vi.mock("./http", () => ({
  requestJson: vi.fn(),
  resolveMapAssetUrl: (path: string) => path
}));

describe("uploadDemBatch", () => {
  beforeEach(() => vi.mocked(requestJson).mockReset());

  it("creates, uploads, completes, and returns the unified DEM", async () => {
    const dem = {
      dem_id: "dem-mosaic",
      filename: "region mosaic",
      crs: "EPSG:4326",
      bounds: [0, 0, 1, 1],
      resolution: [10, 10],
      width: 100,
      height: 100,
      nodata: null,
      task_count: 0,
      active_task_count: 0
    };
    vi.mocked(requestJson)
      .mockResolvedValueOnce({ batch_id: "batch-1", dem_id: "dem-mosaic", status: "uploading", filenames: [], file_count: 0 })
      .mockResolvedValueOnce({ batch_id: "batch-1", filenames: ["a.tif", "b.tif"], file_count: 2 })
      .mockResolvedValueOnce({ batch_id: "batch-1", dem_id: "dem-mosaic", status: "ready", filenames: ["a.tif", "b.tif"], file_count: 2 })
      .mockResolvedValueOnce(dem);
    const files = [new File(["a"], "a.tif"), new File(["b"], "b.tif")];

    await expect(uploadDemBatch(files, "region mosaic")).resolves.toEqual(dem);
    expect(requestJson).toHaveBeenCalledTimes(4);
    expect(vi.mocked(requestJson).mock.calls[1][0]).toBe("/api/dem/batches/batch-1/tiles");
    const form = vi.mocked(requestJson).mock.calls[1][1]?.body as FormData;
    expect(form.getAll("files")).toEqual(files);
  });
});
