import { describe, expect, it } from "vitest";

import { clipProfileFromBounds, radiusAtAzimuth } from "./beamClipProfile";


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
});
