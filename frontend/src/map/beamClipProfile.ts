import type { BeamClipProfile } from "../models/radar/types";

export type { BeamClipProfile } from "../models/radar/types";

interface RadarPosition {
  lon: number;
  lat: number;
}

export function resolveBeamRenderRange(
  requestedRangeM: number,
  effectiveRangeM: number | null | undefined
) {
  const requested = Number.isFinite(requestedRangeM) ? Math.max(0, requestedRangeM) : 0;
  if (!Number.isFinite(effectiveRangeM) || (effectiveRangeM ?? 0) <= 0) {
    return requested;
  }
  return Math.min(requested, effectiveRangeM as number);
}

export function canPreviewBeam(requestDemId: string, selectedDemId: string | null | undefined) {
  return Boolean(requestDemId && selectedDemId && requestDemId === selectedDemId);
}

export function radiusAtAzimuth(
  profile: BeamClipProfile | null | undefined,
  azimuthDeg: number,
  fallbackRadiusM: number
) {
  const fallback = Math.max(0, fallbackRadiusM);
  if (!isValidProfile(profile)) {
    return fallback;
  }
  const azimuth = ((azimuthDeg % 360) + 360) % 360;
  const fractionalIndex = azimuth / profile.azimuth_step_deg;
  const lowerIndex = Math.floor(fractionalIndex) % profile.radius_m.length;
  const upperIndex = (lowerIndex + 1) % profile.radius_m.length;
  const fraction = fractionalIndex - Math.floor(fractionalIndex);
  const lower = Math.max(0, profile.radius_m[lowerIndex]);
  const upper = Math.max(0, profile.radius_m[upperIndex]);
  return lower + (upper - lower) * fraction;
}

export function createRadiusResolver(
  maxRangeM: number,
  profile: BeamClipProfile | null | undefined
) {
  const maximum = Math.max(0, maxRangeM);
  return (azimuthRadians: number) => Math.min(
    maximum,
    radiusAtAzimuth(profile, azimuthRadians * 180 / Math.PI, maximum)
  );
}

export function clipProfileFromBounds(
  bounds: number[],
  radar: RadarPosition,
  maxRangeM: number,
  azimuthStepDeg = 2
): BeamClipProfile | null {
  if (
    bounds.length !== 4
    || !bounds.every(Number.isFinite)
    || !Number.isFinite(radar.lon)
    || !Number.isFinite(radar.lat)
    || !Number.isFinite(maxRangeM)
    || maxRangeM <= 0
    || !Number.isFinite(azimuthStepDeg)
    || azimuthStepDeg <= 0
  ) {
    return null;
  }
  const [minLon, minLat, maxLon, maxLat] = bounds;
  if (radar.lon < minLon || radar.lon > maxLon || radar.lat < minLat || radar.lat > maxLat) {
    return null;
  }

  const longitudeMeters = 111_320 * Math.max(0.01, Math.cos(radar.lat * Math.PI / 180));
  const minX = (minLon - radar.lon) * longitudeMeters;
  const maxX = (maxLon - radar.lon) * longitudeMeters;
  const minY = (minLat - radar.lat) * 111_320;
  const maxY = (maxLat - radar.lat) * 111_320;
  const sampleCount = Math.max(1, Math.round(360 / azimuthStepDeg));
  const actualStepDeg = 360 / sampleCount;
  const radiusM = Array.from({ length: sampleCount }, (_, index) => {
    const azimuthRad = index * actualStepDeg * Math.PI / 180;
    const dx = Math.sin(azimuthRad);
    const dy = Math.cos(azimuthRad);
    const candidates: number[] = [];
    if (dx > 1e-12) candidates.push(maxX / dx);
    if (dx < -1e-12) candidates.push(minX / dx);
    if (dy > 1e-12) candidates.push(maxY / dy);
    if (dy < -1e-12) candidates.push(minY / dy);
    const boundaryDistance = Math.min(...candidates.filter((value) => value >= 0));
    return Math.max(0, Math.min(maxRangeM, boundaryDistance));
  });
  return { azimuth_step_deg: actualStepDeg, radius_m: radiusM };
}

function isValidProfile(profile: BeamClipProfile | null | undefined): profile is BeamClipProfile {
  return Boolean(
    profile
    && Number.isFinite(profile.azimuth_step_deg)
    && profile.azimuth_step_deg > 0
    && profile.radius_m.length > 0
    && profile.radius_m.every(Number.isFinite)
  );
}
