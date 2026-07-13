import { airCorridorDefinition } from "./airCorridor/definition";
import type { AirCorridorMetrics, AirCorridorRequest } from "./airCorridor/types";
import { artilleryDefinition } from "./artillery/definition";
import type { ArtilleryMetrics, ArtilleryRequest } from "./artillery/types";
import { mobilityDefinition } from "./mobility/definition";
import type { MobilityMetrics, MobilityRequest } from "./mobility/types";
import { radarDefinition } from "./radar/definition";
import type { RadarMetrics, RadarRequest } from "./radar/types";
import { reconVehicleDefinition } from "./reconVehicle/definition";
import type { ReconVehicleMetrics, ReconVehicleRequest } from "./reconVehicle/types";
import { MODEL_IDS, type ModelDefinition, type ModelId } from "./shared";
import { uavDefinition } from "./uav/definition";
import type { UavMetrics, UavRequest } from "./uav/types";
import { watchpostDefinition } from "./watchpost/definition";
import type { WatchpostMetrics, WatchpostRequest } from "./watchpost/types";

export { MODEL_IDS } from "./shared";
export type { ModelDefinition, ModelId } from "./shared";

export interface ModelRequestMap {
  radar: RadarRequest; uav: UavRequest; watchpost: WatchpostRequest; artillery: ArtilleryRequest;
  reconVehicle: ReconVehicleRequest; mobility: MobilityRequest; airCorridor: AirCorridorRequest;
}
export interface ModelMetricMap {
  radar: RadarMetrics; uav: UavMetrics; watchpost: WatchpostMetrics; artillery: ArtilleryMetrics;
  reconVehicle: ReconVehicleMetrics; mobility: MobilityMetrics; airCorridor: AirCorridorMetrics;
}

export const MODEL_REGISTRY = {
  radar: radarDefinition,
  uav: uavDefinition,
  watchpost: watchpostDefinition,
  artillery: artilleryDefinition,
  reconVehicle: reconVehicleDefinition,
  mobility: mobilityDefinition,
  airCorridor: airCorridorDefinition
} satisfies { [K in ModelId]: ModelDefinition<ModelRequestMap[K], ModelMetricMap[K]> };

export function getModelDefinition<K extends ModelId>(id: K) {
  return MODEL_REGISTRY[id];
}
