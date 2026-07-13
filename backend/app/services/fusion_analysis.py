import json
from pathlib import Path
from typing import Any

from pyproj import Transformer
from shapely.geometry import GeometryCollection, mapping, shape
from shapely.ops import transform as transform_geometry
from shapely.ops import unary_union

from app.core.errors import AppError
from app.schemas.radar import FusionMetrics, FusionRequest, FusionResult
from app.services.output_files import resolve_task_output_path
from app.services.projection import utm_epsg_from_lonlat
from app.services.task_store import get_task


def analyze_fusion(payload: FusionRequest) -> FusionResult:
    task_ids = list(dict.fromkeys(payload.task_ids))
    if len(task_ids) < 2:
        raise AppError("FUSION_TASK_COUNT", "At least two unique tasks are required for fusion.", status_code=400)

    contract_versions: set[int] = set()
    for task_id in task_ids:
        task = get_task(task_id)
        if task.status != "finished":
            raise AppError("TASK_NOT_FINISHED", f"Task '{task_id}' is not finished.", status_code=409)
        contract_versions.add(task.model.coverage_contract_version if task.model is not None else 1)

    if len(contract_versions) > 1:
        raise AppError(
            "FUSION_CONTRACT_MISMATCH",
            "Coverage tasks use incompatible fusion contract versions.",
            status_code=409,
        )

    visible_geometries = []
    range_geometries = []
    warnings: list[str] = []

    for task_id in task_ids:
        visible = _read_task_geometry(task_id, "visible_geojson")
        theoretical = _read_task_geometry(task_id, "range_geojson")
        if visible.is_empty:
            warnings.append(f"Task {task_id} has no visible geometry.")
        if theoretical.is_empty:
            warnings.append(f"Task {task_id} has no theoretical range geometry.")
        visible_geometries.append(visible)
        range_geometries.append(theoretical)

    center_lon, center_lat = _geometry_center([*visible_geometries, *range_geometries])
    target_epsg = utm_epsg_from_lonlat(center_lon, center_lat)
    to_projected = Transformer.from_crs("EPSG:4326", f"EPSG:{target_epsg}", always_xy=True)
    to_wgs84 = Transformer.from_crs(f"EPSG:{target_epsg}", "EPSG:4326", always_xy=True)

    visible_projected = [_project_geometry(geometry, to_projected) for geometry in visible_geometries]
    range_projected = [_project_geometry(geometry, to_projected) for geometry in range_geometries]

    visible_union = unary_union(visible_projected) if visible_projected else GeometryCollection()
    theoretical_union = unary_union(range_projected) if range_projected else GeometryCollection()
    overlap = _overlap_union(visible_projected)
    blind = theoretical_union.difference(visible_union) if not theoretical_union.is_empty else GeometryCollection()

    visible_area = _area_m2(visible_union)
    theoretical_area = _area_m2(theoretical_union)
    overlap_area = _area_m2(overlap)
    blind_area = _area_m2(blind)

    return FusionResult(
        task_ids=task_ids,
        metrics=FusionMetrics(
            task_count=len(task_ids),
            union_visible_area_m2=visible_area,
            overlap_visible_area_m2=overlap_area,
            union_theoretical_area_m2=theoretical_area,
            blind_area_m2=blind_area,
            overlap_ratio=overlap_area / visible_area if visible_area > 0 else 0,
            blind_ratio=blind_area / theoretical_area if theoretical_area > 0 else 0,
        ),
        visible_union_geojson=_feature_collection(_project_geometry(visible_union, to_wgs84), {"kind": "fusion_visible_union"}),
        overlap_geojson=_feature_collection(_project_geometry(overlap, to_wgs84), {"kind": "fusion_overlap"}),
        blind_geojson=_feature_collection(_project_geometry(blind, to_wgs84), {"kind": "fusion_blind"}),
        warnings=warnings,
    )


def _read_task_geometry(task_id: str, kind: str):
    path = resolve_task_output_path(task_id, kind)
    if not path.exists():
        raise AppError("OUTPUT_NOT_FOUND", f"Task '{task_id}' is missing output '{kind}'.", status_code=404)
    return _read_geojson_geometry(path)


def _read_geojson_geometry(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") == "FeatureCollection":
        geometries = [
            shape(feature["geometry"])
            for feature in payload.get("features", [])
            if isinstance(feature, dict) and feature.get("geometry")
        ]
        return unary_union(geometries) if geometries else GeometryCollection()
    if payload.get("type") == "Feature":
        geometry = payload.get("geometry")
        return shape(geometry) if geometry else GeometryCollection()
    return shape(payload) if payload.get("type") else GeometryCollection()


def _geometry_center(geometries) -> tuple[float, float]:
    combined = unary_union([geometry for geometry in geometries if not geometry.is_empty])
    if combined.is_empty:
        return 0.0, 0.0
    centroid = combined.centroid
    return float(centroid.x), float(centroid.y)


def _project_geometry(geometry, transformer: Transformer):
    if geometry.is_empty:
        return GeometryCollection()
    return transform_geometry(transformer.transform, geometry)


def _overlap_union(geometries):
    intersections = []
    for left_index, left in enumerate(geometries):
        if left.is_empty:
            continue
        for right in geometries[left_index + 1:]:
            if right.is_empty:
                continue
            intersection = left.intersection(right)
            if not intersection.is_empty:
                intersections.append(intersection)
    return unary_union(intersections) if intersections else GeometryCollection()


def _feature_collection(geometry, properties: dict[str, Any]) -> dict[str, Any]:
    features = []
    if not geometry.is_empty:
        features.append({"type": "Feature", "properties": properties, "geometry": mapping(geometry)})
    return {"type": "FeatureCollection", "features": features}


def _area_m2(geometry) -> float:
    return float(geometry.area) if not geometry.is_empty else 0.0
