import pytest

from app.demo_scenarios.registry import MODEL_SPECS


@pytest.mark.parametrize(
    "model_id",
    ["uav", "watchpost", "artillery", "recon_vehicle", "mobility", "air_corridor"],
)
def test_model_registry_has_endpoint_and_required_outputs(model_id: str) -> None:
    spec = MODEL_SPECS[model_id]

    assert spec.base_path.startswith("/api/")
    assert spec.required_outputs


def test_watchpost_rejects_extreme_blocked_ratio() -> None:
    spec = MODEL_SPECS["watchpost"]
    outputs = {"range_geojson", "visible_geojson", "blocked_geojson"}

    assert spec.validate({"blocked_ratio": 0}, outputs)
    assert spec.validate({"blocked_ratio": 0.4}, outputs) == []


def test_mobility_requires_two_reachable_distinct_results() -> None:
    spec = MODEL_SPECS["mobility"]
    outputs = {
        "road_mask_geojson",
        "wheeled_path_geojson",
        "tracked_path_geojson",
    }
    metrics = {
        "wheeled": {"reachable": True, "travel_time_seconds": 100},
        "tracked": {"reachable": True, "travel_time_seconds": 100},
    }

    assert spec.validate(metrics, outputs)
    metrics["tracked"]["travel_time_seconds"] = 140
    assert spec.validate(metrics, outputs) == []


def test_registry_reports_missing_output_kind() -> None:
    errors = MODEL_SPECS["air_corridor"].validate(
        {"route_found": True, "corridor_length_m": 1000},
        {"corridor_path_geojson"},
    )

    assert "missing output: threat_zones_geojson" in errors


def test_air_corridor_requires_an_altitude_change_for_demo_effect() -> None:
    spec = MODEL_SPECS["air_corridor"]
    outputs = set(spec.required_outputs)
    valid = {
        "route_found": True,
        "corridor_length_m": 110_000,
        "direct_distance_m": 100_000,
        "risk_sample_count": 400,
        "altitude_change_count": 5,
        "horizontal_detour_ratio": 1.08,
    }

    assert "scene_glb" in outputs
    assert spec.validate(valid, outputs) == []
    for key, invalid_value in (
        ("direct_distance_m", 70_000),
        ("risk_sample_count", 200),
        ("altitude_change_count", 3),
        ("horizontal_detour_ratio", 1.01),
    ):
        invalid = {**valid, key: invalid_value}
        assert spec.validate(invalid, outputs), key
