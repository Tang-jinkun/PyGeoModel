import type maplibregl from "maplibre-gl";
import { shallowRef } from "vue";

import { fitGeoJsonBounds } from "../map/mapLayers";
import {
  createSpatialDraft,
  reduceSpatialDraft,
  type SpatialCoordinate,
  type SpatialDraft,
  type SpatialDraftAction,
  type SpatialThreat
} from "../map/spatialInput";
import type { SpatialInputKind } from "../models/shared";

export function useMapWorkspace(kind: SpatialInputKind, initialDraft?: SpatialDraft) {
  const draft = shallowRef<SpatialDraft>(initialDraft ? structuredClone(initialDraft) : createSpatialDraft(kind));

  function dispatch(action: SpatialDraftAction) {
    draft.value = reduceSpatialDraft(draft.value, action);
    return draft.value;
  }

  function pickPoint(coordinate: SpatialCoordinate) {
    return dispatch({ type: "set-point", coordinate });
  }

  function appendWaypoint(coordinate: SpatialCoordinate) {
    return dispatch({ type: "append", coordinate });
  }

  function moveWaypoint(index: number, coordinate: SpatialCoordinate) {
    return dispatch({ type: "move", index, coordinate });
  }

  function removeWaypoint(index: number) {
    return dispatch({ type: "remove", index });
  }

  function setStart(coordinate: SpatialCoordinate) {
    return dispatch({ type: "set-start", coordinate });
  }

  function setEnd(coordinate: SpatialCoordinate) {
    return dispatch({ type: "set-end", coordinate });
  }

  function addThreat(threat: SpatialThreat) {
    return dispatch({ type: "add-threat", threat });
  }

  function updateThreat(id: string, coordinate: SpatialCoordinate, properties?: Record<string, unknown>) {
    return dispatch({ type: "update-threat", id, coordinate, properties });
  }

  function removeThreat(id: string) {
    return dispatch({ type: "remove-threat", id });
  }

  function undo() {
    return dispatch({ type: "undo" });
  }

  function clear() {
    return dispatch({ type: "clear" });
  }

  function focusBounds(map: maplibregl.Map, data: GeoJSON.GeoJSON) {
    return fitGeoJsonBounds(map, data);
  }

  function replaceDraft(nextDraft: SpatialDraft) {
    draft.value = structuredClone(nextDraft);
  }

  return {
    draft,
    dispatch,
    pickPoint,
    appendWaypoint,
    moveWaypoint,
    removeWaypoint,
    setStart,
    setEnd,
    addThreat,
    updateThreat,
    removeThreat,
    undo,
    clear,
    focusBounds,
    replaceDraft
  };
}
