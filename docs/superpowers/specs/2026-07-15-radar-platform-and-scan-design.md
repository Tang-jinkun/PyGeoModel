# Radar Platform And Scan Design

## Goal

Export a small realistic radar platform as a standalone GLB and make the separate radar detection-domain GLB visually full and animated with data-driven scanning slices whose lengths vary by terrain, NoData, scan limits, and radar performance.

## Output Contract

- `radar_detection_domain.glb` remains the target-independent detection result.
- `radar_platform.glb` is a second self-contained output with the same scene3d geospatial anchor.
- Both files remain below the existing 50 MB preview limit and are independently downloadable and toggleable.
- Legacy radar tasks without `radar_platform_glb` retain their existing single-GLB or legacy volume behavior.

## Detection Domain

The outer terrain-clipped shell remains authoritative. A sparse internal sample cloud is generated only along valid closed rays and stops at each ray endpoint, so it cannot fill NoData openings or terrain-shadow gaps. A rotating scan slice is generated per 3-degree azimuth cell from the actual elevation-dependent ray endpoints; short and long slices therefore come from model results, not random visual scaling.

The scan animation uses standard glTF TRS animation. Only the current slice and a short trailing slice are visible. The full rotation period is eight seconds and is recorded in metadata.

## Radar Platform

The radar uses physical-scale procedural PBR geometry: equipment cabinet, pedestal, turntable, mast, parabolic dish, and feed arm. Static base nodes remain fixed while rotating nodes carry a standard eight-second azimuth animation around the glTF Y-up axis. The radar is not merged into the detection-domain file.

## Frontend

The existing scene GLB pipeline is generalized from one asset per task to one asset per output kind. The workbench presents independent controls for detection domain and radar platform, supports animation playback with a shared wall-clock phase, and preserves focus/download behavior. Static GLBs continue to load unchanged.

## Verification

- Backend exporter test proves animation accessors/channels target named nodes.
- Radar scene test proves two GLB outputs, fill geometry, scan animation, and varying slice ranges.
- Frontend tests prove animated GLBs load and both radar assets can be independently toggled.
- A real DEM task is generated and checked in the workbench with a desktop screenshot and browser error capture.

