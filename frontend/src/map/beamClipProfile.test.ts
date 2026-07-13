import { describe, expect, it } from "vitest";

import {
  canPreviewBeam,
  clipProfileFromBounds,
  createRadiusResolver,
  radiusAtAzimuth,
  resolveBeamRenderRange
} from "./beamClipProfile";


describe("beam clip profiles", () => {
  it("interpolates through the 360 degree seam", () => {
    const profile = { azimuth_step_deg: 90, radius_m: [100, 200, 300, 400] };

    expect(radiusAtAzimuth(profile, 315, 999)).toBeCloseTo(250);
    expect(radiusAtAzimuth(profile, -45, 999)).toBeCloseTo(250);
  });

  it("clips a centered radar to rectangular DEM bounds", () => {
    const profile = clipProfileFromBounds(
      [-0.01, -0.02, 0.01, 0.02],
      { lon: 0, lat: 0 },
      10_000,
      90
    );

    expect(profile).not.toBeNull();
    expect(profile!.radius_m[0]).toBeGreaterThan(profile!.radius_m[1]);
    expect(profile!.radius_m[1]).toBeCloseTo(profile!.radius_m[3], 5);
  });

  it("returns the fallback for missing legacy profiles", () => {
    expect(radiusAtAzimuth(null, 30, 5000)).toBe(5000);
  });

  it("never resolves a clipped radius beyond the requested range", () => {
    const radius = createRadiusResolver(
      1000,
      { azimuth_step_deg: 90, radius_m: [800, 1200, 500, 900] }
    );

    expect(radius(0)).toBe(800);
    expect(radius(Math.PI / 2)).toBe(1000);
    expect(radius(Math.PI)).toBe(500);
  });

  it("caps completed-task rendering to the effective range", () => {
    expect(resolveBeamRenderRange(10_000, 2500)).toBe(2500);
    expect(resolveBeamRenderRange(10_000, 12_000)).toBe(10_000);
    expect(resolveBeamRenderRange(10_000, null)).toBe(10_000);
  });

  it("enables bounds preview only for the selected request DEM", () => {
    expect(canPreviewBeam("dem_a", "dem_a")).toBe(true);
    expect(canPreviewBeam("dem_a", "dem_b")).toBe(false);
    expect(canPreviewBeam("", "dem_a")).toBe(false);
    expect(canPreviewBeam("dem_a", null)).toBe(false);
  });
});
