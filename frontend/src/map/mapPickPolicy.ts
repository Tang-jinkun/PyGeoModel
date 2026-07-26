export type MapPickTarget = "point" | "route" | "start" | "end" | "threat";

export function isCoordinateInDemBounds(
  [longitude, latitude]: [number, number],
  bounds: readonly number[]
): boolean {
  if (bounds.length !== 4) return false;
  const [west, south, east, north] = bounds;
  return longitude >= west && longitude <= east && latitude >= south && latitude <= north;
}

export function isSingleClickTarget(target: MapPickTarget): boolean {
  return target !== "route";
}
