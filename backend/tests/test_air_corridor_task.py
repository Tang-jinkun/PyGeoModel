import json
from pathlib import Path
from types import SimpleNamespace

import numpy
import rasterio
from rasterio.transform import from_origin

from app.core.config import settings
from app.schemas.air_corridor import AirCorridorPlanningRequest
from app.services.air_corridor_task_store import (
    create_air_corridor_task,
    get_air_corridor_task,
)
from app.workers.air_corridor_task import (
    _compute_air_corridor,
    _write_air_corridor_outputs,
    run_air_corridor_task,
)


class Prepared:
    target_epsg = 32644
    start_x = 5.0
    start_y = 95.0
    end_x = 95.0
    end_y = 95.0
    threat_xy = {"sam_1": (45.0, 95.0)}
    bounds = type("Bounds", (), {"left": 0, "bottom": 0, "right": 100, "top": 100})()
    resolution_m = (10, 10)


def prepared_dem(tmp_path: Path):
    path = tmp_path / "projected.tif"
    data = numpy.zeros((10, 10), dtype=numpy.float32)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=10,
        height=10,
        count=1,
        dtype="float32",
        crs="EPSG:32644",
        transform=from_origin(0, 100, 10, 10),
    ) as dataset:
        dataset.write(data, 1)
    return SimpleNamespace(
        projected_dem=path,
        target_epsg=32644,
        start_x=5.0,
        start_y=95.0,
        end_x=95.0,
        end_y=95.0,
        threat_xy={},
        bounds=SimpleNamespace(left=0, bottom=0, right=100, top=100),
        resolution_m=(10.0, 10.0),
    )


def test_air_corridor_flat_dem_finds_route_without_threat() -> None:
    dem = numpy.zeros((10, 10), dtype=numpy.float32)
    transform = from_origin(0, 100, 10, 10)
    payload = AirCorridorPlanningRequest(
        dem_id="dem_a",
        start={"lon": 79.8, "lat": 31.48, "altitude_m": 300},
        end={"lon": 79.81, "lat": 31.48, "altitude_m": 300},
        altitude_layers_m=[300],
        threats=[],
    )
    prepared = Prepared()
    prepared.threat_xy = {}

    result = _compute_air_corridor(dem, transform, None, prepared, payload)

    assert result["metrics"].route_found is True
    assert result["metrics"].risk_score == 0
    assert result["metrics"].corridor_length_m > 0


def test_air_corridor_uses_higher_layer_to_reduce_threat_risk() -> None:
    dem = numpy.zeros((10, 10), dtype=numpy.float32)
    transform = from_origin(0, 100, 10, 10)
    payload = AirCorridorPlanningRequest(
        dem_id="dem_a",
        start={"lon": 79.8, "lat": 31.48, "altitude_m": 300},
        end={"lon": 79.81, "lat": 31.48, "altitude_m": 300},
        altitude_layers_m=[300, 1200],
        threats=[
            {
                "id": "sam_1",
                "lon": 79.805,
                "lat": 31.48,
                "max_range_m": 60,
                "min_altitude_m": 0,
                "max_altitude_m": 900,
                "threat_level": 10,
            }
        ],
        planning={"allow_altitude_change": True, "threat_weight": 20, "altitude_change_weight": 0.01},
    )

    result = _compute_air_corridor(dem, transform, None, Prepared(), payload)

    assert result["metrics"].route_found is True
    assert result["metrics"].altitude_change_count > 0
    assert result["metrics"].max_altitude_m == 1200


def test_worker_stages_scene_glb_and_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    task_id = "air_corridor_task_a"
    output_dir = tmp_path / task_id
    staging_dir = output_dir / ".staging-test"
    staging_dir.mkdir(parents=True)
    payload = AirCorridorPlanningRequest(
        dem_id="dem_a",
        start={"lon": 79.8, "lat": 31.48, "altitude_m": 300},
        end={"lon": 79.81, "lat": 31.48, "altitude_m": 300},
        altitude_layers_m=[300],
        threats=[],
    )
    scene_metadata = {
        "schema_version": 1,
        "task_id": task_id,
        "model_id": "air_corridor",
        "units": "metre",
        "source_crs": "EPSG:32644",
        "geographic_crs": "EPSG:4326",
        "origin": {
            "projected_x": 50.0,
            "projected_y": 95.0,
            "longitude": 79.8,
            "latitude": 31.48,
            "altitude_amsl_m": 0.0,
        },
        "axes": {"x": "east", "y": "up", "z": "south"},
        "route_found": True,
        "risk_sample_count": 10,
        "threat_count": 0,
        "corridor_width_m": 500.0,
    }

    def fake_glb(path: Path, **_kwargs):
        path.write_bytes(b"glTF")
        return scene_metadata

    monkeypatch.setattr(
        "app.workers.air_corridor_task.write_air_corridor_glb",
        fake_glb,
    )
    outputs, output_files, _metrics, _model, _warnings = (
        _write_air_corridor_outputs(
            task_id,
            staging_dir,
            output_dir,
            prepared_dem(tmp_path),
            payload,
        )
    )

    assert outputs.scene_glb == f"/outputs/{task_id}/air_corridor_result.glb"
    assert any(item.kind == "scene_glb" and item.exists for item in output_files)
    manifest = json.loads(
        (output_dir / "output_manifest.json").read_text(encoding="utf-8")
    )
    assert any(item["kind"] == "scene_glb" for item in manifest["files"])
    metadata = json.loads(
        (output_dir / "model_metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["model"]["scene3d"]["model_id"] == "air_corridor"


def test_glb_export_failure_marks_task_failed_and_leaves_no_artifact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    payload = AirCorridorPlanningRequest(
        dem_id="dem_a",
        start={"lon": 79.8, "lat": 31.48, "altitude_m": 300},
        end={"lon": 79.81, "lat": 31.48, "altitude_m": 300},
        altitude_layers_m=[300],
        threats=[],
    )
    task = create_air_corridor_task(payload)
    prepared = prepared_dem(tmp_path)
    monkeypatch.setattr(
        "app.workers.air_corridor_task.find_dem_file",
        lambda _dem_id: tmp_path / "source.tif",
    )
    monkeypatch.setattr(
        "app.workers.air_corridor_task._prepare_air_corridor_dem",
        lambda _source, _destination, _payload: prepared,
    )

    def fail_glb(_path: Path, **_kwargs):
        raise ValueError("invalid scene")

    monkeypatch.setattr(
        "app.workers.air_corridor_task.write_air_corridor_glb",
        fail_glb,
    )

    run_air_corridor_task(task.task_id, payload)

    detail = get_air_corridor_task(task.task_id)
    assert detail.status == "failed"
    assert "invalid scene" in detail.message
    assert not (
        settings.outputs_dir / task.task_id / "air_corridor_result.glb"
    ).exists()
