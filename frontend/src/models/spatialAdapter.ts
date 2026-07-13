import type { SpatialCoordinate, SpatialDraft, SpatialThreat } from "../map/spatialInput";
import type { AirDefenseThreatInput } from "./airCorridor/types";
import type { ModelId, ModelRequestMap } from "./registry";

export function spatialDraftFromRequest<K extends ModelId>(
  modelId: K,
  request: ModelRequestMap[K]
): SpatialDraft {
  switch (modelId) {
    case "radar":
      return pointDraft("point", coordinate((request as ModelRequestMap["radar"]).radar));
    case "watchpost":
      return pointDraft("point", coordinate((request as ModelRequestMap["watchpost"]).observer));
    case "artillery":
      return pointDraft("point", coordinate((request as ModelRequestMap["artillery"]).battery));
    case "uav": {
      const value = request as ModelRequestMap["uav"];
      const points = value.route?.waypoints.length
        ? value.route.waypoints.map(coordinate)
        : [coordinate(value.uav)];
      return pointDraft("point-or-route", ...points);
    }
    case "reconVehicle": {
      const value = request as ModelRequestMap["reconVehicle"];
      const points = value.route?.waypoints.length
        ? value.route.waypoints.map(coordinate)
        : [coordinate(value.vehicle)];
      return pointDraft("point-or-route", ...points);
    }
    case "mobility": {
      const value = request as ModelRequestMap["mobility"];
      return {
        kind: "start-end",
        points: [],
        start: coordinate(value.start),
        end: coordinate(value.end),
        threats: [],
        history: []
      };
    }
    case "airCorridor": {
      const value = request as ModelRequestMap["airCorridor"];
      return {
        kind: "start-end-threats",
        points: [],
        start: coordinate(value.start),
        end: coordinate(value.end),
        threats: value.threats.map(threatFromRequest),
        history: []
      };
    }
  }
  throw new Error(`Unsupported model: ${modelId}`);
}

export function applySpatialDraftToRequest<K extends ModelId>(
  modelId: K,
  source: ModelRequestMap[K],
  draft: SpatialDraft
): ModelRequestMap[K] {
  const request = structuredClone(source) as ModelRequestMap[K];
  switch (modelId) {
    case "radar": {
      const value = request as ModelRequestMap["radar"];
      assignCoordinate(value.radar, draft.points[0]);
      break;
    }
    case "watchpost": {
      const value = request as ModelRequestMap["watchpost"];
      assignCoordinate(value.observer, draft.points[0]);
      break;
    }
    case "artillery": {
      const value = request as ModelRequestMap["artillery"];
      assignCoordinate(value.battery, draft.points[0]);
      break;
    }
    case "uav": {
      const value = request as ModelRequestMap["uav"];
      if (draft.points.length === 0) {
        value.route = null;
      } else if (draft.points.length === 1) {
        assignCoordinate(value.uav, draft.points[0]);
        value.route = null;
      } else if (draft.points.length > 1) {
        const oldWaypoints = value.route?.waypoints ?? [];
        value.route = {
          sample_interval_m: value.route?.sample_interval_m ?? 100,
          waypoints: draft.points.map((point, index) => withCoordinate(
            oldWaypoints[index] ?? value.uav,
            point
          ))
        };
        value.uav = { ...value.route.waypoints[0] };
      }
      break;
    }
    case "reconVehicle": {
      const value = request as ModelRequestMap["reconVehicle"];
      if (draft.points.length === 0) {
        value.route = null;
      } else if (draft.points.length === 1) {
        assignCoordinate(value.vehicle, draft.points[0]);
        value.route = null;
      } else if (draft.points.length > 1) {
        const oldWaypoints = value.route?.waypoints ?? [];
        value.route = {
          sample_interval_m: value.route?.sample_interval_m ?? 100,
          waypoints: draft.points.map((point, index) => withCoordinate(
            oldWaypoints[index] ?? value.vehicle,
            point
          ))
        };
        value.vehicle = { ...value.route.waypoints[0] };
      }
      break;
    }
    case "mobility": {
      const value = request as ModelRequestMap["mobility"];
      assignCoordinate(value.start, draft.start ?? undefined);
      assignCoordinate(value.end, draft.end ?? undefined);
      break;
    }
    case "airCorridor": {
      const value = request as ModelRequestMap["airCorridor"];
      assignCoordinate(value.start, draft.start ?? undefined);
      assignCoordinate(value.end, draft.end ?? undefined);
      const oldThreats = new Map(value.threats.map((threat) => [threat.id, threat]));
      value.threats = draft.threats.map((threat) => threatToRequest(threat, oldThreats.get(threat.id)));
      break;
    }
  }
  return request;
}

function pointDraft(kind: "point" | "point-or-route", ...points: SpatialCoordinate[]): SpatialDraft {
  return { kind, points, start: null, end: null, threats: [], history: [] };
}

function coordinate(value: { lon: number; lat: number }): SpatialCoordinate {
  return [value.lon, value.lat];
}

function assignCoordinate(value: { lon: number; lat: number }, point?: SpatialCoordinate) {
  if (!point) return;
  [value.lon, value.lat] = point;
}

function withCoordinate<T extends { lon: number; lat: number }>(value: T, point: SpatialCoordinate): T {
  return { ...value, lon: point[0], lat: point[1] };
}

function threatFromRequest(threat: AirDefenseThreatInput): SpatialThreat {
  const { id, lon, lat, ...properties } = threat;
  return { id, coordinate: [lon, lat], properties };
}

function threatToRequest(threat: SpatialThreat, fallback?: AirDefenseThreatInput): AirDefenseThreatInput {
  const properties = threat.properties as Partial<Omit<AirDefenseThreatInput, "id" | "lon" | "lat">> | undefined;
  return {
    id: threat.id,
    name: properties?.name ?? fallback?.name ?? null,
    lon: threat.coordinate[0],
    lat: threat.coordinate[1],
    min_range_m: properties?.min_range_m ?? fallback?.min_range_m ?? 0,
    max_range_m: properties?.max_range_m ?? fallback?.max_range_m ?? 1,
    min_altitude_m: properties?.min_altitude_m ?? fallback?.min_altitude_m ?? 0,
    max_altitude_m: properties?.max_altitude_m ?? fallback?.max_altitude_m ?? 1,
    threat_level: properties?.threat_level ?? fallback?.threat_level ?? 1,
    kill_zone_radius_m: properties?.kill_zone_radius_m ?? fallback?.kill_zone_radius_m ?? null,
    warning_zone_radius_m: properties?.warning_zone_radius_m ?? fallback?.warning_zone_radius_m ?? null
  };
}
