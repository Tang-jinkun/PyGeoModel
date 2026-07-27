# Radar Platform Scale And Overlap Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Increase only radar platform display size by 10x and show multi-radar overlap in gold above cooperative 3D imagery.

**Architecture:** The backend retains its existing independent platform GLB generator and changes only its display-scale constant. The frontend keeps overlap as GeoJSON but gives it a gold fill/outline and moves it after 3D scene creation.

**Tech Stack:** Python, trimesh GLB export, Vue TypeScript, MapLibre/Mapbox APIs, pytest, Vitest.

## Global Constraints

- Detection calculations and detection-domain GLB geometry remain unchanged.
- Only the platform's horizontal display scale changes.
- The overlap output artifact and its topology remain unchanged.

---

### Task 1: Scale Only The Radar Platform

**Files:**
- Modify: `backend/app/scene3d/radar_platform.py`
- Modify: `backend/tests/test_radar_scene3d.py`

- [ ] **Step 1: Write a failing metadata assertion**

```py
assert platform_metadata["dimensions_m"]["width"] == 5.5 * 1000
```

- [ ] **Step 2: Verify red**

Run: `python -m pytest backend/tests/test_radar_scene3d.py -k radar_platform`

Expected: FAIL because width is based on 100.

- [ ] **Step 3: Implement the constant change**

```py
DISPLAY_SCALE = 1000.0
```

- [ ] **Step 4: Verify green and commit**

Run: `python -m pytest backend/tests/test_radar_scene3d.py -k radar_platform`

Commit: `git add backend/app/scene3d/radar_platform.py backend/tests/test_radar_scene3d.py && git commit -m "feat: enlarge radar platform display"`

### Task 2: Make The Overlap Gold And Foregrounded

**Files:**
- Modify: `frontend/src/map/multiRadarLayerAdapter.ts`
- Modify: `frontend/src/map/multiRadarLayerAdapter.test.ts`
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Write a failing adapter assertion**

```ts
expect(map.addLayer).toHaveBeenCalledWith(expect.objectContaining({
  id: "multi-radar-overlap",
  paint: expect.objectContaining({ "fill-color": "#d4a017", "fill-outline-color": "#facc15" })
}));
```

- [ ] **Step 2: Verify red**

Run: `npm run test -- --run src/map/multiRadarLayerAdapter.test.ts`

Expected: FAIL because overlap is purple and has no gold outline assertion.

- [ ] **Step 3: Implement gold paint and raise operation**

Use gold fill `#d4a017`, opacity `0.58`, and outline `#facc15`. Add `raiseLayer(map, "overlap_geojson")` to the adapter, calling `map.moveLayer("multi-radar-overlap")`; invoke it after cooperative or fusion GLB creation completes.

- [ ] **Step 4: Verify green and commit**

Run: `npm run test -- --run src/map/multiRadarLayerAdapter.test.ts src/App.test.ts`

Commit: `git add frontend/src/map/multiRadarLayerAdapter.ts frontend/src/map/multiRadarLayerAdapter.test.ts frontend/src/App.vue && git commit -m "fix: foreground multi-radar overlap"`
