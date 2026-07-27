# Radar Platform Scale And Overlap Visibility Design

## Goal

Make only the rendered radar platform ten times larger and make the existing multi-radar overlap result unmistakably gold above cooperative 3D results.

## Scope

- Change only `radar_platform.glb` display scale from 100 to 1000.
- Do not change radar position, height, detection range, coverage computation, or detection-domain GLB geometry.
- Render `overlap_geojson` as a gold fill with a gold outline.
- Raise the overlap map layer after cooperative 3D scene loading so the transparent detection-domain GLBs cannot visually hide it.

## Evidence

- The platform is generated independently in `backend/app/scene3d/radar_platform.py` with `DISPLAY_SCALE = 100`.
- The active multi-radar task contains one valid overlap `MultiPolygon` with nonzero area.
- The frontend currently paints that layer purple (`#7c3aed`) while cooperative 3D detection-domain GLBs visually dominate the map.

## Tests

- Radar platform metadata reports a 10x display width without changing its vertical scale contract.
- The multi-radar adapter paints overlap with gold fill and outline and can raise it above other map layers.
- Existing aggregate overlays and platform animation continue to pass their tests.
