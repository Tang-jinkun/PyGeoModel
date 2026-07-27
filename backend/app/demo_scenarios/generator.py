import argparse
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

from app.demo_scenarios.coverage_builders import BUILDERS as COVERAGE_BUILDERS
from app.demo_scenarios.models import ScenarioEnvelope
from app.demo_scenarios.route_builders import (
    build_air_corridor,
    build_mobility,
    spatial_artifacts,
)
from app.demo_scenarios.storage import read_json, write_json_atomic
from app.demo_scenarios.terrain import TerrainGrid
from app.schemas.air_corridor import AirCorridorPlanningRequest
from app.schemas.artillery import ArtilleryCoverageRequest
from app.schemas.mobility import MobilityAccessibilityRequest
from app.schemas.recon_vehicle import ReconVehicleCoverageRequest
from app.schemas.uav import UavReconRequest
from app.schemas.watchpost import WatchpostDetectionRequest


MODEL_ORDER = [
    "uav",
    "watchpost",
    "artillery",
    "recon_vehicle",
    "mobility",
    "air_corridor",
]
BUILDERS = {
    **COVERAGE_BUILDERS,
    "mobility": build_mobility,
    "air_corridor": build_air_corridor,
}
REQUEST_SCHEMAS = {
    "uav": UavReconRequest,
    "watchpost": WatchpostDetectionRequest,
    "artillery": ArtilleryCoverageRequest,
    "recon_vehicle": ReconVehicleCoverageRequest,
    "mobility": MobilityAccessibilityRequest,
    "air_corridor": AirCorridorPlanningRequest,
}
TARGET_DEM_ID = "dem_20260713_080113_884937cf"
TARGET_BOUNDS = [78.39572341, 30.449041933, 80.942515968, 32.70424882]


@lru_cache(maxsize=2)
def _load_terrain(dem_path: Path) -> TerrainGrid:
    return TerrainGrid.load(dem_path)


def _validate_dem_metadata(data_dir: Path, dem_id: str) -> None:
    metadata_path = data_dir / "dem" / dem_id / "metadata.json"
    metadata = read_json(metadata_path)
    if metadata.get("dem_id") != dem_id:
        raise ValueError(f"DEM metadata id mismatch in {metadata_path}")
    bounds = metadata.get("bounds")
    if (
        metadata.get("crs") != "EPSG:4326"
        or not isinstance(bounds, list)
        or len(bounds) != 4
    ):
        raise ValueError(f"Unsupported DEM metadata in {metadata_path}")
    if dem_id == TARGET_DEM_ID and bounds != TARGET_BOUNDS:
        raise ValueError(f"Target DEM bounds mismatch in {metadata_path}")


def generate_one(
    data_dir: Path,
    dem_id: str,
    model_id: str,
    candidate_index: int,
) -> ScenarioEnvelope:
    _validate_dem_metadata(data_dir, dem_id)
    dem_path = data_dir / "dem" / dem_id / "dem.cog.tif"
    if not dem_path.exists():
        raise FileNotFoundError(f"DEM COG not found: {dem_path}")
    if model_id not in BUILDERS:
        raise ValueError(f"Unsupported demo model: {model_id}")

    terrain = _load_terrain(dem_path)
    scenario = BUILDERS[model_id](terrain, dem_id, candidate_index)
    native_request = (
        REQUEST_SCHEMAS[model_id]
        .model_validate(scenario.request)
        .model_dump(mode="json")
    )
    scenario = replace(scenario, request=native_request)

    output_dir = data_dir / "demo-scenarios" / dem_id
    write_json_atomic(
        output_dir / f"{scenario.scenario_id}.json",
        scenario.to_dict(),
    )
    for filename, payload in spatial_artifacts(scenario).items():
        write_json_atomic(output_dir / filename, payload)
    return scenario


def generate_scenarios(
    data_dir: Path,
    dem_id: str,
    candidate_indices: dict[str, int] | None = None,
) -> dict[str, ScenarioEnvelope]:
    selected = candidate_indices or {}
    return {
        model_id: generate_one(
            data_dir,
            dem_id,
            model_id,
            selected.get(model_id, 0),
        )
        for model_id in MODEL_ORDER
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate deterministic synthetic PyGeoModel demo scenarios."
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--dem-id", required=True)
    args = parser.parse_args()
    scenarios = generate_scenarios(args.data_dir, args.dem_id)
    for model_id, scenario in scenarios.items():
        print(
            f"{model_id}: candidate={scenario.candidate_index} "
            f"scenario={scenario.scenario_id}"
        )
