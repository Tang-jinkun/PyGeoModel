# Full-Fidelity Cooperative Radar 3D Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render a completed two-to-five-station cooperative radar task with every current single-radar GLB and one gold terrain-aware common-detection intersection volume.

**Architecture:** Keep the existing aggregate worker and common visibility grid, but add an explicit `cooperative_3d` presentation mode. A cooperative task owns a normal single-radar coverage child task for every station, then exposes those completed child task IDs in station summaries. The worker writes one `coverage_count >= 2` GLB only; the client loads all station scene/platform artifacts plus that intersection artifact using the existing GLB scene layer.

**Tech Stack:** FastAPI, Pydantic, NumPy, Rasterio, Trimesh, scikit-image marching cubes, existing GLB exporter, Vue 3, TypeScript, MapLibre GL, Three.js, pytest, Vitest.

## Global Constraints

- Cooperative presentation accepts three through five radar stations; the existing aggregate mode continues to support two through 256 stations.
- Reuse the existing single-radar `scene_glb` and `radar_platform_glb` generator; do not recreate its visual geometry in the multi-radar writer.
- Cooperative fusion output is one gold `coverage_count >= 2` intersection mesh. Do not render the existing jade union mesh or 3+ coverage colour tier in cooperative mode.
- A missing common-detection intersection is valid; completed station scenes must still load.
- Existing single-radar APIs, output contracts, and scan behavior remain backward compatible.

---

### Task 1: Add an Explicit Cooperative Task Contract

**Files:**
- Modify: `backend/app/schemas/radar.py`
- Modify: `backend/app/api/radar.py`
- Modify: `frontend/src/models/multiRadar/types.ts`
- Modify: `frontend/src/api/multiRadar.ts`
- Modify: `frontend/src/components/MultiRadarPanel.vue`
- Test: `backend/tests/test_multi_radar_api.py`
- Test: `frontend/src/api/multiRadar.test.ts`
- Create: `frontend/src/components/MultiRadarPanel.test.ts`

**Interfaces:**
- Consumes: `MultiRadarRequest.radars`.
- Produces: `presentation_mode: Literal["aggregate", "cooperative_3d"]`, `MultiRadarOutputs.cooperative_intersection_glb`, and station fields `scene_task_id`, `scene_status`, and `scene_message`.

- [ ] **Step 1: Write failing schema/API tests for cooperative bounds and returned fields.**

```python
def test_cooperative_task_rejects_six_stations(client, multi_payload):
    response = client.post("/api/radar/multi-coverage", json={
        **multi_payload(6), "presentation_mode": "cooperative_3d"
    })
    assert response.status_code == 422


def test_cooperative_task_accepts_three_stations(client, multi_payload):
    response = client.post("/api/radar/multi-coverage", json={
        **multi_payload(3), "presentation_mode": "cooperative_3d"
    })
    assert response.status_code == 202
    assert response.json()["request"]["presentation_mode"] == "cooperative_3d"
```

```ts
it("posts cooperative presentation mode", async () => {
  await createMultiRadarTask({ dem_id: "dem-1", presentation_mode: "cooperative_3d", radars: stations });
  expect(fetch).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({
    body: expect.stringContaining('"presentation_mode":"cooperative_3d"')
  }));
});
```

- [ ] **Step 2: Run focused tests and confirm contract failures.**

Run: `python -m pytest tests/test_multi_radar_api.py -q` from `backend`.

Expected: FAIL because `presentation_mode` and cooperative station fields do not exist.

Run: `npm test -- src/api/multiRadar.test.ts src/components/MultiRadarPanel.test.ts` from `frontend`.

Expected: FAIL because the TypeScript request has no presentation mode.

- [ ] **Step 3: Implement the request and response types.**

```python
MultiRadarPresentationMode = Literal["aggregate", "cooperative_3d"]

class MultiRadarRequest(BaseModel):
    dem_id: str
    radars: list[MultiRadarStation] = Field(min_length=2, max_length=256)
    presentation_mode: MultiRadarPresentationMode = "aggregate"

    @model_validator(mode="after")
    def validate_cooperative_size(self):
        if self.presentation_mode == "cooperative_3d" and not 2 <= len(self.radars) <= 5:
            raise ValueError("Cooperative 3D presentation requires two to five radar stations.")
        return self
```

Add nullable `cooperative_intersection_glb` to `MultiRadarOutputs`; add nullable `scene_task_id`, `scene_status`, and `scene_message` to `MultiRadarStationSummary`. Mirror every field in the TypeScript types. In `MultiRadarPanel`, add a compact two-option mode control and submit the selected mode; validate three through five entries only when cooperative mode is selected.

- [ ] **Step 4: Re-run focused tests.**

Run: `python -m pytest tests/test_multi_radar_api.py -q` from `backend`.

Expected: PASS.

Run: `npm test -- src/api/multiRadar.test.ts src/components/MultiRadarPanel.test.ts` from `frontend`.

Expected: PASS.

- [ ] **Step 5: Commit the contract change.**

```powershell
git add backend/app/schemas/radar.py backend/app/api/radar.py backend/tests/test_multi_radar_api.py frontend/src/models/multiRadar/types.ts frontend/src/api/multiRadar.ts frontend/src/api/multiRadar.test.ts frontend/src/components/MultiRadarPanel.vue frontend/src/components/MultiRadarPanel.test.ts
git commit -m "feat: add cooperative radar presentation mode"
```

### Task 2: Write a Single Gold Intersection GLB

**Files:**
- Modify: `backend/app/services/multi_radar_fusion_volume.py`
- Test: `backend/tests/test_multi_radar_fusion_volume.py`

**Interfaces:**
- Consumes: `FusionHeightCounts.coverage_count` aligned on a common terrain grid.
- Produces: `write_cooperative_intersection_glb(path, task_id, counts) -> dict | None` and the sole mesh node `cooperative_intersection/common_detection`.

- [ ] **Step 1: Write failing writer tests.**

```python
def test_writes_one_gold_common_detection_mesh(tmp_path, fusion_counts):
    path = tmp_path / "cooperative_intersection.glb"
    metadata = write_cooperative_intersection_glb(path, task_id="multi-1", counts=fusion_counts)
    scene = trimesh.load(path, force="scene")
    assert metadata["kind"] == "cooperative_intersection"
    assert {node_name for node_name in scene.graph.nodes if "common_detection" in node_name}
    assert not {node_name for node_name in scene.graph.nodes if "union" in node_name or "triple" in node_name}


def test_returns_none_when_no_two_station_cell_exists(tmp_path, single_coverage_counts):
    assert write_cooperative_intersection_glb(tmp_path / "none.glb", task_id="multi-1", counts=single_coverage_counts) is None
```

- [ ] **Step 2: Run the focused writer test and confirm it fails.**

Run: `python -m pytest tests/test_multi_radar_fusion_volume.py -q` from `backend`.

Expected: FAIL because the cooperative writer is undefined.

- [ ] **Step 3: Implement the dedicated cooperative writer without changing the legacy writer.**

```python
COOPERATIVE_INTERSECTION_MATERIAL = MaterialSpec(
    "cooperative_common_detection_gold", (244, 176, 68, 126),
    shading="unlit", emissive_rgb=(160, 104, 24),
)

def write_cooperative_intersection_glb(path: Path, *, task_id: str, counts: FusionHeightCounts) -> dict | None:
    frame = _fusion_frame(counts)
    mesh = _coverage_mesh(counts, threshold=2, frame=frame)
    if mesh is None:
        return None
    root = SceneNode(
        name="cooperative_intersection",
        extras={"kind": "cooperative_intersection"},
        children=[SceneNode(
            name="cooperative_intersection/common_detection",
            mesh=mesh,
            material=COOPERATIVE_INTERSECTION_MATERIAL,
            extras={"kind": "common_detection", "minimum_coverage_count": 2},
        )],
    )
    metadata = frame.metadata(f"{task_id}--intersection", "radar")
    metadata.update({"kind": "cooperative_intersection", "minimum_coverage_count": 2})
    export_glb(path, [root], scene_metadata=metadata, include_normals=False)
    return metadata
```

Keep `write_multi_radar_fusion_glb` for aggregate compatibility. Do not append a union or triple node in the cooperative writer.

- [ ] **Step 4: Re-run focused writer tests.**

Run: `python -m pytest tests/test_multi_radar_fusion_volume.py -q` from `backend`.

Expected: PASS.

- [ ] **Step 5: Commit the intersection writer.**

```powershell
git add backend/app/services/multi_radar_fusion_volume.py backend/tests/test_multi_radar_fusion_volume.py
git commit -m "feat: export cooperative radar intersection volume"
```

### Task 3: Produce Complete Station Scenes as Cooperative Child Tasks

**Files:**
- Modify: `backend/app/workers/multi_radar_coverage_task.py`
- Modify: `backend/app/services/multi_radar_task_store.py`
- Test: `backend/tests/test_multi_radar_coverage_task.py`
- Test: `backend/tests/test_multi_radar_task_store.py`

**Interfaces:**
- Consumes: a cooperative `MultiRadarRequest`, station coverage requests, `run_coverage_task(task_id, request)`, and fusion height masks.
- Produces: finished coverage child task IDs in `StationEvaluation.scene_task_id`, `cooperative_intersection.glb`, and a `cooperative_intersection_glb` output URL.

- [ ] **Step 1: Write failing worker tests for automatic station artifacts and empty overlap.**

```python
def test_cooperative_worker_records_completed_scene_task_for_each_station(tmp_path, cooperative_payload, monkeypatch):
    run_multi_radar_coverage_task("multi-1", cooperative_payload)
    task = get_multi_task("multi-1")
    assert [station.scene_task_id for station in task.stations] == ["coverage-a", "coverage-b", "coverage-c"]
    assert task.outputs.cooperative_intersection_glb.endswith("cooperative_intersection.glb")


def test_cooperative_worker_completes_without_intersection_glb(tmp_path, cooperative_payload_without_overlap):
    run_multi_radar_coverage_task("multi-1", cooperative_payload_without_overlap)
    task = get_multi_task("multi-1")
    assert task.status == "finished"
    assert task.outputs.cooperative_intersection_glb is None
```

- [ ] **Step 2: Run the focused worker/store tests and confirm they fail.**

Run: `python -m pytest tests/test_multi_radar_coverage_task.py tests/test_multi_radar_task_store.py -q` from `backend`.

Expected: FAIL because no child scene task IDs or cooperative output URL are recorded.

- [ ] **Step 3: Add a bounded child-scene generation phase.**

After common-grid station evaluation succeeds, create a normal coverage task for each successful cooperative station with `create_task(station_coverage_request(payload.dem_id, station))`. Execute `run_coverage_task` with at most three worker threads, then read each child with `get_task` and attach its ID/status/message to the matching `StationEvaluation`/summary. Keep the multi task running until this phase completes, with messages of the form `Generating full scenes 2 of 3.`

Use the existing coverage task instead of copying GLB geometry into the multi worker. This is the compatibility boundary that guarantees the cooperative station shell, scan animation, and platform are byte-for-byte generated by the current single-radar pipeline.

When `payload.presentation_mode == "cooperative_3d"`, write only:

```python
intersection_path = staging_dir / "cooperative_intersection.glb"
metadata = write_cooperative_intersection_glb(intersection_path, task_id=task_id, counts=fusion_counts)
if metadata is None:
    intersection_path = None
```

Move the file to the output directory and return `cooperative_intersection_glb` only when `intersection_path` exists. Leave aggregate mode on the existing `fusion_scene_glb` code path.

- [ ] **Step 4: Re-run focused worker/store tests.**

Run: `python -m pytest tests/test_multi_radar_coverage_task.py tests/test_multi_radar_task_store.py -q` from `backend`.

Expected: PASS.

- [ ] **Step 5: Commit the cooperative artifact pipeline.**

```powershell
git add backend/app/workers/multi_radar_coverage_task.py backend/app/services/multi_radar_task_store.py backend/tests/test_multi_radar_coverage_task.py backend/tests/test_multi_radar_task_store.py
git commit -m "feat: generate full scenes for cooperative radar tasks"
```

### Task 4: Load the Whole Cooperative Scene Automatically

**Files:**
- Create: `frontend/src/models/multiRadar/cooperativeScene.ts`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/components/tasks/MultiRadarStationList.vue`
- Modify: `frontend/src/composables/useMapWorkspace.ts`
- Modify: `frontend/src/map/sceneGlbLayer.ts`
- Test: `frontend/src/models/multiRadar/cooperativeScene.test.ts`
- Test: `frontend/src/composables/useMapWorkspace.test.ts`
- Test: `frontend/src/map/sceneGlbLayer.test.ts`
- Test: `frontend/src/components/tasks/MultiRadarStationList.test.ts`

**Interfaces:**
- Consumes: cooperative station `scene_task_id` values and `cooperative_intersection_glb`.
- Produces: `loadCooperativeScene(task)`, per-station visibility state, and `focusSceneGlbLayers(map, assetIds)` for bounds covering all loaded artifacts.

- [ ] **Step 1: Write failing front-end tests.**

```ts
it("loads scene and platform GLBs for every finished cooperative station", async () => {
  await loadCooperativeScene(task);
  expect(setSceneGlbVisibility).toHaveBeenCalledTimes(6);
  expect(setSceneGlbVisibility).toHaveBeenCalledWith(map, "dem-1", "radar", stationTaskA, true, "scene_glb");
  expect(setSceneGlbVisibility).toHaveBeenCalledWith(map, "dem-1", "radar", stationTaskA, true, "radar_platform_glb");
});

it("loads gold intersection but never legacy fusion scene for cooperative tasks", async () => {
  await loadCooperativeScene(taskWithIntersection);
  expect(loadScene).toHaveBeenCalledWith(expect.objectContaining({ filename: "cooperative_intersection.glb" }));
  expect(loadScene).not.toHaveBeenCalledWith(expect.objectContaining({ filename: "fusion_scene.glb" }));
});
```

- [ ] **Step 2: Run focused tests and confirm they fail.**

Run: `npm test -- src/models/multiRadar/cooperativeScene.test.ts src/composables/useMapWorkspace.test.ts src/map/sceneGlbLayer.test.ts src/components/tasks/MultiRadarStationList.test.ts` from `frontend`.

Expected: FAIL because cooperative helpers and aggregate focusing do not exist.

- [ ] **Step 3: Implement a cooperative-scene coordinator and multi-layer focus.**

Create `cooperativeScene.ts` to convert `cooperative_intersection_glb` into the existing pseudo scene task format and to list valid station child task IDs. In `App.vue`, replace on-demand detail loading for `presentation_mode === "cooperative_3d"` with one `Promise.allSettled` load for each station `scene_glb`, `radar_platform_glb`, plus the optional intersection pseudo task. Retain the old detail endpoint behavior for aggregate tasks.

Add a multi-asset focus method in the GLB layer:

```ts
export function focusSceneGlbLayers(map: maplibregl.Map, taskIds: string[]) {
  const entries = taskIds
    .map((taskId) => registry.get(map)?.get(taskId)?.asset.bounds)
    .filter((bounds): bounds is SceneGlbBounds => Boolean(bounds));
  if (!entries.length) return false;
  map.fitBounds([[Math.min(...entries.map((b) => b.west)), Math.min(...entries.map((b) => b.south))],
    [Math.max(...entries.map((b) => b.east)), Math.max(...entries.map((b) => b.north))]],
    { padding: 60, pitch: 55, bearing: -25, duration: 800 });
  return true;
}
```

The existing `mixer.setTime(performance.now() / 1_000)` remains the shared scan clock. Use station GLB task IDs as layer asset IDs; do not add LRU removal in cooperative mode. Update the station list action from `Show scan` to a stable visibility toggle for already loaded cooperative stations.

- [ ] **Step 4: Re-run focused front-end tests.**

Run: `npm test -- src/models/multiRadar/cooperativeScene.test.ts src/composables/useMapWorkspace.test.ts src/map/sceneGlbLayer.test.ts src/components/tasks/MultiRadarStationList.test.ts` from `frontend`.

Expected: PASS.

- [ ] **Step 5: Commit the cooperative renderer.**

```powershell
git add frontend/src/models/multiRadar/cooperativeScene.ts frontend/src/models/multiRadar/cooperativeScene.test.ts frontend/src/App.vue frontend/src/components/tasks/MultiRadarStationList.vue frontend/src/components/tasks/MultiRadarStationList.test.ts frontend/src/composables/useMapWorkspace.ts frontend/src/composables/useMapWorkspace.test.ts frontend/src/map/sceneGlbLayer.ts frontend/src/map/sceneGlbLayer.test.ts
git commit -m "feat: render cooperative radar scenes together"
```

### Task 5: Verify the End-to-End Cooperative Presentation

**Files:**
- Modify: `docs/superpowers/specs/2026-07-26-multi-radar-fusion-3d-design.md` only if verification exposes a design correction.

**Interfaces:**
- Consumes: a three-station cooperative request using a DEM with nearby radar positions.
- Produces: verified task outputs, 3D scene fetches, and manual visual evidence.

- [ ] **Step 1: Run the complete backend suite.**

Run: `python -m pytest -q` from `backend`.

Expected: PASS with no failures.

- [ ] **Step 2: Run complete front-end verification.**

Run: `npm test` from `frontend`.

Expected: PASS with no failures.

Run: `npm run build` from `frontend`.

Expected: successful production build; record any pre-existing bundle-size warning separately from test failures.

- [ ] **Step 3: Rebuild and start the containers.**

Run: `docker compose up --build -d` from the worktree root.

Expected: backend is reachable on port 8000. If port 5173 is unavailable, run the preview front end on port 5174 and confirm HTTP 200.

- [ ] **Step 4: Submit and inspect one nearby three-station cooperative task.**

Use `presentation_mode: "cooperative_3d"` with three nearby radar objects. Confirm the completed task contains three finished `scene_task_id` values and, when common volume exists, a `cooperative_intersection_glb` URL. Confirm network traffic fetches every child `scene_glb` and `radar_platform_glb` plus `cooperative_intersection.glb`, and does not fetch the legacy `fusion_scene.glb`.

- [ ] **Step 5: Perform visual acceptance checks.**

Confirm the initial 3D view includes all three platforms, all three complete green terrain-aware shells, their grid/boundary/scan cues, and a gold lens/core only where domains share detection. Toggle one station off and on; its platform and shell must disappear and return without disturbing the other stations or the intersection. Rotate and zoom through the scene to verify no opaque union shell hides the individual radar visuals.

- [ ] **Step 6: Commit verification-only corrections when required.**

```powershell
git add docs/superpowers/specs/2026-07-26-multi-radar-fusion-3d-design.md
git commit -m "docs: record cooperative radar verification correction"
```
