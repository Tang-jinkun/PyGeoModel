import { afterEach, describe, expect, it, vi } from "vitest";
import { MODEL_IDS } from "../models/registry";
import type { BaseModelRequest, TaskStatus, TaskSummary } from "../models/shared";
import { useTaskManager } from "./useTaskManager";

function task(taskId: string, status: TaskStatus, progress = 0): TaskSummary {
  return {
    task_id: taskId,
    status,
    progress,
    message: "",
    output_files: [],
    warnings: []
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve;
  });
  return { promise, resolve };
}

afterEach(() => {
  vi.useRealTimers();
});

describe("useTaskManager", () => {
  it("initializes task arrays for every registered model", () => {
    const manager = useTaskManager({ pollIntervalMs: 1000 });

    expect(Object.keys(manager.tasksByModel)).toEqual(MODEL_IDS);
    expect(MODEL_IDS.every((modelId) => manager.tasksByModel[modelId].length === 0)).toBe(true);
    manager.dispose();
  });

  it("continues polling a UAV task when the visible model changes", async () => {
    vi.useFakeTimers();
    const get = vi.fn()
      .mockResolvedValueOnce(task("u1", "running", 25))
      .mockResolvedValueOnce(task("u1", "finished", 100));
    const manager = useTaskManager({ pollIntervalMs: 1000, clientFactory: () => ({ get }) });

    manager.track("uav", task("u1", "running"));
    await vi.advanceTimersByTimeAsync(500);
    expect(get).not.toHaveBeenCalled();
    manager.setVisibleModel("radar");
    await vi.advanceTimersByTimeAsync(1500);

    expect(get).toHaveBeenCalledTimes(2);
    expect(manager.getTask("uav", "u1")?.status).toBe("finished");
    manager.dispose();
  });

  it("updates a repeated task without creating a second timer and stops on terminal state", async () => {
    vi.useFakeTimers();
    const get = vi.fn().mockResolvedValue(task("u1", "finished", 100));
    const manager = useTaskManager({ pollIntervalMs: 1000, clientFactory: () => ({ get }) });

    manager.track("uav", task("u1", "running", 10));
    await vi.advanceTimersByTimeAsync(500);
    manager.track("uav", task("u1", "running", 20));

    expect(manager.tasksByModel.uav).toHaveLength(1);
    expect(manager.getTask("uav", "u1")?.progress).toBe(20);
    expect(vi.getTimerCount()).toBe(1);

    await vi.advanceTimersByTimeAsync(500);

    expect(get).toHaveBeenCalledTimes(1);
    expect(manager.getTask("uav", "u1")?.status).toBe("finished");
    expect(vi.getTimerCount()).toBe(0);
    manager.dispose();
  });

  it("stops polling when the backend reports a failed task", async () => {
    vi.useFakeTimers();
    const get = vi.fn().mockResolvedValue(task("u1", "failed", 100));
    const manager = useTaskManager({ pollIntervalMs: 100, clientFactory: () => ({ get }) });

    manager.track("uav", task("u1", "running"));
    await vi.advanceTimersByTimeAsync(100);

    expect(manager.getTask("uav", "u1")?.status).toBe("failed");
    expect(get).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
    manager.dispose();
  });

  it("tracks and selects a submitted terminal task without scheduling a poll", async () => {
    vi.useFakeTimers();
    const created = task("r1", "finished", 100);
    const create = vi.fn().mockResolvedValue(created);
    const get = vi.fn();
    const manager = useTaskManager({ pollIntervalMs: 1000, clientFactory: () => ({ create, get }) });
    const request = { dem_id: "dem-1" };

    await expect(manager.submit("radar", request)).resolves.toBe(created);

    expect(create).toHaveBeenCalledWith(request);
    expect(manager.getTask("radar", "r1")).toEqual(created);
    expect(manager.selectedTaskKey.value).toBe("radar:r1");
    expect(vi.getTimerCount()).toBe(0);
    manager.dispose();
  });

  it("refreshes a model by replacing stale tasks and polling each nonterminal task once", async () => {
    vi.useFakeTimers();
    const list = vi.fn().mockResolvedValue([
      task("u2", "running", 20),
      task("u3", "pending")
    ]);
    const get = vi.fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockImplementation((taskId: string) => Promise.resolve(task(taskId, "finished", 100)));
    const manager = useTaskManager({
      pollIntervalMs: 100,
      maxRetryDelayMs: 500,
      clientFactory: () => ({ list, get })
    });

    manager.track("uav", task("old", "running"));
    manager.select("uav", "old");
    await vi.advanceTimersByTimeAsync(100);
    expect(manager.connectionInterrupted.value).toBe(true);

    await expect(manager.refreshModel("uav")).resolves.toEqual([
      task("u2", "running", 20),
      task("u3", "pending")
    ]);

    expect(manager.tasksByModel.uav.map(({ task_id }) => task_id)).toEqual(["u2", "u3"]);
    expect(manager.selectedTaskKey.value).toBeNull();
    expect(manager.connectionInterrupted.value).toBe(false);
    expect(vi.getTimerCount()).toBe(2);

    await vi.advanceTimersByTimeAsync(100);
    expect(get).toHaveBeenCalledTimes(3);
    expect(manager.tasksByModel.uav.every(({ status }) => status === "finished")).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
    manager.dispose();
  });

  it("keeps the newest result when overlapping refreshes resolve newest first", async () => {
    const older = deferred<TaskSummary[]>();
    const newer = deferred<TaskSummary[]>();
    const list = vi.fn()
      .mockReturnValueOnce(older.promise)
      .mockReturnValueOnce(newer.promise);
    const manager = useTaskManager({ pollIntervalMs: 100, clientFactory: () => ({ list, get: vi.fn() }) });

    const olderRefresh = manager.refreshModel("uav");
    const newerRefresh = manager.refreshModel("uav");
    newer.resolve([task("newest", "finished", 100)]);
    await newerRefresh;
    older.resolve([task("older", "finished", 100)]);
    await olderRefresh;

    expect(manager.tasksByModel.uav.map(({ task_id }) => task_id)).toEqual(["newest"]);
    manager.dispose();
  });

  it("does not reintroduce a deleted task from a pending refresh", async () => {
    vi.useFakeTimers();
    const pendingList = deferred<TaskSummary[]>();
    const list = vi.fn().mockReturnValue(pendingList.promise);
    const deleteTask = vi.fn().mockResolvedValue({
      task_id: "u1",
      deleted_task_record: true,
      deleted_output_dir: true
    });
    const manager = useTaskManager({
      pollIntervalMs: 100,
      clientFactory: () => ({ list, delete: deleteTask, get: vi.fn() })
    });
    manager.track("uav", task("u1", "finished", 100));

    const refresh = manager.refreshModel("uav");
    await manager.remove("uav", "u1");
    pendingList.resolve([task("u1", "running", 25)]);
    await refresh;

    expect(manager.getTask("uav", "u1")).toBeUndefined();
    expect(vi.getTimerCount()).toBe(0);
    manager.dispose();
  });

  it("ignores a pending refresh after disposal", async () => {
    vi.useFakeTimers();
    const pendingList = deferred<TaskSummary[]>();
    const list = vi.fn().mockReturnValue(pendingList.promise);
    const manager = useTaskManager({ pollIntervalMs: 100, clientFactory: () => ({ list, get: vi.fn() }) });

    const refresh = manager.refreshModel("uav");
    manager.dispose();
    pendingList.resolve([task("u1", "running", 25)]);
    await refresh;

    expect(manager.tasksByModel.uav).toEqual([]);
    expect(manager.connectionInterrupted.value).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("keeps a submitted task when an earlier refresh resolves later", async () => {
    vi.useFakeTimers();
    const pendingList = deferred<TaskSummary[]>();
    const submitted = task("u1", "finished", 100);
    const list = vi.fn().mockReturnValue(pendingList.promise);
    const create = vi.fn().mockResolvedValue(submitted);
    const manager = useTaskManager({
      pollIntervalMs: 100,
      clientFactory: () => ({ list, create, get: vi.fn() })
    });

    const refresh = manager.refreshModel("uav");
    await manager.submit("uav", { dem_id: "dem-1" });
    pendingList.resolve([]);
    await refresh;

    expect(manager.getTask("uav", "u1")).toEqual(submitted);
    expect(manager.selectedTaskKey.value).toBe("uav:u1");
    expect(vi.getTimerCount()).toBe(0);
    manager.dispose();
  });

  it("keeps a publicly tracked task when an earlier refresh resolves later", async () => {
    const pendingList = deferred<TaskSummary[]>();
    const list = vi.fn().mockReturnValue(pendingList.promise);
    const manager = useTaskManager({ pollIntervalMs: 100, clientFactory: () => ({ list, get: vi.fn() }) });

    const refresh = manager.refreshModel("uav");
    manager.track("uav", task("tracked", "finished", 100));
    pendingList.resolve([task("stale", "finished", 100)]);
    await refresh;

    expect(manager.tasksByModel.uav.map(({ task_id }) => task_id)).toEqual(["tracked"]);
    manager.dispose();
  });

  it("backs off failed polls to the maximum delay and resets after success", async () => {
    vi.useFakeTimers();
    const get = vi.fn()
      .mockRejectedValueOnce(new Error("offline-1"))
      .mockRejectedValueOnce(new Error("offline-2"))
      .mockRejectedValueOnce(new Error("offline-3"))
      .mockResolvedValueOnce(task("u1", "running", 50))
      .mockResolvedValue(task("u1", "finished", 100));
    const manager = useTaskManager({
      pollIntervalMs: 100,
      maxRetryDelayMs: 250,
      clientFactory: () => ({ get })
    });

    manager.track("uav", task("u1", "running"));
    await vi.advanceTimersByTimeAsync(100);
    expect(get).toHaveBeenCalledTimes(1);
    expect(manager.connectionInterrupted.value).toBe(true);

    await vi.advanceTimersByTimeAsync(199);
    expect(get).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(get).toHaveBeenCalledTimes(2);

    await vi.advanceTimersByTimeAsync(249);
    expect(get).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(1);
    expect(get).toHaveBeenCalledTimes(3);

    await vi.advanceTimersByTimeAsync(250);
    expect(get).toHaveBeenCalledTimes(4);
    expect(manager.connectionInterrupted.value).toBe(false);

    await vi.advanceTimersByTimeAsync(100);
    expect(get).toHaveBeenCalledTimes(5);
    manager.dispose();
  });

  it("keeps interruption active until every failing task recovers", async () => {
    vi.useFakeTimers();
    const attempts = new Map<string, number>();
    const get = vi.fn().mockImplementation((taskId: string) => {
      const attempt = (attempts.get(taskId) ?? 0) + 1;
      attempts.set(taskId, attempt);
      if (taskId === "u1" && attempt === 2) return Promise.resolve(task(taskId, "finished", 100));
      if (taskId === "r1" && attempt === 3) return Promise.resolve(task(taskId, "finished", 100));
      return Promise.reject(new Error(`offline-${taskId}-${attempt}`));
    });
    const manager = useTaskManager({
      pollIntervalMs: 100,
      maxRetryDelayMs: 200,
      clientFactory: () => ({ get })
    });

    manager.track("uav", task("u1", "running"));
    manager.track("radar", task("r1", "running"));
    await vi.advanceTimersByTimeAsync(100);
    expect(manager.connectionInterrupted.value).toBe(true);

    await vi.advanceTimersByTimeAsync(200);
    expect(manager.getTask("uav", "u1")?.status).toBe("finished");
    expect(manager.connectionInterrupted.value).toBe(true);

    await vi.advanceTimersByTimeAsync(200);
    expect(manager.getTask("radar", "r1")?.status).toBe("finished");
    expect(manager.connectionInterrupted.value).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
    manager.dispose();
  });

  it("retains all local state when backend deletion fails", async () => {
    vi.useFakeTimers();
    const deleteTask = vi.fn().mockRejectedValue(new Error("delete failed"));
    const get = vi.fn().mockRejectedValue(new Error("offline"));
    const manager = useTaskManager({ pollIntervalMs: 100, clientFactory: () => ({ delete: deleteTask, get }) });
    manager.track("uav", task("u1", "running"));
    manager.select("uav", "u1");
    await vi.advanceTimersByTimeAsync(100);

    await expect(manager.remove("uav", "u1")).rejects.toThrow("delete failed");

    expect(manager.getTask("uav", "u1")).toBeDefined();
    expect(manager.selectedTaskKey.value).toBe("uav:u1");
    expect(manager.connectionInterrupted.value).toBe(true);
    expect(vi.getTimerCount()).toBe(1);
    manager.dispose();
  });

  it("clears polling, failure state, and only the matching selection after deletion", async () => {
    vi.useFakeTimers();
    const deleteTask = vi.fn().mockImplementation((taskId: string) => Promise.resolve({
      task_id: taskId,
      deleted_task_record: true,
      deleted_output_dir: true
    }));
    const get = vi.fn().mockRejectedValue(new Error("offline"));
    const manager = useTaskManager({
      pollIntervalMs: 100,
      clientFactory: () => ({ delete: deleteTask, get })
    });
    manager.track("uav", task("u1", "running"));
    await vi.advanceTimersByTimeAsync(100);
    expect(manager.connectionInterrupted.value).toBe(true);
    manager.select("uav", "u1");

    await manager.remove("uav", "u1");

    expect(manager.getTask("uav", "u1")).toBeUndefined();
    expect(manager.selectedTaskKey.value).toBeNull();
    expect(manager.connectionInterrupted.value).toBe(false);
    expect(vi.getTimerCount()).toBe(0);

    manager.track("uav", task("u2", "finished", 100));
    manager.track("uav", task("u3", "finished", 100));
    manager.select("uav", "u2");
    await manager.remove("uav", "u3");
    expect(manager.selectedTaskKey.value).toBe("uav:u2");
    manager.dispose();
  });

  it("returns a deep clone of a stored request", () => {
    const manager = useTaskManager({ pollIntervalMs: 1000 });
    const request: BaseModelRequest & { nested: { value: number } } = {
      dem_id: "dem-1",
      nested: { value: 1 }
    };
    manager.track("radar", { ...task("r1", "finished", 100), request });

    const restored = manager.restoreRequest("radar", "r1") as typeof request;
    restored.nested.value = 2;

    expect(restored).not.toBe(request);
    expect(restored.nested).not.toBe(request.nested);
    expect(request.nested.value).toBe(1);
    expect(manager.restoreRequest("radar", "missing")).toBeNull();
    manager.dispose();
  });

  it("disposes idempotently and permanently prevents polling", async () => {
    vi.useFakeTimers();
    const get = vi.fn().mockRejectedValue(new Error("offline"));
    const manager = useTaskManager({ pollIntervalMs: 100, clientFactory: () => ({ get }) });
    manager.track("uav", task("u1", "running"));
    await vi.advanceTimersByTimeAsync(100);
    expect(manager.connectionInterrupted.value).toBe(true);

    manager.dispose();
    manager.dispose();
    manager.track("radar", task("r1", "running"));
    await vi.advanceTimersByTimeAsync(10_000);

    expect(get).toHaveBeenCalledTimes(1);
    expect(manager.connectionInterrupted.value).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("does not reschedule an in-flight poll after disposal", async () => {
    vi.useFakeTimers();
    let resolveGet!: (value: TaskSummary) => void;
    const get = vi.fn().mockReturnValue(new Promise<TaskSummary>((resolve) => {
      resolveGet = resolve;
    }));
    const manager = useTaskManager({ pollIntervalMs: 100, clientFactory: () => ({ get }) });
    manager.track("uav", task("u1", "running"));
    await vi.advanceTimersByTimeAsync(100);

    manager.dispose();
    resolveGet(task("u1", "running", 50));
    await Promise.resolve();
    await Promise.resolve();
    manager.track("radar", task("r1", "running"));
    await vi.advanceTimersByTimeAsync(10_000);

    expect(get).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });
});
