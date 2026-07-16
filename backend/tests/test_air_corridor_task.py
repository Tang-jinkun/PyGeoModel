import json
from pathlib import Path
from types import SimpleNamespace

import numpy
import pytest
import rasterio
from rasterio.transform import from_origin

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.air_corridor import AirCorridorPlanningRequest
from app.services.air_corridor_task_store import (
    create_air_corridor_task,
    get_air_corridor_task,
)
from app.workers.air_corridor_task import (
    _commit_staged_outputs,
    _compute_air_corridor,
    _threat_ground_elevations,
    _write_air_corridor_outputs,
    run_air_corridor_task,
)
from app.services.air_corridor_output_files import AIR_CORRIDOR_OUTPUT_FILENAMES


class Prepared:
    target_epsg = 32644
    start_x = 5.0
    start_y = 95.0
    end_x = 95.0
    end_y = 95.0
    threat_xy = {"sam_1": (45.0, 95.0)}
    bounds = type("Bounds", (), {"left": 0, "bottom": 0, "right": 100, "top": 100})()
    resolution_m = (10, 10)


def prepared_dem(
    tmp_path: Path,
    *,
    data: numpy.ndarray | None = None,
    nodata: float | None = None,
    threat_xy: dict[str, tuple[float, float]] | None = None,
):
    path = tmp_path / "projected.tif"
    if data is None:
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
        nodata=nodata,
    ) as dataset:
        dataset.write(data, 1)
    return SimpleNamespace(
        projected_dem=path,
        target_epsg=32644,
        start_x=5.0,
        start_y=95.0,
        end_x=95.0,
        end_y=95.0,
        threat_xy=threat_xy or {},
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


def test_air_corridor_reports_direct_detour_and_sample_metrics() -> None:
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
    metrics = result["metrics"]

    assert metrics.direct_distance_m == pytest.approx(90.0)
    assert metrics.horizontal_detour_ratio >= 1.0
    assert metrics.risk_sample_count == len(result["sample_features"])


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


def test_threat_ground_elevations_return_none_for_invalid_dem_samples() -> None:
    nodata = -9999.0
    dem = numpy.asarray([[123.0, nodata, numpy.nan]], dtype=numpy.float32)
    transform = from_origin(0, 100, 10, 10)
    payload = AirCorridorPlanningRequest(
        dem_id="dem_a",
        start={"lon": 79.8, "lat": 31.48, "altitude_m": 300},
        end={"lon": 79.81, "lat": 31.48, "altitude_m": 300},
        threats=[
            {"id": threat_id, "lon": 79.8, "lat": 31.48, "max_range_m": 60}
            for threat_id in ("finite", "nodata", "nan", "outside")
        ],
    )
    prepared = SimpleNamespace(
        threat_xy={
            "finite": (5.0, 95.0),
            "nodata": (15.0, 95.0),
            "nan": (25.0, 95.0),
            "outside": (35.0, 95.0),
        }
    )

    assert _threat_ground_elevations(
        dem,
        transform,
        nodata,
        prepared,
        payload,
    ) == {
        "finite": 123.0,
        "nodata": None,
        "nan": None,
        "outside": None,
    }


def test_worker_stages_scene_glb_and_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    task_id = "air_corridor_task_a"
    settings.data_dir = tmp_path
    settings.ensure_directories()
    output_dir = settings.outputs_dir / task_id
    staging_dir = settings.outputs_dir / f".{task_id}.staging-test"
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
            prepared_dem(staging_dir),
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
    assert metadata["model"]["scene3d"]["tactical_unit_count"] == 0
    assert metadata["model"]["scene3d"]["omitted_units"] == []
    assert {
        path.name for path in output_dir.iterdir()
    } == set(AIR_CORRIDOR_OUTPUT_FILENAMES.values())


def test_worker_propagates_scene_unit_omissions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_id = "air_corridor_task_omission"
    settings.data_dir = tmp_path
    settings.ensure_directories()
    output_dir = settings.outputs_dir / task_id
    staging_dir = settings.outputs_dir / f".{task_id}.staging-test"
    staging_dir.mkdir(parents=True)
    nodata = -9999.0
    dem = numpy.zeros((10, 10), dtype=numpy.float32)
    dem[0, 4] = nodata
    prepared = prepared_dem(
        tmp_path,
        data=dem,
        nodata=nodata,
        threat_xy={"sam_1": (45.0, 95.0)},
    )
    payload = AirCorridorPlanningRequest(
        dem_id="dem_a",
        start={"lon": 79.8, "lat": 31.48, "altitude_m": 300},
        end={"lon": 79.81, "lat": 31.48, "altitude_m": 300},
        altitude_layers_m=[300],
        threats=[
            {
                "id": "sam_1",
                "lon": 79.805,
                "lat": 31.48,
                "max_range_m": 60,
            }
        ],
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
        "threat_count": 1,
        "corridor_width_m": 500.0,
        "tactical_unit_count": 0,
        "omitted_units": [
            {"unit_id": "sam_1", "reason": "altitude_amsl_m must be finite"}
        ],
    }
    glb_arguments: dict = {}

    def fake_glb(path: Path, **kwargs):
        glb_arguments.update(kwargs)
        path.write_bytes(b"glTF")
        return scene_metadata

    monkeypatch.setattr(
        "app.workers.air_corridor_task.write_air_corridor_glb",
        fake_glb,
    )
    _outputs, _output_files, _metrics, model, warnings = (
        _write_air_corridor_outputs(
            task_id,
            staging_dir,
            output_dir,
            prepared,
            payload,
        )
    )
    expected_warnings = [
        "Scene3D omitted unit 'sam_1': altitude_amsl_m must be finite"
    ]

    assert glb_arguments["threat_ground_elevations_m"] == {"sam_1": None}
    assert model.scene3d is not None
    assert [item.model_dump() for item in model.scene3d.omitted_units] == (
        scene_metadata["omitted_units"]
    )
    assert warnings == expected_warnings
    model_document = json.loads(
        (output_dir / "model_metadata.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (output_dir / "output_manifest.json").read_text(encoding="utf-8")
    )
    assert model_document["warnings"] == expected_warnings
    assert manifest["warnings"] == expected_warnings


def test_scene_unit_omission_warning_reaches_finished_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    payload = AirCorridorPlanningRequest(
        dem_id="dem_a",
        start={"lon": 79.8, "lat": 31.48, "altitude_m": 300},
        end={"lon": 79.81, "lat": 31.48, "altitude_m": 300},
        altitude_layers_m=[300],
        threats=[
            {
                "id": "sam_1",
                "lon": 79.805,
                "lat": 31.48,
                "max_range_m": 60,
            }
        ],
    )
    task = create_air_corridor_task(payload)
    prepared = prepared_dem(
        tmp_path,
        threat_xy={"sam_1": (45.0, 95.0)},
    )
    monkeypatch.setattr(
        "app.workers.air_corridor_task.find_dem_file",
        lambda _dem_id: tmp_path / "source.tif",
    )
    monkeypatch.setattr(
        "app.workers.air_corridor_task._prepare_air_corridor_dem",
        lambda _source, _destination, _payload: prepared,
    )

    def fake_glb(path: Path, **kwargs):
        path.write_bytes(b"glTF")
        return {
            "schema_version": 1,
            "task_id": task.task_id,
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
            "route_found": kwargs["route_found"],
            "risk_sample_count": len(kwargs["sample_features"]),
            "threat_count": 1,
            "corridor_width_m": 500.0,
            "tactical_unit_count": 0,
            "omitted_units": [
                {
                    "unit_id": "sam_1",
                    "reason": "unit geometry is invalid",
                }
            ],
        }

    monkeypatch.setattr(
        "app.workers.air_corridor_task.write_air_corridor_glb",
        fake_glb,
    )

    run_air_corridor_task(task.task_id, payload)

    detail = get_air_corridor_task(task.task_id)
    assert detail.status == "finished"
    assert detail.warnings == [
        "Scene3D omitted unit 'sam_1': unit geometry is invalid"
    ]


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


def test_output_publication_uses_one_sibling_directory_rename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staging_dir = tmp_path / ".air_corridor_task_a.staging-test"
    output_dir = tmp_path / "air_corridor_task_a"
    staging_dir.mkdir()
    for filename in AIR_CORRIDOR_OUTPUT_FILENAMES.values():
        (staging_dir / filename).write_text(filename, encoding="utf-8")
    original_replace = Path.replace
    replacements: list[tuple[Path, Path]] = []

    def track_replace(source: Path, target: Path) -> Path:
        replacements.append((source, Path(target)))
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", track_replace)

    _commit_staged_outputs(staging_dir, output_dir)

    assert replacements == [(staging_dir, output_dir)]
    assert not staging_dir.exists()
    assert {
        path.name for path in output_dir.iterdir()
    } == set(AIR_CORRIDOR_OUTPUT_FILENAMES.values())


def test_output_publication_failure_leaves_no_partial_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staging_dir = tmp_path / ".air_corridor_task_a.staging-test"
    output_dir = tmp_path / "air_corridor_task_a"
    staging_dir.mkdir()
    for filename in AIR_CORRIDOR_OUTPUT_FILENAMES.values():
        (staging_dir / filename).write_text(filename, encoding="utf-8")
    original_replace = Path.replace
    replacements: list[tuple[Path, Path]] = []

    def fail_publication(source: Path, target: Path) -> Path:
        target_path = Path(target)
        replacements.append((source, target_path))
        if source == staging_dir or (
            source.parent == staging_dir
            and sum(item[0].parent == staging_dir for item in replacements) == 2
        ):
            raise OSError("injected directory publication failure")
        return original_replace(source, target_path)

    monkeypatch.setattr(Path, "replace", fail_publication)

    with pytest.raises(OSError, match="injected directory publication failure"):
        _commit_staged_outputs(staging_dir, output_dir)

    assert replacements == [(staging_dir, output_dir)]
    assert not output_dir.exists()
    assert {
        path.name for path in staging_dir.iterdir()
    } == set(AIR_CORRIDOR_OUTPUT_FILENAMES.values())


def test_output_publication_refuses_to_replace_existing_task_directory(
    tmp_path: Path,
) -> None:
    staging_dir = tmp_path / ".air_corridor_task_a.staging-test"
    output_dir = tmp_path / "air_corridor_task_a"
    staging_dir.mkdir()
    output_dir.mkdir()
    (staging_dir / "new.txt").write_text("new", encoding="utf-8")
    (output_dir / "legacy.txt").write_text("legacy", encoding="utf-8")

    with pytest.raises(AppError, match="already exists"):
        _commit_staged_outputs(staging_dir, output_dir)

    assert (staging_dir / "new.txt").read_text(encoding="utf-8") == "new"
    assert (output_dir / "legacy.txt").read_text(encoding="utf-8") == "legacy"


def test_oversize_glb_failure_rolls_back_sibling_staging_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    observed_staging_dirs: list[Path] = []
    monkeypatch.setattr(
        "app.workers.air_corridor_task.find_dem_file",
        lambda _dem_id: tmp_path / "source.tif",
    )

    def fake_prepare(_source: Path, destination: Path, _payload):
        observed_staging_dirs.append(destination.parent)
        return prepared

    monkeypatch.setattr(
        "app.workers.air_corridor_task._prepare_air_corridor_dem",
        fake_prepare,
    )
    monkeypatch.setattr(
        "app.workers.air_corridor_task.write_air_corridor_glb",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError(
                "GLB payload exceeds 50000000-byte hard limit: 50000001 bytes"
            )
        ),
    )

    run_air_corridor_task(task.task_id, payload)

    detail = get_air_corridor_task(task.task_id)
    output_dir = settings.outputs_dir / task.task_id
    assert detail.status == "failed"
    assert "50000000-byte hard limit" in detail.message
    assert observed_staging_dirs[0].parent == settings.outputs_dir
    assert observed_staging_dirs[0] != output_dir
    assert not output_dir.exists()
    assert not observed_staging_dirs[0].exists()
