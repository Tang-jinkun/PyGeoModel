from pathlib import Path

import numpy
import pytest
from pyproj import Transformer
from shapely.geometry import Point
import trimesh

from app.scene3d import air_corridor as air_corridor_scene
from app.scene3d.air_corridor import write_air_corridor_glb
from app.scene3d.exporter import read_glb_document
from app.schemas.air_corridor import AirCorridorPlanningRequest


def sample_features(risks: list[float]) -> list[dict]:
    coordinates = [
        (500_000.0, 3_500_000.0, 6200.0),
        (501_000.0, 3_500_200.0, 6800.0),
        (502_000.0, 3_500_000.0, 6400.0),
    ]
    return [
        {
            "geometry": Point(x, y),
            "properties": {
                "index": index,
                "altitude_amsl_m": altitude,
                "risk": risk,
            },
        }
        for index, ((x, y, altitude), risk) in enumerate(zip(coordinates, risks))
    ]


def payload_with_two_threats() -> AirCorridorPlanningRequest:
    return AirCorridorPlanningRequest(
        dem_id="dem_a",
        start={"lon": 79.8, "lat": 31.48, "altitude_m": 6200, "altitude_mode": "amsl"},
        end={"lon": 79.82, "lat": 31.48, "altitude_m": 6400, "altitude_mode": "amsl"},
        threats=[
            {
                "id": "a",
                "lon": 79.81,
                "lat": 31.48,
                "min_range_m": 0,
                "max_range_m": 3000,
                "min_altitude_m": 5500,
                "max_altitude_m": 7200,
                "kill_zone_radius_m": 1200,
                "warning_zone_radius_m": 2400,
            },
            {
                "id": "b",
                "lon": 79.815,
                "lat": 31.481,
                "min_range_m": 300,
                "max_range_m": 3500,
                "min_altitude_m": 5700,
                "max_altitude_m": 7400,
                "kill_zone_radius_m": 1400,
                "warning_zone_radius_m": 2800,
            },
        ],
        planning={"corridor_width_m": 500},
    )


def payload_with_one_threat() -> AirCorridorPlanningRequest:
    return AirCorridorPlanningRequest(
        dem_id="dem_a",
        start={"lon": 79.8, "lat": 31.48, "altitude_m": 300, "altitude_mode": "agl"},
        end={"lon": 79.82, "lat": 31.48, "altitude_m": 400, "altitude_mode": "agl"},
        threats=[
            {
                "id": "a",
                "lon": 79.81,
                "lat": 31.48,
                "max_range_m": 3000,
                "min_altitude_m": 5500,
                "max_altitude_m": 7200,
                "kill_zone_radius_m": 1200,
                "warning_zone_radius_m": 2400,
            }
        ],
        planning={"corridor_width_m": 500},
    )


def test_air_corridor_scene_writes_semantic_nodes(tmp_path: Path) -> None:
    output = tmp_path / "air_corridor_result.glb"
    metadata = write_air_corridor_glb(
        output,
        task_id="air_corridor_task_a",
        target_epsg=32644,
        path_points=[
            (500_000, 3_500_000, 6200),
            (501_000, 3_500_200, 6800),
            (502_000, 3_500_000, 6400),
        ],
        sample_features=sample_features([0.0, 5.0, 10.0]),
        prepared_threat_xy={
            "a": (501_000, 3_500_000),
            "b": (501_500, 3_500_300),
        },
        threat_ground_elevations_m={"a": 5900, "b": 6000},
        start_ground_elevation_m=5900,
        end_ground_elevation_m=6000,
        payload=payload_with_two_threats(),
        route_found=True,
    )
    scene = trimesh.load(output, force="scene")
    names = set(scene.graph.nodes_geometry)
    document = read_glb_document(output.read_bytes())
    nodes_by_name = {node["name"]: node for node in document["nodes"]}

    assert {
        "corridor_path",
        "corridor_ribbon",
        "risk_low",
        "risk_medium",
        "risk_high",
        "start",
        "end",
    } <= names
    assert metadata["route_found"] is True
    assert metadata["risk_sample_count"] == 3
    assert metadata["tactical_unit_count"] == 2
    assert metadata["omitted_units"] == []
    for unit_id in ("a", "b"):
        root = nodes_by_name[f"unit_{unit_id}"]
        roles = {
            document["nodes"][index]["extras"]["role"]
            for index in root["children"]
        }
        assert roles == {
            "model",
            "symbol_cross",
            "label_cross",
            "warning_zone",
            "kill_zone",
        }
    assert "threat_a_warning" not in nodes_by_name

    materials = {material["name"]: material for material in document["materials"]}
    semantic_materials = {
        "corridor_path",
        "corridor_ribbon",
        "risk_low",
        "risk_medium",
        "risk_high",
        "start",
        "end",
        "unit_warning_zone",
        "unit_kill_zone",
        "tactical_symbol_backplate",
        "tactical_symbol_threat",
    }
    for material_name in semantic_materials:
        material = materials[material_name]
        assert material["extensions"]["KHR_materials_unlit"] == {}
        assert len(material["emissiveFactor"]) == 3


def test_route_found_scene_marks_requested_terminals(tmp_path: Path) -> None:
    output = tmp_path / "air_corridor_result.glb"
    payload = payload_with_two_threats()
    write_air_corridor_glb(
        output,
        task_id="air_corridor_task_a",
        target_epsg=32644,
        path_points=[
            (500_000, 3_500_000, 6200),
            (501_000, 3_500_200, 6800),
            (502_000, 3_500_000, 6400),
        ],
        sample_features=sample_features([0.0, 5.0, 10.0]),
        prepared_threat_xy={
            "a": (501_000, 3_500_000),
            "b": (501_500, 3_500_300),
        },
        threat_ground_elevations_m={"a": 5900, "b": 6000},
        start_ground_elevation_m=5900,
        end_ground_elevation_m=6000,
        payload=payload,
        route_found=True,
    )
    scene = trimesh.load(output, force="scene")
    document = read_glb_document(output.read_bytes())
    origin = document["asset"]["extras"]["scene3d"]["origin"]
    to_target = Transformer.from_crs("EPSG:4326", "EPSG:32644", always_xy=True)

    for name, terminal in (("start", payload.start), ("end", payload.end)):
        x, y = to_target.transform(terminal.lon, terminal.lat)
        expected = numpy.asarray(
            [
                x - origin["projected_x"],
                terminal.altitude_m - origin["altitude_amsl_m"],
                -(y - origin["projected_y"]),
            ]
        )
        assert numpy.allclose(scene.geometry[name].vertices.mean(axis=0), expected)


def test_route_not_found_scene_contains_context_only(tmp_path: Path) -> None:
    output = tmp_path / "air_corridor_result.glb"
    write_air_corridor_glb(
        output,
        task_id="air_corridor_task_a",
        target_epsg=32644,
        path_points=[],
        sample_features=[],
        prepared_threat_xy={"a": (501_000, 3_500_000)},
        threat_ground_elevations_m={"a": 6100},
        start_ground_elevation_m=5900,
        end_ground_elevation_m=6000,
        payload=payload_with_one_threat(),
        route_found=False,
    )
    names = set(trimesh.load(output, force="scene").graph.nodes_geometry)

    assert {
        "start",
        "end",
        "unit_a/warning_zone",
        "unit_a/kill_zone",
    } <= names
    assert "corridor_path" not in names


def test_threat_body_uses_ground_anchor_while_zones_keep_absolute_altitudes(
    tmp_path: Path,
) -> None:
    output = tmp_path / "air_corridor_result.glb"
    payload = payload_with_one_threat()
    payload.threats[0].min_altitude_m = 0
    write_air_corridor_glb(
        output,
        task_id="air_corridor_task_a",
        target_epsg=32644,
        path_points=[],
        sample_features=[],
        prepared_threat_xy={"a": (501_000, 3_500_000)},
        threat_ground_elevations_m={"a": 6100},
        start_ground_elevation_m=5900,
        end_ground_elevation_m=6000,
        payload=payload,
        route_found=False,
    )
    scene = trimesh.load(output, force="scene")
    document = read_glb_document(output.read_bytes())
    origin_altitude = document["asset"]["extras"]["scene3d"]["origin"][
        "altitude_amsl_m"
    ]

    root_transform, _root_geometry = scene.graph.get("unit_a")
    assert root_transform[1, 3] + origin_altitude == pytest.approx(6100)
    zone_transform, zone_geometry = scene.graph.get("unit_a/warning_zone")
    zone_vertices = trimesh.transform_points(
        scene.geometry[zone_geometry].vertices,
        zone_transform,
    )
    assert zone_vertices[:, 1].min() + origin_altitude == pytest.approx(0)
    assert zone_vertices[:, 1].max() + origin_altitude == pytest.approx(7200)


def test_invalid_threat_ground_omits_unit_but_keeps_route_and_terminals(
    tmp_path: Path,
) -> None:
    output = tmp_path / "air_corridor_result.glb"
    metadata = write_air_corridor_glb(
        output,
        task_id="air_corridor_task_a",
        target_epsg=32644,
        path_points=[
            (500_000, 3_500_000, 6200),
            (502_000, 3_500_000, 6400),
        ],
        sample_features=[],
        prepared_threat_xy={"a": (501_000, 3_500_000)},
        threat_ground_elevations_m={"a": None},
        start_ground_elevation_m=5900,
        end_ground_elevation_m=6000,
        payload=payload_with_one_threat(),
        route_found=True,
    )
    document = read_glb_document(output.read_bytes())
    node_names = {node["name"] for node in document["nodes"]}

    assert {"corridor_path", "corridor_ribbon", "start", "end"} <= node_names
    assert metadata["tactical_unit_count"] == 0
    assert metadata["omitted_units"] == [
        {"unit_id": "a", "reason": "altitude_amsl_m must be finite"}
    ]
    assert not any(name.startswith("unit_a") for name in node_names)


def test_explicit_zero_threat_radius_omits_the_complete_unit(
    tmp_path: Path,
) -> None:
    output = tmp_path / "air_corridor_result.glb"
    payload = payload_with_one_threat()
    payload.threats[0].warning_zone_radius_m = 0

    metadata = write_air_corridor_glb(
        output,
        task_id="air_corridor_task_a",
        target_epsg=32644,
        path_points=[],
        sample_features=[],
        prepared_threat_xy={"a": (501_000, 3_500_000)},
        threat_ground_elevations_m={"a": 6100},
        start_ground_elevation_m=5900,
        end_ground_elevation_m=6000,
        payload=payload,
        route_found=False,
    )
    document = read_glb_document(output.read_bytes())
    node_names = {node["name"] for node in document["nodes"]}

    assert metadata["tactical_unit_count"] == 0
    assert metadata["omitted_units"] == [
        {
            "unit_id": "a",
            "reason": "warning_zone outer radius must exceed inner radius",
        }
    ]
    assert not any(name.startswith("unit_a") for name in node_names)


def test_none_threat_radius_keeps_the_documented_fallback() -> None:
    payload = payload_with_one_threat()
    payload.threats[0].warning_zone_radius_m = None
    payload.threats[0].kill_zone_radius_m = None

    spec = air_corridor_scene._threat_unit_spec(
        payload.threats[0],
        0,
        (501_000, 3_500_000),
        6100,
        payload.planning.corridor_width_m,
    )

    assert spec.warning_zone is not None
    assert spec.warning_zone.outer_radius_m == payload.threats[0].max_range_m
    assert spec.kill_zone is not None
    assert spec.kill_zone.outer_radius_m == payload.threats[0].max_range_m * 0.7


def test_omitted_distant_threat_does_not_influence_scene_origin(
    tmp_path: Path,
) -> None:
    output = tmp_path / "air_corridor_result.glb"
    payload = payload_with_one_threat()
    path_points = [
        (500_000, 3_500_000, 6200),
        (502_000, 3_500_000, 6400),
    ]
    to_target = Transformer.from_crs(
        "EPSG:4326",
        "EPSG:32644",
        always_xy=True,
    )
    start_xy = to_target.transform(payload.start.lon, payload.start.lat)
    end_xy = to_target.transform(payload.end.lon, payload.end.lat)
    expected_x = (
        min(start_xy[0], end_xy[0], *(point[0] for point in path_points))
        + max(start_xy[0], end_xy[0], *(point[0] for point in path_points))
    ) / 2

    metadata = write_air_corridor_glb(
        output,
        task_id="air_corridor_task_a",
        target_epsg=32644,
        path_points=path_points,
        sample_features=[],
        prepared_threat_xy={"a": (50_000_000, 3_500_000)},
        threat_ground_elevations_m={"a": None},
        start_ground_elevation_m=5900,
        end_ground_elevation_m=6000,
        payload=payload,
        route_found=True,
    )

    assert metadata["omitted_units"]
    assert metadata["origin"]["projected_x"] == pytest.approx(expected_x)
    assert metadata["origin"]["altitude_amsl_m"] == 6200


def test_long_threat_names_use_request_order_labels_and_preserve_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "air_corridor_result.glb"
    payload = payload_with_two_threats()
    payload.threats[0].name = "Shared threat prefix alpha"
    payload.threats[1].name = "Shared threat prefix bravo"
    captured_labels: list[str | None] = []
    build_unit_nodes = air_corridor_scene.build_unit_nodes

    def capture_specs(specs, frame):
        captured_labels.extend(spec.short_label for spec in specs)
        return build_unit_nodes(specs, frame)

    monkeypatch.setattr(air_corridor_scene, "build_unit_nodes", capture_specs)
    write_air_corridor_glb(
        output,
        task_id="air_corridor_task_a",
        target_epsg=32644,
        path_points=[],
        sample_features=[],
        prepared_threat_xy={
            "a": (501_000, 3_500_000),
            "b": (501_500, 3_500_300),
        },
        threat_ground_elevations_m={"a": 5900, "b": 6000},
        start_ground_elevation_m=5900,
        end_ground_elevation_m=6000,
        payload=payload,
        route_found=False,
    )
    document = read_glb_document(output.read_bytes())
    nodes_by_name = {node["name"]: node for node in document["nodes"]}

    assert captured_labels == ["AD-01", "AD-02"]
    for threat in payload.threats:
        assert nodes_by_name[f"unit_{threat.id}"]["extras"][
            "source"
        ] == threat.model_dump()
