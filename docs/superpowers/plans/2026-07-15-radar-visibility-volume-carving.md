# Radar Visibility Volume Carving Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export a smooth nominal radar hemisphere carved by DEM terrain, NoData, and line-of-sight shadow through a Marching Cubes visibility volume.

**Architecture:** A focused `radar_volume.py` module builds an occupancy grid from the prepared DEM and `minimum_visible_height.tif`, extracts the surface with `skimage.measure.marching_cubes`, and derives terrain and unknown boundary segments. `radar.py` consumes that geometry while retaining its ray-driven scan animation and legacy fallback; the coverage worker supplies the visibility raster.

**Tech Stack:** Python 3.12, NumPy, rasterio 1.4.3, scikit-image 0.25.2, trimesh 4.12.2, pytest 8.3.4, glTF 2.0.

## Global Constraints

- The nominal preview volume uses the effective range and a full `0` to `90` degree upper hemisphere.
- Existing request elevation limits continue to drive animated scan slices and later target evaluation.
- Invalid DEM and minimum-visible-height cells are unknown empty space, not terrain blockage.
- Runtime resolution is capped at `256 x 256 x 128`; focused tests may pass smaller explicit grid shapes.
- Use Marching Cubes at occupancy level `0.5`; do not smooth vertex positions across real visibility boundaries.
- Export terrain contact and NoData/DEM-edge boundaries as separate semantic nodes and metadata counts.
- Preserve the separate radar platform GLB, the eight-second scan animation, legacy callers, geospatial metadata, and the 50 MB preview limit.

---

### Task 1: Visibility Volume Kernel

**Files:**
- Create: `backend/app/scene3d/radar_volume.py`
- Modify: `backend/requirements.txt`
- Test: `backend/tests/test_radar_volume.py`

**Interfaces:**
- Produces: `RadarVisibilityVolume(vertices, faces, terrain_segments, unknown_segments, grid_shape, occupied_voxel_count)`.
- Produces: `build_radar_visibility_volume(prepared, payload, min_visible_height, *, grid_shape=None) -> RadarVisibilityVolume`.
- Consumes: `PreparedCoverageDem`, `CoverageRequest`, the projected DEM, and `minimum_visible_height.tif`.

- [ ] **Step 1: Write failing geometry tests**

Create a synthetic projected DEM with a central ridge, a NoData corner, and a minimum-visible-height raster whose lee side requires increasing target height. Assert that `build_radar_visibility_volume(..., grid_shape=(40, 40, 24))` produces a non-empty watertight-scale surface, contains fewer voxels than the uncarved hemisphere, has both terrain and unknown boundary segments, and reports `(40, 40, 24)` in XYZ order.

- [ ] **Step 2: Run the focused test and verify RED**

Run from `backend`:

```powershell
& 'E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe' -m pytest tests/test_radar_volume.py -v
```

Expected: collection fails because `app.scene3d.radar_volume` does not exist.

- [ ] **Step 3: Add the proven Marching Cubes dependency**

Append exactly `scikit-image==0.25.2` to `backend/requirements.txt`, install it into the existing development virtual environment, and import `skimage.measure` only in `radar_volume.py`.

- [ ] **Step 4: Implement occupancy and surface extraction**

Use an explicit `(x_count, y_count, z_count)` API while storing occupancy as `(z, y, x)`. Vectorize nominal-sphere, above-terrain, line-of-sight-threshold, scan-sector, and valid-data tests. Run `measure.marching_cubes(occupancy.astype(numpy.float32), level=0.5, spacing=(z_pitch, y_pitch, x_pitch))`, reorder returned ZYX vertices to XYZ projected coordinates, and recompute normals without changing vertex positions.

- [ ] **Step 5: Extract honest boundaries**

Intersect final mesh triangles with the sampled DEM clearance field to produce red terrain segments. Use `measure.find_contours` on the horizontal valid-data mask to produce gray unknown-boundary segments at sampled terrain height. Deduplicate zero-length segments and leave both lists empty only when that boundary class is genuinely absent.

- [ ] **Step 6: Verify GREEN and commit**

Run:

```powershell
& 'E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe' -m pytest tests/test_radar_volume.py -v
```

Expected: all radar-volume tests pass.

Commit `backend/requirements.txt`, `backend/app/scene3d/radar_volume.py`, and `backend/tests/test_radar_volume.py` with message `feat: carve radar visibility volume`.

---

### Task 2: Radar GLB And Worker Integration

**Files:**
- Modify: `backend/app/scene3d/radar.py`
- Modify: `backend/app/workers/coverage_task.py`
- Test: `backend/tests/test_radar_scene3d.py`
- Test: `backend/tests/test_coverage_task_outputs.py`

**Interfaces:**
- Consumes: `build_radar_visibility_volume(...)` from Task 1.
- Produces: `write_radar_coverage_glb(..., min_visible_height: Path | None = None) -> dict` with `visibility_volume` metadata.

- [ ] **Step 1: Write failing GLB and worker tests**

Extend the radar fixture with a matching minimum-visible-height GeoTIFF. Pass it to `write_radar_coverage_glb`, assert nodes `radar_result/detectable_shell`, `radar_result/terrain_contact`, and `radar_result/unknown_boundary` exist, and assert metadata includes `method: "marching_cubes"`, `nominal_elevation_deg: [0, 90]`, non-zero occupied voxels, faces, and both boundary counts. Spy on the worker writer and assert it receives the staged `min_visible_height` path.

- [ ] **Step 2: Run focused tests and verify RED**

Run from `backend`:

```powershell
& 'E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe' -m pytest tests/test_radar_scene3d.py tests/test_coverage_task_outputs.py -q
```

Expected: the GLB contract or worker path assertion fails against the current incomplete integration.

- [ ] **Step 3: Replace the unfinished 2D carved-dome draft**

Remove `CarvedDomeGeometry` and `_terrain_carved_dome_geometry`. When `min_visible_height` is present, call the Task 1 kernel, transform its projected vertices and boundary segments through `SceneFrame`, create separate red and gray tube meshes, and retain `_shell_mesh`/`_ground_contact_mesh` only for legacy callers.

- [ ] **Step 4: Wire the real raster and metadata**

Pass `min_visible_height=min_visible_height` from `run_coverage_task`. Record grid shape, occupied voxels, face count, terrain segment count, unknown segment count, nominal elevation, and actual scan elevation limits under `visibility_volume`. Keep all scan animation nodes and the separate platform writer unchanged.

- [ ] **Step 5: Verify GREEN, regression tests, and size**

Run:

```powershell
& 'E:\Github\PyGeoModel\backend\.venv\Scripts\python.exe' -m pytest tests/test_radar_volume.py tests/test_radar_scene3d.py tests/test_coverage_task_outputs.py -q
```

Generate the synthetic GLB test fixture and assert the file remains below 50 MB. Expected: all focused tests pass.

- [ ] **Step 6: Commit integration**

Commit the radar writer, worker, and tests with message `feat: export terrain-carved radar volume`.

---

### Task 3: Real DEM Verification

**Files:**
- Runtime only: ignored task outputs and `.superpowers/screenshots/*`.

**Interfaces:**
- Consumes: the feature Docker environment and the existing radar workbench.
- Produces: test evidence, GLB metadata/size evidence, two animation screenshots, and browser error capture.

- [ ] **Step 1: Run backend and frontend regressions**

Run the full backend pytest suite, focused frontend scene-GLB tests, and `npm run build`. Expected: all commands exit `0`.

- [ ] **Step 2: Rebuild the isolated Docker services**

Rebuild the feature compose environment without using the main checkout's `5173/8000` services. Confirm backend health before task submission.

- [ ] **Step 3: Generate and inspect a real radar task**

Run a 40 km target-independent radar task against the existing DEM, confirm both radar GLBs return `200 model/gltf-binary`, the detection GLB is below 50 MB, and its metadata reports Marching Cubes volume and both boundary classes.

- [ ] **Step 4: Capture visual evidence**

Open the feature workbench, enable detection domain and platform independently, capture two frames separated in the eight-second animation, and confirm the dome remains round while terrain/shadow regions are visibly removed. Record browser console/page errors.

- [ ] **Step 5: Commit acceptance evidence if source docs changed**

Do not commit runtime GLBs or screenshots unless the repository already tracks the relevant evidence file. Confirm `git diff --check` and a clean expected worktree before final review.

