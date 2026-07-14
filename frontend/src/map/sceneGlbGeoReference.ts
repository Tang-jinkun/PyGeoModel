import maplibregl from "maplibre-gl";
import proj4 from "proj4";

export interface Scene3dMetadata {
  schema_version: 1;
  task_id: string;
  model_id: string;
  units: "metre";
  source_crs: string;
  geographic_crs: "EPSG:4326";
  origin: {
    projected_x: number;
    projected_y: number;
    longitude: number;
    latitude: number;
    altitude_amsl_m: number;
  };
  axes: { x: "east"; y: "up"; z: "south" };
  [key: string]: unknown;
}

export interface SceneMetadataExpectation {
  taskId?: string;
  modelId?: string;
}

export interface SceneGeographicPosition {
  projected: [number, number];
  altitudeAmslM: number;
  longitude: number;
  latitude: number;
  mercator: [number, number, number];
}

export interface SceneGeoReference {
  metadata: Scene3dMetadata;
  anchor: maplibregl.MercatorCoordinate;
  project(point: readonly [number, number, number]): SceneGeographicPosition;
}

export function validateScene3dMetadata(
  value: unknown,
  expected: SceneMetadataExpectation = {}
): Scene3dMetadata {
  if (!isRecord(value) || value.schema_version !== 1) {
    throw new Error("GLB scene3d schema_version must be 1");
  }
  if (value.units !== "metre") {
    throw new Error("GLB scene3d units must be metre");
  }
  if (value.geographic_crs !== "EPSG:4326") {
    throw new Error("GLB scene3d geographic CRS must be EPSG:4326");
  }
  if (
    !isRecord(value.axes)
    || value.axes.x !== "east"
    || value.axes.y !== "up"
    || value.axes.z !== "south"
  ) {
    throw new Error("GLB scene3d axes must be X=east, Y=up, Z=south");
  }
  if (typeof value.source_crs !== "string" || utmDefinition(value.source_crs) === null) {
    throw new Error("GLB scene3d source CRS must be WGS84 UTM");
  }
  if (typeof value.task_id !== "string" || typeof value.model_id !== "string") {
    throw new Error("GLB scene3d task_id and model_id are required");
  }
  if (expected.taskId && value.task_id !== expected.taskId) {
    throw new Error("GLB scene3d task_id does not match the selected task");
  }
  if (expected.modelId && value.model_id !== expected.modelId) {
    throw new Error("GLB scene3d model_id does not match the selected model");
  }
  if (!isFiniteOrigin(value.origin)) {
    throw new Error("GLB scene3d origin must be finite");
  }
  return value as unknown as Scene3dMetadata;
}

export function createSceneGeoReference(metadata: Scene3dMetadata): SceneGeoReference {
  const definition = utmDefinition(metadata.source_crs);
  if (!definition) {
    throw new Error("GLB scene3d source CRS must be WGS84 UTM");
  }
  const inverse = proj4(definition, "EPSG:4326");
  const anchor = maplibregl.MercatorCoordinate.fromLngLat(
    { lng: metadata.origin.longitude, lat: metadata.origin.latitude },
    metadata.origin.altitude_amsl_m
  );
  return {
    metadata,
    anchor,
    project([x, y, z]) {
      const projected: [number, number] = [
        metadata.origin.projected_x + x,
        metadata.origin.projected_y - z
      ];
      const [longitude, latitude] = inverse.forward(projected);
      const altitudeAmslM = metadata.origin.altitude_amsl_m + y;
      const mercator = maplibregl.MercatorCoordinate.fromLngLat(
        { lng: longitude, lat: latitude },
        altitudeAmslM
      );
      const values = [
        longitude,
        latitude,
        altitudeAmslM,
        mercator.x,
        mercator.y,
        mercator.z
      ];
      if (!values.every(Number.isFinite)) {
        throw new Error("GLB vertex produced non-finite coordinates");
      }
      return {
        projected,
        altitudeAmslM,
        longitude,
        latitude,
        mercator: [
          mercator.x - anchor.x,
          mercator.y - anchor.y,
          mercator.z - anchor.z
        ]
      };
    }
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isFiniteOrigin(value: unknown): value is Scene3dMetadata["origin"] {
  if (!isRecord(value)) return false;
  return [
    value.projected_x,
    value.projected_y,
    value.longitude,
    value.latitude,
    value.altitude_amsl_m
  ].every((item) => typeof item === "number" && Number.isFinite(item));
}

function utmDefinition(sourceCrs: string) {
  const match = /^EPSG:(326|327)(0[1-9]|[1-5][0-9]|60)$/.exec(sourceCrs);
  if (!match) return null;
  const south = match[1] === "327";
  const zone = Number(match[2]);
  return `+proj=utm +zone=${zone} ${south ? "+south " : ""}+datum=WGS84 +units=m +no_defs`;
}
