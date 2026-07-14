import json
from pathlib import Path

import pytest

from app.demo_scenarios.generator import MODEL_ORDER, generate_scenarios
from tests.demo_scenario_helpers import write_dem


def prepare_dem(data_dir: Path, dem_id: str = "dem_a") -> None:
    dem_dir = data_dir / "dem" / dem_id
    dem_dir.mkdir(parents=True)
    write_dem(dem_dir / "dem.cog.tif")
    (dem_dir / "metadata.json").write_text(
        json.dumps(
            {
                "dem_id": dem_id,
                "crs": "EPSG:4326",
                "bounds": [79.0, 31.6, 79.4, 32.0],
            }
        ),
        encoding="utf-8",
    )


def test_generator_writes_six_scenarios_and_artifacts(tmp_path: Path) -> None:
    prepare_dem(tmp_path)

    scenarios = generate_scenarios(tmp_path, "dem_a")

    output = tmp_path / "demo-scenarios" / "dem_a"
    assert list(scenarios) == MODEL_ORDER
    assert len(list(output.glob("*.json"))) == 6
    assert (output / "road-network.geojson").exists()
    assert (output / "air-defense-threats.geojson").exists()
    assert all("synthetic" not in item.request for item in scenarios.values())


def test_generator_rejects_mismatched_dem_metadata(tmp_path: Path) -> None:
    prepare_dem(tmp_path)
    metadata_path = tmp_path / "dem" / "dem_a" / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "dem_id": "wrong_dem",
                "crs": "EPSG:4326",
                "bounds": [79.0, 31.6, 79.4, 32.0],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="metadata id mismatch"):
        generate_scenarios(tmp_path, "dem_a")
