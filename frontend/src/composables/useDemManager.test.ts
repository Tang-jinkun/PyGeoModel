import { beforeEach, describe, expect, it, vi } from "vitest";

import { deleteDem, listDems, uploadDem, type DemMetadata } from "../api/dem";
import { useDemManager } from "./useDemManager";
import { useModelWorkspace } from "./useModelWorkspace";

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

const demB: DemMetadata = {
  ...demA,
  dem_id: "dem-b",
  filename: "terrain-b.tif"
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve;
  });
  return { promise, resolve };
}

function createManagerWithWorkspace() {
  const workspace = useModelWorkspace();
  const manager = useDemManager({ setDemForAll: workspace.setDemForAll });
  return { manager, workspace };
}

describe("useDemManager", () => {
  beforeEach(() => {
    vi.mocked(deleteDem).mockReset();
    vi.mocked(listDems).mockReset();
    vi.mocked(uploadDem).mockReset();
  });

  it("selects a DEM for every model draft", async () => {
    vi.mocked(listDems).mockResolvedValue([demA]);
    const { manager, workspace } = createManagerWithWorkspace();

    await manager.load();
    manager.select(demA.dem_id);

    expect(manager.dems.value).toEqual([demA]);
    expect(manager.selectedDem.value).toBe("dem-a");
    expect(Object.values(workspace.drafts).every(({ dem_id }) => dem_id === "dem-a")).toBe(true);
    expect(manager.loading.value).toBe(false);
  });

  it("selects an uploaded DEM for every model draft", async () => {
    vi.mocked(uploadDem).mockResolvedValue(demA);
    const { manager, workspace } = createManagerWithWorkspace();

    await manager.upload(new File(["elevation"], demA.filename, { type: "image/tiff" }));

    expect(manager.dems.value).toEqual([demA]);
    expect(manager.selectedDem.value).toBe(demA.dem_id);
    expect(Object.values(workspace.drafts).every(({ dem_id }) => dem_id === demA.dem_id)).toBe(true);
    expect(manager.uploading.value).toBe(false);
  });

  it("clears a selected DEM and every draft only after backend deletion succeeds", async () => {
    const { manager, workspace } = createManagerWithWorkspace();
    vi.mocked(listDems).mockResolvedValue([demA]);
    await manager.load();
    manager.select(demA.dem_id);
    vi.mocked(deleteDem).mockRejectedValueOnce(new Error("delete failed"));

    await expect(manager.remove(demA.dem_id)).rejects.toThrow("delete failed");
    expect(manager.selectedDem.value).toBe(demA.dem_id);
    expect(manager.dems.value).toEqual([demA]);
    expect(Object.values(workspace.drafts).every(({ dem_id }) => dem_id === demA.dem_id)).toBe(true);

    vi.mocked(deleteDem).mockResolvedValueOnce({ dem_id: demA.dem_id, deleted: true });
    await manager.remove(demA.dem_id);

    expect(manager.selectedDem.value).toBeNull();
    expect(manager.dems.value).toEqual([]);
    expect(Object.values(workspace.drafts).every(({ dem_id }) => dem_id === "")).toBe(true);
  });

  it("keeps only the newest load result when an older load resolves last", async () => {
    const older = deferred<DemMetadata[]>();
    const newer = deferred<DemMetadata[]>();
    vi.mocked(listDems)
      .mockReturnValueOnce(older.promise)
      .mockReturnValueOnce(newer.promise);
    const { manager } = createManagerWithWorkspace();

    const firstLoad = manager.load();
    const secondLoad = manager.load();
    newer.resolve([demB]);
    await secondLoad;
    older.resolve([demA]);
    await firstLoad;

    expect(manager.dems.value).toEqual([demB]);
  });

  it("keeps loading true until every concurrent load settles", async () => {
    const first = deferred<DemMetadata[]>();
    const second = deferred<DemMetadata[]>();
    vi.mocked(listDems)
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const { manager } = createManagerWithWorkspace();

    const firstLoad = manager.load();
    const secondLoad = manager.load();
    expect(manager.loading.value).toBe(true);

    second.resolve([demB]);
    await secondLoad;
    expect(manager.loading.value).toBe(true);

    first.resolve([demA]);
    await firstLoad;
    expect(manager.loading.value).toBe(false);
  });

  it("merges concurrent uploads and keeps uploading true until all settle", async () => {
    const first = deferred<DemMetadata>();
    const second = deferred<DemMetadata>();
    vi.mocked(uploadDem)
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const { manager } = createManagerWithWorkspace();

    const firstUpload = manager.upload(new File(["a"], demA.filename));
    const secondUpload = manager.upload(new File(["b"], demB.filename));
    expect(manager.uploading.value).toBe(true);

    second.resolve(demB);
    await secondUpload;
    expect(manager.uploading.value).toBe(true);

    first.resolve(demA);
    await firstUpload;
    expect(manager.uploading.value).toBe(false);
    expect(manager.dems.value).toEqual([demB, demA]);
  });

  it("does not let a pending load replace a successful upload", async () => {
    const pending = deferred<DemMetadata[]>();
    vi.mocked(listDems).mockReturnValueOnce(pending.promise);
    vi.mocked(uploadDem).mockResolvedValue(demB);
    const { manager } = createManagerWithWorkspace();

    const load = manager.load();
    await manager.upload(new File(["b"], demB.filename));
    pending.resolve([demA]);
    await load;

    expect(manager.dems.value).toEqual([demB]);
  });

  it("does not let a pending load restore a successfully deleted DEM", async () => {
    const pending = deferred<DemMetadata[]>();
    vi.mocked(listDems)
      .mockResolvedValueOnce([demA])
      .mockReturnValueOnce(pending.promise);
    vi.mocked(deleteDem).mockResolvedValue({ dem_id: demA.dem_id, deleted: true });
    const { manager } = createManagerWithWorkspace();
    await manager.load();
    manager.select(demA.dem_id);

    const load = manager.load();
    await manager.remove(demA.dem_id);
    pending.resolve([demA]);
    await load;

    expect(manager.dems.value).toEqual([]);
    expect(manager.selectedDem.value).toBeNull();
  });
});
