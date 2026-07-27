# Radar Visibility Volume Carving Design

## Goal

Replace the terrain-draped radar preview with a smooth nominal detection dome that is carved by terrain, NoData, and terrain line-of-sight shadow. The result must read as a continuous radar volume with natural mountain-shaped bites rather than a surface following DEM elevation or a fan of ray seams.

## Physical Model

The exported preview volume is:

```text
nominal upper-hemisphere volume
INTERSECT valid DEM space above local terrain
INTERSECT terrain line-of-sight reachable space
```

The nominal volume uses the effective range from the existing radar-equation/range calculation and a full 0 to 90 degree upper hemisphere. This represents the target-independent maximum detection domain. Existing request elevation limits continue to govern the animated scan slices and later target evaluation, and are recorded separately in metadata.

Terrain line of sight comes from the existing `minimum_visible_height.tif`. At each horizontal sample, a voxel is visible only when its altitude is at or above both local DEM elevation and `terrain + minimum_visible_agl`. Invalid DEM or minimum-visible-height cells remain empty, so NoData never becomes terrain blockage.

## Volume And Surface Extraction

The volume builder uses a regular projected-coordinate grid. Runtime resolution is capped at `256 x 256 x 128`; the horizontal resolution follows `advanced.voxel_grid_size` with a minimum useful preview size, and the vertical resolution follows `advanced.voxel_vertical_levels` with a higher preview floor. Focused tests use smaller explicit shapes.

`skimage.measure.marching_cubes` extracts the 0.5 occupancy isosurface. The result is transformed from array coordinates to projected XYZ, then into the existing Y-up glTF scene frame. Geometry is not Laplacian-smoothed because that would move real shadow boundaries. Vertex normals may be recomputed for smooth lighting. Empty or degenerate occupancy raises a clear task error rather than publishing a misleading fallback.

The existing ray grid remains authoritative for animated scan slices and diagnostics. It no longer creates the detection shell when a minimum-visible-height raster is available. Legacy direct callers without that raster retain the current ray-shell fallback.

## Boundary Semantics

Red terrain-contact lines come from the final extracted surface intersecting the DEM height field. They include the outer ground contact and internal ridge/valley contacts where terrain enters the nominal volume.

Gray unknown-boundary lines mark transitions between valid DEM samples and NoData or the DEM edge. They are exported as a separate semantic node and material so unknown space is not presented as terrain shadow. The two boundary classes are recorded separately in metadata.

## Integration

`write_radar_coverage_glb` accepts the existing `minimum_visible_height.tif` path. `coverage_task` passes the staged raster after height layers and voxels have been generated. The GLB keeps the existing output kind, animation, platform separation, geospatial metadata, and 50 MB preview limit.

The radar detection metadata records the volume grid shape, occupied voxel count, extracted face count, boundary segment counts, `nominal_elevation_deg: [0, 90]`, and the request's actual scan elevation limits.

## Verification

- A synthetic ridge fixture proves that the carved volume contains a terrain/shadow bite while retaining a smooth nominal outer surface.
- GLB tests prove Marching Cubes metadata, red terrain-contact geometry, gray unknown-boundary geometry, animation preservation, and self-contained buffers.
- Worker tests prove `minimum_visible_height.tif` is passed to the GLB writer.
- A real DEM task is rebuilt and visually checked from two animation frames with browser errors captured.

