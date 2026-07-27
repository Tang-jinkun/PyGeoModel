import { afterEach, describe, expect, it, vi } from "vitest";
import { createTaskClient } from "./tasks";

afterEach(() => vi.unstubAllGlobals());

describe("createTaskClient", () => {
  it("uses one model base path for the full lifecycle", async () => {
    const fetchMock = vi.fn().mockImplementation(() => new Response(JSON.stringify([]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const client = createTaskClient("/api/uav/recon");
    await client.list();
    await client.outputs("t-1");
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/uav/recon", "/api/uav/recon/t-1/outputs"
    ]);
  });

  it("posts an explicit rerun with the caller's idempotency key", async () => {
    const fetchMock = vi.fn().mockImplementation(() => new Response(JSON.stringify({}), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await createTaskClient("/api/uav/recon").rerun("task-1", "00000000-0000-4000-8000-000000000001");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/uav/recon/task-1/rerun",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ get: expect.any(Function) })
      })
    );
    const headers = fetchMock.mock.calls[0][1].headers as Headers;
    expect(headers.get("Idempotency-Key")).toBe("00000000-0000-4000-8000-000000000001");
  });
});
