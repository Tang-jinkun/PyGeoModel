# DEM-Clipped Theoretical Beam Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clip every radar theoretical output and solid 3D beam to the radially continuous valid DEM domain, while reporting the excluded area as unknown rather than blocked.

**Architecture:** Reproject the DEM and its validity mask onto a full requested-range canvas, then derive one authoritative radial analysis domain and compact azimuth/radius clip profile. The backend uses that domain for all masks, vectors, metrics, and fusion inputs; the frontend consumes the profile for Three.js geometry and falls back to DEM bounds for previews and legacy tasks.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, NumPy, Rasterio, Shapely, pytest, Vue 3, TypeScript, Three.js, MapLibre GL JS, Vitest, Docker Compose, Nginx.

## Global Constraints

- DEM-exterior cells are unknown: they are neither visible nor blocked.
- The analysis domain stops at the first invalid DEM sample along each radar azimuth.
- Validity comes from the raster mask/NoData metadata; negative terrain elevations remain valid.
- `radar_range.geojson`, visible/blocked outputs, height layers, voxels, and clipped volumes share one domain mask.
- Existing task records remain readable when new metrics or `beam_clip_profile` are absent.
- The full request boundary is reference-only, gray, low opacity, and disabled by default.
- Do not introduce a new geometry or GIS dependency in the frontend.
- Preserve the existing 100 km request limit and 2 degree clip-profile sampling.

---

## File Map

- Create `backend/app/services/coverage_domain.py`: pure raster-domain and azimuth-profile calculations.
- Modify `backend/app/services/coverage_model.py`: full coverage canvas, mask reprojection, radar validity checks, prepared-domain metadata.
- Modify `backend/app/workers/coverage_task.py`: common masks, clipped vectors, area identities, model profile.
- Modify `backend/app/schemas/radar.py`: backward-compatible metrics and clip-profile contracts.
- Modify `backend/tests/test_coverage_model.py`: DEM mask, full canvas, negative elevation, invalid radar tests.
- Modify `backend/tests/test_coverage_task_outputs.py`: mask partition, metrics, output geometry, profile tests.
- Modify `backend/tests/test_radar_outputs_api.py`: new and legacy JSON contract tests.
- Modify `backend/tests/test_fusion_analysis_api.py`: prove unknown exterior is not a fusion blind area.
- Create `frontend/src/map/beamClipProfile.ts`: profile interpolation and DEM-bounds fallback.
- Create `frontend/src/map/beamClipProfile.test.ts`: pure profile unit tests.
- Modify `frontend/src/api/radar.ts`: new metrics/profile types and normalization.
- Modify `frontend/src/models/radar/types.ts`: shared model metric typing.
- Modify `frontend/src/models/radar/definition.ts`: registry labels for analyzed/requested/unknown areas.
- Modify `frontend/src/map/radarVolumeLayer.ts`: per-azimuth radius geometry and optional full boundary.
- Modify `frontend/src/App.vue`: select authoritative/fallback profile and expose reference-boundary control.
- Modify `frontend/src/components/ResultPanel.vue`: display requested, analyzed, and unknown areas.
- Modify `docs/radar_coverage_metrics_api.md`: document changed semantics and new fields.

---

### Task 1: Build the Authoritative DEM Analysis Domain

**Files:**
- Create: `backend/app/services/coverage_domain.py`
- Modify: `backend/app/services/coverage_model.py`
- Test: `backend/tests/test_coverage_model.py`

**Interfaces:**
- Produces: `CoverageDomain(analysis_mask, azimuth_step_deg, radius_m)`.
- Produces: `build_coverage_domain(valid_pixels, transform, radar_x, radar_y, max_range_m, azimuth_step_deg=2.0) -> CoverageDomain`.
- Extends: `PreparedCoverageDem.analysis_domain`, `PreparedCoverageDem.beam_clip_profile_m`, and `PreparedCoverageDem.beam_clip_azimuth_step_deg`.
- Consumes later: `_coverage_masks_for_prepared` in Task 2.

- [ ] **Step 1: Write failing pure-domain tests**

Add tests that use `from_origin(-50, 50, 10, 10)` and a `10 x 10` boolean mask:

```python
def test_build_coverage_domain_stops_at_first_nodata_gap() -> None:
    valid = numpy.ones((10, 10), dtype=bool)
    valid[2, 5] = False

    domain = build_coverage_domain(valid, from_origin(-50, 50, 10, 10), 5, 5, 100, azimuth_step_deg=2)

    north_index = 0
    assert domain.radius_m[north_index] < 30
    assert not domain.analysis_mask[0, 5]


def test_build_coverage_domain_preserves_other_azimuths() -> None:
    valid = numpy.ones((10, 10), dtype=bool)
    valid[2, 5] = False

    domain = build_coverage_domain(valid, from_origin(-50, 50, 10, 10), 5, 5, 100, azimuth_step_deg=2)

    east_index = 90 // 2
    assert domain.radius_m[east_index] >= 40
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
cd backend
python -m pytest tests/test_coverage_model.py -q
```

Expected: collection fails because `app.services.coverage_domain` does not exist.

- [ ] **Step 3: Implement the pure domain module**

Create a frozen dataclass and pure helpers. Sample every ray at half the smaller pixel size, stop before the first invalid/out-of-grid sample, and rasterize the interpolated radial limit back onto cell centers:

```python
@dataclass(frozen=True)
class CoverageDomain:
    analysis_mask: numpy.ndarray
    azimuth_step_deg: float
    radius_m: tuple[float, ...]


def build_coverage_domain(valid_pixels, transform, radar_x, radar_y, max_range_m, azimuth_step_deg=2.0):
    if valid_pixels.ndim != 2 or not valid_pixels.any():
        raise ValueError("DEM valid mask is empty")
    row, col = rowcol(transform, radar_x, radar_y)
    if not _inside(valid_pixels, row, col) or not valid_pixels[row, col]:
        raise ValueError("Radar is on an invalid DEM cell")
    sample_step = max(0.01, min(abs(transform.a), abs(transform.e)) / 2)
    azimuths = numpy.arange(0.0, 360.0, azimuth_step_deg)
    radii = tuple(
        _continuous_valid_radius(valid_pixels, transform, radar_x, radar_y, azimuth, max_range_m, sample_step)
        for azimuth in azimuths
    )
    return CoverageDomain(
        analysis_mask=_profile_to_mask(valid_pixels, transform, radar_x, radar_y, radii, azimuth_step_deg),
        azimuth_step_deg=azimuth_step_deg,
        radius_m=radii,
    )
```

Keep coordinate conventions identical to the existing model: `0 deg = north`, clockwise positive.

- [ ] **Step 4: Run pure-domain tests and verify GREEN**

Run the same focused pytest command. Expected: the new domain tests pass.

- [ ] **Step 5: Write failing full-canvas and validity tests**

Add these cases to `test_coverage_model.py`:

```python
def test_prepare_coverage_dem_uses_full_requested_canvas(tmp_path: Path) -> None:
    source = tmp_path / "source.tif"
    destination = tmp_path / "projected.tif"
    write_test_dem(source)
    request = make_request(lon=105.0, lat=35.0, max_range_m=6_000)

    prepared = prepare_coverage_dem(source, destination, request)

    assert prepared.projected_bounds.left <= prepared.radar_x - 5_900
    assert prepared.projected_bounds.right >= prepared.radar_x + 5_900
    assert prepared.analysis_domain.shape == (rasterio.open(destination).height, rasterio.open(destination).width)


def test_prepare_coverage_dem_rejects_radar_on_nodata(tmp_path: Path) -> None:
    source = tmp_path / "source.tif"
    write_test_dem(source, nodata_center=True)

    with pytest.raises(AppError) as exc_info:
        prepare_coverage_dem(source, tmp_path / "projected.tif", make_request(lon=105.0, lat=35.0))

    assert exc_info.value.code == "RADAR_ON_DEM_NODATA"


def test_prepare_coverage_dem_keeps_negative_elevations_valid(tmp_path: Path) -> None:
    source = tmp_path / "source.tif"
    write_test_dem(source, elevation=-25)

    prepared = prepare_coverage_dem(source, tmp_path / "projected.tif", make_request(lon=105.0, lat=35.0))

    assert prepared.analysis_domain.any()
```

- [ ] **Step 6: Run the focused tests and verify RED**

Expected failures: cropped projected bounds, missing prepared fields, and no NoData radar error.

- [ ] **Step 7: Reproject data and mask onto a full canvas**

In `prepare_coverage_dem`:

1. Keep the source intersection window for efficient reads.
2. Derive output resolution with `calculate_default_transform`.
3. Use `from_origin(target_left, target_top, x_resolution, y_resolution)` and `ceil(range_width / resolution)` for a full requested square.
4. Reproject source values as `float32` with an explicit float NoData sentinel.
5. Reproject `(~source_data.mask).astype(uint8)` using `Resampling.nearest` into a separate in-memory validity array.
6. Write the validity array as the projected dataset mask.
7. Reject an invalid radar cell with `AppError("RADAR_ON_DEM_NODATA", ..., status_code=400)`.
8. Build `CoverageDomain` and store its mask/profile on `PreparedCoverageDem`.
9. Calculate `dem_coverage_ratio` from scan/range cells intersecting `analysis_domain`, not from the source bounding box.
10. Reject an exact ratio below `MIN_DEM_COVERAGE_RATIO` with `RANGE_OUTSIDE_DEM`; use the exact ratio in the message.

Add optional defaults for the new dataclass fields so existing focused worker fixtures remain constructible until Task 2 updates them:

```python
analysis_domain: numpy.ndarray | None = None
beam_clip_profile_m: tuple[float, ...] = ()
beam_clip_azimuth_step_deg: float = 2.0
```

- [ ] **Step 8: Run backend coverage-model tests**

Run:

```bash
cd backend
python -m pytest tests/test_coverage_model.py -q
```

Expected: all coverage-model tests pass.

- [ ] **Step 9: Commit Task 1**

```bash
git add backend/app/services/coverage_domain.py backend/app/services/coverage_model.py backend/tests/test_coverage_model.py
git commit -m "feat: derive radar analysis domain from DEM validity"
```

---

### Task 2: Apply the Domain to Outputs, Metrics, and Fusion

**Files:**
- Modify: `backend/app/schemas/radar.py`
- Modify: `backend/app/workers/coverage_task.py`
- Modify: `backend/tests/test_coverage_task_outputs.py`
- Modify: `backend/tests/test_radar_outputs_api.py`
- Modify: `backend/tests/test_fusion_analysis_api.py`

**Interfaces:**
- Produces schema: `BeamClipProfile(azimuth_step_deg: float, radius_m: list[float])`.
- Extends `CoverageMetrics` with `requested_theoretical_area_m2` and `unknown_area_m2`.
- Extends `CoverageModelMetadata` with optional `beam_clip_profile`.
- Produces mask keys: `raw_theoretical`, `analysis_domain`, `theoretical`, `unknown`, `visible`, and `blocked`.
- Consumes Task 1 fields from `PreparedCoverageDem`.

- [ ] **Step 1: Write failing mask-partition tests**

Test `_coverage_masks` directly with a `4 x 4` full theoretical beam and a domain mask whose right half is false:

```python
def test_coverage_masks_partition_unknown_from_blocked() -> None:
    data = numpy.full((4, 4), 10, dtype=numpy.float32)
    domain = numpy.ones((4, 4), dtype=bool)
    domain[:, 2:] = False

    masks = _coverage_masks(data, from_origin(-20, 20, 10, 10), 0, 0, make_request(), 100, 1000, domain)

    assert numpy.array_equal(masks["raw_theoretical"], masks["theoretical"] | masks["unknown"])
    assert not numpy.any(masks["unknown"] & masks["blocked"])
    assert numpy.array_equal(masks["theoretical"], masks["visible"] | masks["blocked"])
```

- [ ] **Step 2: Run the worker test and verify RED**

Run:

```bash
cd backend
python -m pytest tests/test_coverage_task_outputs.py -q
```

Expected: `_coverage_masks` has no domain parameter or new mask keys.

- [ ] **Step 3: Implement common mask semantics**

Change `_coverage_masks` to accept `analysis_domain`. Use:

```python
raw_theoretical = sector_mask & effective_range_mask & elevation_mask
domain_mask = analysis_domain if analysis_domain is not None else numpy.ones_like(data, dtype=bool)
theoretical_mask = raw_theoretical & domain_mask
terrain_visible = domain_mask & numpy.isfinite(data) & (data <= target_height_m)
visible_mask = theoretical_mask & terrain_visible
unknown_mask = raw_theoretical & ~domain_mask
blocked_mask = theoretical_mask & ~visible_mask
```

Return all six semantic masks plus existing primitive masks. Update height layers, voxels, clipped volume, and vector output code to use `visible` and `blocked` instead of independently recomputing differences.

- [ ] **Step 4: Run worker tests and verify GREEN**

Run the focused worker suite. Expected: partition tests and existing height-layer tests pass.

- [ ] **Step 5: Write failing schema, metric, and API compatibility tests**

Add assertions:

```python
metrics = CoverageMetrics(
    requested_theoretical_area_m2=1600,
    theoretical_area_m2=800,
    unknown_area_m2=800,
    visible_area_m2=500,
    blocked_area_m2=300,
)
assert metrics.requested_theoretical_area_m2 == metrics.theoretical_area_m2 + metrics.unknown_area_m2

legacy = CoverageTaskSummary.model_validate({
    "task_id": "task_old", "status": "finished", "metrics": {"theoretical_area_m2": 100}
})
assert legacy.metrics.unknown_area_m2 == 0
assert legacy.model is None
```

Add an API fixture whose model includes:

```json
"beam_clip_profile": {"azimuth_step_deg": 2, "radius_m": [1000, 900]}
```

Verify the task detail returns it unchanged.

- [ ] **Step 6: Run schema/API tests and verify RED**

Run:

```bash
cd backend
python -m pytest tests/test_coverage_task_outputs.py tests/test_radar_outputs_api.py -q
```

Expected: missing Pydantic fields and missing model profile.

- [ ] **Step 7: Add backward-compatible schema fields**

Implement:

```python
class BeamClipProfile(BaseModel):
    azimuth_step_deg: float = Field(default=2, gt=0, le=10)
    radius_m: list[float] = Field(default_factory=list)


class CoverageMetrics(BaseModel):
    requested_theoretical_area_m2: float = 0
    theoretical_area_m2: float = 0
    unknown_area_m2: float = 0
    # retain existing fields


class CoverageModelMetadata(BaseModel):
    # retain existing required fields
    beam_clip_profile: BeamClipProfile | None = None
```

Defaults are mandatory for old task records.

- [ ] **Step 8: Write metrics and model output from common masks**

In `_write_vector_outputs`:

```python
requested_theoretical_area = _mask_area(masks["raw_theoretical"], transform)
theoretical_area = _mask_area(masks["theoretical"], transform)
unknown_area = _mask_area(masks["unknown"], transform)
visible_area = _mask_area(masks["visible"], transform)
blocked_area = _mask_area(masks["blocked"], transform)
```

Write `radar_range.geojson` from `masks["theoretical"]`. Populate `BeamClipProfile` with Task 1 radii capped to `effective_range`. Set model `dem_coverage_ratio` to `theoretical_area / requested_theoretical_area` when the requested area is nonzero. Add a warning when unknown area is positive.

Use the same fields in `model_metadata.json` and `output_manifest.json` via existing `model_dump()` paths.

- [ ] **Step 9: Prove fusion excludes unknown exterior**

Extend the fusion test with a clipped theoretical polygon and a larger conceptual request polygon that is not written to `radar_range.geojson`. Assert `blind_geojson` bounds never exceed the clipped theoretical polygon. No fusion implementation change is expected; the test locks in use of `range_geojson`.

- [ ] **Step 10: Run all affected backend tests**

Run:

```bash
cd backend
python -m pytest tests/test_coverage_model.py tests/test_coverage_task_outputs.py tests/test_radar_outputs_api.py tests/test_fusion_analysis_api.py -q
```

Expected: all tests pass.

- [ ] **Step 11: Commit Task 2**

```bash
git add backend/app/schemas/radar.py backend/app/workers/coverage_task.py backend/tests/test_coverage_task_outputs.py backend/tests/test_radar_outputs_api.py backend/tests/test_fusion_analysis_api.py
git commit -m "feat: classify DEM-exterior radar coverage as unknown"
```

---

### Task 3: Normalize and Test Beam Clip Profiles in the Frontend

**Files:**
- Create: `frontend/src/map/beamClipProfile.ts`
- Create: `frontend/src/map/beamClipProfile.test.ts`
- Modify: `frontend/src/api/radar.ts`
- Modify: `frontend/src/models/radar/types.ts`
- Modify: `frontend/src/models/radar/definition.ts`

**Interfaces:**
- Produces TypeScript type `BeamClipProfile`.
- Produces `radiusAtAzimuth(profile, azimuthDeg, fallbackRadiusM) -> number`.
- Produces `clipProfileFromBounds(bounds, radar, maxRangeM, azimuthStepDeg=2) -> BeamClipProfile | null`.
- Consumes later: `RadarVolumeRenderOptions.clipProfile` in Task 4.

- [ ] **Step 1: Write failing interpolation and bounds tests**

Create Vitest cases:

```typescript
it("interpolates through the 360 degree seam", () => {
  const profile = { azimuth_step_deg: 90, radius_m: [100, 200, 300, 400] };
  expect(radiusAtAzimuth(profile, 315, 999)).toBeCloseTo(250);
  expect(radiusAtAzimuth(profile, -45, 999)).toBeCloseTo(250);
});

it("clips a centered radar to rectangular DEM bounds", () => {
  const profile = clipProfileFromBounds([-0.01, -0.02, 0.01, 0.02], { lon: 0, lat: 0 }, 10_000, 90)!;
  expect(profile.radius_m[0]).toBeGreaterThan(profile.radius_m[1]);
  expect(profile.radius_m[1]).toBeCloseTo(profile.radius_m[3], -1);
});

it("returns the fallback for missing legacy profiles", () => {
  expect(radiusAtAzimuth(null, 30, 5000)).toBe(5000);
});
```

- [ ] **Step 2: Run Vitest and verify RED**

Run:

```bash
cd frontend
npm test -- src/map/beamClipProfile.test.ts
```

Expected: import failure because the module does not exist.

- [ ] **Step 3: Implement pure interpolation and bounds fallback**

Use modulo-normalized azimuths and linear interpolation between adjacent samples, including wraparound. For bounds fallback, convert longitude/latitude deltas to local meters using `111_320 * cos(latitude)` for longitude and `111_320` for latitude, then compute the nearest positive ray/rectangle intersection.

Clamp every radius to `[0, maxRangeM]`; return `null` for malformed bounds or a radar outside the bounds.

- [ ] **Step 4: Run Vitest and verify GREEN**

Run the focused test file. Expected: all profile helper tests pass.

- [ ] **Step 5: Write failing API normalization tests**

Add a focused `frontend/src/api/radar.test.ts`. Export `normalizeCoverageTaskStatus` from `frontend/src/api/radar.ts` as a stable pure normalizer and test it directly:

```typescript
expect(task.metrics?.requested_theoretical_area_m2).toBe(1200);
expect(task.metrics?.unknown_area_m2).toBe(200);
expect(task.model?.beam_clip_profile?.radius_m).toEqual([1000, 900]);
```

Also verify a legacy payload normalizes missing values to zero/null.

- [ ] **Step 6: Extend frontend contracts and normalizers**

Add optional/normalized fields in `frontend/src/api/radar.ts`:

```typescript
export interface BeamClipProfile {
  azimuth_step_deg: number;
  radius_m: number[];
}
```

Normalize a profile only when its step is positive and radii are a non-empty finite number array. Add requested/unknown metrics with zero defaults. Extend `RadarMetrics` in `frontend/src/models/radar/types.ts` and add registry metric labels “Requested theoretical area” and “Unknown DEM area”. Keep `normalizeCoverageTaskSummary` private; only export the status normalizer required by the focused contract test.

- [ ] **Step 7: Run focused frontend tests and type build**

Run:

```bash
cd frontend
npm test -- src/map/beamClipProfile.test.ts
npm run build
```

Expected: focused tests and TypeScript production build pass.

- [ ] **Step 8: Commit Task 3**

```bash
git add frontend/src/map/beamClipProfile.ts frontend/src/map/beamClipProfile.test.ts frontend/src/api/radar.ts frontend/src/api/radar.test.ts frontend/src/models/radar/types.ts frontend/src/models/radar/definition.ts
git commit -m "feat: normalize radar beam clip profiles"
```

---

### Task 4: Render the Clipped Solid Beam and Optional Full Boundary

**Files:**
- Modify: `frontend/src/map/radarVolumeLayer.ts`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/components/ResultPanel.vue`
- Test: `frontend/src/map/beamClipProfile.test.ts`

**Interfaces:**
- Consumes: `BeamClipProfile`, `radiusAtAzimuth`, and `clipProfileFromBounds` from Task 3.
- Extends: `RadarVolumeRenderOptions` with `clipProfile`, `showFullRequestOutline`, and `referenceOpacity`.
- Produces: one Three.js custom layer whose solid and all decorations share the same clipped radius function.

- [ ] **Step 1: Add failing geometry-radius tests**

Export a pure `createRadiusResolver(maxRangeM, profile)` from `beamClipProfile.ts` and test:

```typescript
it("never returns a clipped radius beyond the requested range", () => {
  const radius = createRadiusResolver(1000, { azimuth_step_deg: 90, radius_m: [800, 1200, 500, 900] });
  expect(radius(0)).toBe(800);
  expect(radius(Math.PI / 2)).toBe(1000);
  expect(radius(Math.PI)).toBe(500);
});
```

- [ ] **Step 2: Run focused Vitest and verify RED**

Expected: `createRadiusResolver` is missing.

- [ ] **Step 3: Convert volume geometry to per-azimuth radii**

In `radarVolumeLayer.ts`:

1. Store the clip profile in normalized render options and rebuild on change.
2. Replace `VolumeShape.radius` with `maxRadius`, `radiusScale`, and `radiusAtAzimuth(azimuthRadians)`.
3. Change `volumePoint` to use the resolver for its azimuth.
4. Ensure main mesh, top cap, scan plane, rays, ground connectors, boundary lines, wireframe, and supplementary lobes call `volumePoint` rather than caching the old scalar radius.
5. Keep supplementary-lobe scaling by multiplying `radiusScale`, not by creating a new fixed radius.
6. Recreate the animated scan shape with the current clip profile.

- [ ] **Step 4: Add the full request reference outline**

When `showFullRequestOutline` is true, create a second un-clipped `VolumeShape` and add only gray `LineSegments` for its outer boundary. Use `referenceOpacity`; do not add a solid material or classify the outside area as blocked.

- [ ] **Step 5: Connect authoritative and fallback profiles in App.vue**

Add a `radarRequestBoundary` layer control with gray color, default `visible: false`, and description “完整请求波束参考边界”.

Track whether the displayed request came from a finished task. Profile selection order:

```typescript
const clipProfile = displayedTaskId && task.value?.model?.beam_clip_profile
  ? task.value.model.beam_clip_profile
  : clipProfileFromBounds(
      demList.value.find((item) => item.dem_id === request.dem_id)?.bounds ?? dem.value?.bounds ?? [],
      request.radar,
      request.coverage.max_range_m
    );
```

Call `addOrUpdateRadarVolume` when either the solid beam or reference boundary is visible. Pass solid opacity `0` when only the reference is enabled. Make both controls available for requests; preserve the profile-free bounds fallback for legacy task records.

- [ ] **Step 6: Update result language and metrics**

Rename user-facing labels:

- “理论波束” -> “可分析理论波束”.
- “理论范围” -> “可分析理论范围”.
- Add requested theoretical area and unknown DEM area rows/cards to `ResultPanel.vue`.
- Keep blocked ratio tied to analyzed theoretical area.

- [ ] **Step 7: Run frontend tests and build**

Run:

```bash
cd frontend
npm test
npm run build
```

Expected: all Vitest tests and production build pass.

- [ ] **Step 8: Commit Task 4**

```bash
git add frontend/src/map/radarVolumeLayer.ts frontend/src/map/beamClipProfile.test.ts frontend/src/App.vue frontend/src/components/ResultPanel.vue
git commit -m "feat: clip theoretical beam rendering to DEM domain"
```

---

### Task 5: Documentation, Full Verification, and Running Deployment

**Files:**
- Modify: `docs/radar_coverage_metrics_api.md`

**Interfaces:**
- Documents the schema and semantic identities delivered by Tasks 1-4.
- Verifies the existing Docker/Nginx public route without changing its path.

- [ ] **Step 1: Update API documentation**

Document:

```text
requested_theoretical_area_m2 = complete theoretical beam before DEM clipping
theoretical_area_m2 = requested theoretical beam inside the radially continuous DEM domain
unknown_area_m2 = requested theoretical beam outside that domain
blocked_ratio = blocked_area_m2 / theoretical_area_m2
```

Add `beam_clip_profile` to model metadata and state that old tasks omit it and use rectangular bounds fallback.

- [ ] **Step 2: Run the complete backend suite**

```bash
cd backend
python -m pytest -q
```

Expected: zero failures.

- [ ] **Step 3: Run complete frontend tests and build**

```bash
cd frontend
npm test
npm run build
```

Expected: zero test failures and successful Vite build.

- [ ] **Step 4: Rebuild and restart the containers**

```bash
docker compose up -d --build
docker compose ps
```

Expected: backend and frontend containers are `Up`; ports remain bound to `127.0.0.1` because Nginx owns the public entry point.

- [ ] **Step 5: Run public HTTP regression checks**

```bash
curl --fail --silent --show-error --output /dev/null --write-out '%{http_code}\n' http://124.221.208.30/PyGeoModel/
curl --fail --silent --show-error http://124.221.208.30/PyGeoModel/api/health
```

Expected: page returns `200`; API returns `{"status":"ok"}`.

- [ ] **Step 6: Verify Three.js rendering visually**

Use Playwright at desktop `1440 x 1000` and mobile `390 x 844`:

1. Open `http://127.0.0.1:5173/PyGeoModel/`.
2. Load a completed task or create a synthetic partial-DEM task.
3. Capture screenshots with the analyzed beam enabled and full boundary disabled, then enabled.
4. Check canvas pixels contain non-background colors in the DEM region and no solid beam color beyond the DEM boundary.
5. Confirm controls and labels do not overlap at either viewport.

Expected: nonblank moving Three.js scene, clipped solid envelope, optional gray full boundary, no incoherent overlaps.

- [ ] **Step 7: Commit documentation**

```bash
git add docs/radar_coverage_metrics_api.md
git commit -m "docs: explain DEM-clipped radar coverage metrics"
```

- [ ] **Step 8: Final repository check**

```bash
git status --short
git log -6 --oneline
```

Expected: clean worktree and task commits visible above the design/plan commits.
