import type { SpatialInputKind } from "../models/shared";

export type SpatialCoordinate = [longitude: number, latitude: number];

export interface SpatialThreat {
  id: string;
  coordinate: SpatialCoordinate;
  properties?: Record<string, unknown>;
}

interface SpatialSnapshot {
  points: SpatialCoordinate[];
  start: SpatialCoordinate | null;
  end: SpatialCoordinate | null;
  threats: SpatialThreat[];
}

export interface SpatialDraft extends SpatialSnapshot {
  kind: SpatialInputKind;
  history: SpatialSnapshot[];
}

export type SpatialDraftAction =
  | { type: "set-point"; coordinate: SpatialCoordinate }
  | { type: "append"; coordinate: SpatialCoordinate }
  | { type: "move"; index: number; coordinate: SpatialCoordinate }
  | { type: "remove"; index: number }
  | { type: "set-start"; coordinate: SpatialCoordinate }
  | { type: "set-end"; coordinate: SpatialCoordinate }
  | { type: "add-threat"; threat: SpatialThreat }
  | { type: "update-threat"; id: string; coordinate?: SpatialCoordinate; properties?: Record<string, unknown> }
  | { type: "remove-threat"; id: string }
  | { type: "undo" }
  | { type: "clear" };

export function createSpatialDraft(kind: SpatialInputKind): SpatialDraft {
  return {
    kind,
    points: [],
    start: null,
    end: null,
    threats: [],
    history: []
  };
}

export function reduceSpatialDraft(state: SpatialDraft, action: SpatialDraftAction): SpatialDraft {
  if (action.type === "undo") {
    const previous = state.history.at(-1);
    if (!previous) return cloneDraft(state);
    return {
      kind: state.kind,
      ...cloneSnapshot(previous),
      history: state.history.slice(0, -1).map(cloneSnapshot)
    };
  }

  const current = cloneSnapshot(state);
  let next: SpatialSnapshot | null = null;

  switch (action.type) {
    case "set-point":
      next = { ...current, points: [normalizeCoordinate(action.coordinate)] };
      break;
    case "append":
      next = { ...current, points: [...current.points, normalizeCoordinate(action.coordinate)] };
      break;
    case "move":
      if (!isValidIndex(action.index, current.points)) return cloneDraft(state);
      next = {
        ...current,
        points: current.points.map((point, index) => (
          index === action.index ? normalizeCoordinate(action.coordinate) : point
        ))
      };
      break;
    case "remove":
      if (!isValidIndex(action.index, current.points)) return cloneDraft(state);
      next = { ...current, points: current.points.filter((_, index) => index !== action.index) };
      break;
    case "set-start":
      next = { ...current, start: normalizeCoordinate(action.coordinate) };
      break;
    case "set-end":
      next = { ...current, end: normalizeCoordinate(action.coordinate) };
      break;
    case "add-threat":
      next = { ...current, threats: [...current.threats, normalizeThreat(action.threat)] };
      break;
    case "update-threat": {
      const threatIndex = current.threats.findIndex(({ id }) => id === action.id);
      if (threatIndex < 0) return cloneDraft(state);
      next = {
        ...current,
        threats: current.threats.map((threat, index) => index === threatIndex ? {
          id: threat.id,
          coordinate: action.coordinate ? normalizeCoordinate(action.coordinate) : cloneCoordinate(threat.coordinate),
          properties: action.properties === undefined
            ? cloneProperties(threat.properties)
            : cloneProperties(action.properties)
        } : threat)
      };
      break;
    }
    case "remove-threat":
      if (!current.threats.some(({ id }) => id === action.id)) return cloneDraft(state);
      next = { ...current, threats: current.threats.filter(({ id }) => id !== action.id) };
      break;
    case "clear":
      next = { points: [], start: null, end: null, threats: [] };
      break;
  }

  return {
    kind: state.kind,
    ...next,
    history: [...state.history.map(cloneSnapshot), current]
  };
}

export function spatialDraftToGeoJson(state: SpatialDraft): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];

  if (state.kind === "point" || state.kind === "point-or-route") {
    if (state.points.length === 1) {
      features.push(pointFeature(state.points[0], { kind: "point", index: 0 }));
    } else if (state.points.length > 1) {
      features.push({
        type: "Feature",
        properties: { kind: "route" },
        geometry: {
          type: "LineString",
          coordinates: state.points.map(cloneCoordinate)
        }
      });
    }
  }

  if (state.start) features.push(pointFeature(state.start, { kind: "start" }));
  if (state.end) features.push(pointFeature(state.end, { kind: "end" }));
  for (const threat of state.threats) {
    features.push(pointFeature(threat.coordinate, {
      ...cloneProperties(threat.properties),
      kind: "threat",
      id: threat.id
    }));
  }

  return { type: "FeatureCollection", features };
}

function normalizeCoordinate(coordinate: SpatialCoordinate): SpatialCoordinate {
  const [longitude, latitude] = coordinate;
  if (!Number.isFinite(longitude) || longitude < -180 || longitude > 180) {
    throw new RangeError("Longitude must be finite and within [-180, 180]");
  }
  if (!Number.isFinite(latitude) || latitude < -90 || latitude > 90) {
    throw new RangeError("Latitude must be finite and within [-90, 90]");
  }
  return [longitude, latitude];
}

function normalizeThreat(threat: SpatialThreat): SpatialThreat {
  return {
    id: threat.id,
    coordinate: normalizeCoordinate(threat.coordinate),
    properties: cloneProperties(threat.properties)
  };
}

function cloneDraft(state: SpatialDraft): SpatialDraft {
  return {
    kind: state.kind,
    ...cloneSnapshot(state),
    history: state.history.map(cloneSnapshot)
  };
}

function cloneSnapshot(snapshot: SpatialSnapshot): SpatialSnapshot {
  return {
    points: snapshot.points.map(cloneCoordinate),
    start: snapshot.start ? cloneCoordinate(snapshot.start) : null,
    end: snapshot.end ? cloneCoordinate(snapshot.end) : null,
    threats: snapshot.threats.map((threat) => ({
      id: threat.id,
      coordinate: cloneCoordinate(threat.coordinate),
      properties: cloneProperties(threat.properties)
    }))
  };
}

function cloneCoordinate(coordinate: SpatialCoordinate): SpatialCoordinate {
  return [coordinate[0], coordinate[1]];
}

function cloneProperties(properties?: Record<string, unknown>): Record<string, unknown> | undefined {
  return properties === undefined ? undefined : structuredClone(properties);
}

function pointFeature(
  coordinate: SpatialCoordinate,
  properties: Record<string, unknown>
): GeoJSON.Feature<GeoJSON.Point> {
  return {
    type: "Feature",
    properties,
    geometry: { type: "Point", coordinates: cloneCoordinate(coordinate) }
  };
}

function isValidIndex(index: number, values: unknown[]): boolean {
  return Number.isInteger(index) && index >= 0 && index < values.length;
}
