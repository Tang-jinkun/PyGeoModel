export interface LoadedHeightLayer {
  visible: GeoJSON.GeoJSON;
  blocked: GeoJSON.GeoJSON | null;
}

export function createHeightLayerLoader(
  fetchGeoJson: (url: string) => Promise<GeoJSON.GeoJSON>
) {
  const cache = new Map<number, LoadedHeightLayer>();
  const pending = new Map<number, Promise<LoadedHeightLayer | null>>();
  let taskId: string | null = null;
  let generation = 0;

  function setTask(nextTaskId: string | null) {
    if (taskId === nextTaskId) return;
    taskId = nextTaskId;
    generation++;
    cache.clear();
    pending.clear();
  }

  function load(heightM: number, visibleUrl: string, blockedUrl: string | null) {
    const cached = cache.get(heightM);
    if (cached) return Promise.resolve(cached);
    const existing = pending.get(heightM);
    if (existing) return existing;

    const expectedTaskId = taskId;
    const expectedGeneration = generation;
    let request!: Promise<LoadedHeightLayer | null>;
    request = Promise.all([
      fetchGeoJson(visibleUrl),
      blockedUrl ? fetchGeoJson(blockedUrl) : Promise.resolve(null)
    ]).then(([visible, blocked]) => {
      if (generation !== expectedGeneration || taskId !== expectedTaskId) return null;
      const loaded = { visible, blocked };
      cache.set(heightM, loaded);
      return loaded;
    }).finally(() => {
      if (pending.get(heightM) === request) pending.delete(heightM);
    });
    pending.set(heightM, request);
    return request;
  }

  return { setTask, load };
}
