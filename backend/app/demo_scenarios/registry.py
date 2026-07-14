from dataclasses import dataclass
from typing import Callable


Validator = Callable[[dict, set[str]], list[str]]


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    base_path: str
    required_outputs: frozenset[str]
    metric_validator: Validator

    def validate(self, metrics: dict, output_kinds: set[str]) -> list[str]:
        errors = [
            f"missing output: {kind}"
            for kind in sorted(self.required_outputs - output_kinds)
        ]
        return errors + self.metric_validator(metrics, output_kinds)


def _positive(metrics: dict, *keys: str) -> list[str]:
    return [
        f"metric must be positive: {key}"
        for key in keys
        if float(metrics.get(key) or 0) <= 0
    ]


def _uav(metrics: dict, _: set[str]) -> list[str]:
    return _positive(
        metrics,
        "route_length_m",
        "coverage_point_count",
        "visible_area_m2",
        "blocked_area_m2",
    )


def _watchpost(metrics: dict, _: set[str]) -> list[str]:
    ratio = float(metrics.get("blocked_ratio") or 0)
    if 0.01 < ratio < 0.99:
        return []
    return ["blocked_ratio must be between 0.01 and 0.99"]


def _artillery(metrics: dict, _: set[str]) -> list[str]:
    return _positive(
        metrics,
        "theoretical_area_m2",
        "reachable_area_m2",
        "terrain_masked_area_m2",
        "sample_point_count",
    )


def _recon(metrics: dict, _: set[str]) -> list[str]:
    return _positive(
        metrics,
        "route_length_m",
        "coverage_point_count",
        "visible_area_m2",
        "blocked_area_m2",
    )


def _mobility(metrics: dict, _: set[str]) -> list[str]:
    wheeled = metrics.get("wheeled", {})
    tracked = metrics.get("tracked", {})
    errors: list[str] = []
    if not wheeled.get("reachable") or not tracked.get("reachable"):
        errors.append("both vehicle types must be reachable")
    wheeled_time = wheeled.get("travel_time_seconds")
    tracked_time = tracked.get("travel_time_seconds")
    if (
        wheeled_time is None
        or tracked_time is None
        or abs(float(wheeled_time) - float(tracked_time)) <= 1
    ):
        errors.append("vehicle travel times must differ by more than one second")
    return errors


def _air(metrics: dict, _: set[str]) -> list[str]:
    errors = (
        []
        if metrics.get("route_found") is True
        else ["air corridor route was not found"]
    )
    errors += _positive(metrics, "corridor_length_m")
    if int(metrics.get("altitude_change_count") or 0) <= 0:
        errors.append("air corridor must change altitude for the demo scenario")
    return errors


MODEL_SPECS = {
    "uav": ModelSpec(
        "uav",
        "/api/uav/recon",
        frozenset({"footprint_geojson", "visible_geojson", "blocked_geojson"}),
        _uav,
    ),
    "watchpost": ModelSpec(
        "watchpost",
        "/api/watchpost/detection",
        frozenset({"range_geojson", "visible_geojson", "blocked_geojson"}),
        _watchpost,
    ),
    "artillery": ModelSpec(
        "artillery",
        "/api/artillery/coverage",
        frozenset(
            {
                "theoretical_geojson",
                "reachable_geojson",
                "terrain_masked_geojson",
                "sample_points_geojson",
            }
        ),
        _artillery,
    ),
    "recon_vehicle": ModelSpec(
        "recon_vehicle",
        "/api/recon-vehicle/coverage",
        frozenset({"footprint_geojson", "visible_geojson", "blocked_geojson"}),
        _recon,
    ),
    "mobility": ModelSpec(
        "mobility",
        "/api/mobility/accessibility",
        frozenset(
            {"road_mask_geojson", "wheeled_path_geojson", "tracked_path_geojson"}
        ),
        _mobility,
    ),
    "air_corridor": ModelSpec(
        "air_corridor",
        "/api/air-corridor/planning",
        frozenset(
            {
                "threat_zones_geojson",
                "corridor_buffer_geojson",
                "corridor_path_geojson",
                "risk_samples_geojson",
            }
        ),
        _air,
    ),
}
