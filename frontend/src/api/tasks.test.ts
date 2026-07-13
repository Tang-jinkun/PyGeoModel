import { afterEach, describe, expect, it, vi } from "vitest";
import { createTaskClient } from "./tasks";

afterEach(() => vi.unstubAllGlobals());

describe("createTaskClient", () => {
  it("uses one model base path for the full lifecycle", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const client = createTaskClient("/api/uav/recon");
    await client.list();
    await client.outputs("t-1");
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/uav/recon", "/api/uav/recon/t-1/outputs"
    ]);
  });
});
