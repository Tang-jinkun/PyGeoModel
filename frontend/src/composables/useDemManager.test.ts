import { beforeEach, describe, expect, it, vi } from "vitest";

import { deleteDem, listDems, uploadDem, type DemMetadata } from "../api/dem";
import { useDemManager } from "./useDemManager";

vi.mock("../api/dem", () => ({
  deleteDem: vi.fn(),
  listDems: vi.fn(),
  uploadDem: vi.fn()
}));

const demA: DemMetadata = {
  dem_id: "dem-a",
  filename: "terrain-a.tif",
  crs: "EPSG:4326",
  bounds: [0, 0, 1, 1],
  resolution: [10, 10],
  width: 100,
  height: 100,
  nodata: null,
  task_count: 3,
  active_task_count: 1
};

describe("useDemManager", () => {
  beforeEach(() => {
    vi.mocked(deleteDem).mockReset();
    vi.mocked(listDems).mockReset();
    vi.mocked(uploadDem).mockReset();
  });

  it("loads DEMs and tracks the selected DEM id", async () => {
    vi.mocked(listDems).mockResolvedValue([demA]);
    const manager = useDemManager();

    await manager.load();
    manager.select(demA.dem_id);

    expect(manager.dems.value).toEqual([demA]);
    expect(manager.selectedDem.value).toBe("dem-a");
    expect(manager.loading.value).toBe(false);
  });

  it("adds an uploaded DEM after the upload succeeds", async () => {
    vi.mocked(uploadDem).mockResolvedValue(demA);
    const manager = useDemManager();

    await manager.upload(new File(["elevation"], demA.filename, { type: "image/tiff" }));

    expect(manager.dems.value).toEqual([demA]);
    expect(manager.uploading.value).toBe(false);
  });

  it("clears a selected DEM only after backend deletion succeeds", async () => {
    const manager = useDemManager();
    vi.mocked(listDems).mockResolvedValue([demA]);
    await manager.load();
    manager.select(demA.dem_id);
    vi.mocked(deleteDem).mockRejectedValueOnce(new Error("delete failed"));

    await expect(manager.remove(demA.dem_id)).rejects.toThrow("delete failed");
    expect(manager.selectedDem.value).toBe(demA.dem_id);
    expect(manager.dems.value).toEqual([demA]);

    vi.mocked(deleteDem).mockResolvedValueOnce({ dem_id: demA.dem_id, deleted: true });
    await manager.remove(demA.dem_id);

    expect(manager.selectedDem.value).toBeNull();
    expect(manager.dems.value).toEqual([]);
  });
});
