import json
from pathlib import Path

import numpy
import pytest
import rasterio
from rasterio.coords import BoundingBox
from rasterio.transform import from_origin
from shapely.geometry import Point

from app.core.errors import AppError
from app.schemas.radar import CoverageMetrics, CoverageModelMetadata, CoverageOutputFile, CoverageRequest
from app.services.coverage_model import PreparedCoverageDem
from app.services.output_files import OUTPUT_FILENAMES, describe_output_files
from app.workers.coverage_task import (
    _commit_staged_outputs,
    _ensure_finished_outputs_exist,
    _ensure_staged_outputs_exist,
    _generate_height_layers,
    _write_feature_collection,
    _write_json_atomic,
    _write_output_manifest,
    _write_text_atomic,
)


def test_write_feature_collection_is_valid_json_and_cleans_temp(tmp_path: Path) -> None:
    path = tmp_path / "visible.geojson"

    _write_feature_collection(path, Point(0, 0).buffer(1), {"kind": "visible"})

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["type"] == "FeatureCollection"
    assert payload["features"][0]["properties"] == {"kind": "visible"}
    assert not list(tmp_path.glob("*.tmp"))


def test_write_feature_collection_handles_empty_geometry(tmp_path: Path) -> None:
    path = tmp_path / "empty.geojson"

    _write_feature_collection(path, None, {"kind": "visible"})

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {"type": "FeatureCollection", "features": []}


def test_write_json_atomic_writes_valid_json_and_cleans_temp(tmp_path: Path) -> None:
    path = tmp_path / "model_metadata.json"

    _write_json_atomic(path, {"ok": True})

    assert json.loads(path.read_text(encoding="utf-8")) == {"ok": True}
    assert not list(tmp_path.glob("*.tmp"))


def test_write_text_atomic_failure_preserves_existing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "target.json"
    path.write_text("old", encoding="utf-8")

    def fail_fsync(_: int) -> None:
        raise OSError("boom")

    monkeypatch.setattr("app.workers.coverage_task.os.fsync", fail_fsync)

    with pytest.raises(OSError):
        _write_text_atomic(path, "new")

    assert path.read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob("*.tmp"))


def test_write_output_manifest_includes_all_sections(tmp_path: Path) -> None:
    path = tmp_path / "output_manifest.json"
    files = [
        CoverageOutputFile(
            kind="visible_geojson",
            label="Visible Area GeoJSON",
            url="/outputs/task_a/visible.geojson",
            download_url="/api/radar/coverage/task_a/outputs/visible_geojson",
            filename="visible.geojson",
            media_type="application/geo+json",
            size_bytes=2,
            exists=True,
        )
    ]
    metrics = CoverageMetrics(theoretical_area_m2=100, visible_area_m2=60, blocked_area_m2=40, blocked_ratio=0.4)
    model = CoverageModelMetadata(
        target_epsg=32648,
        radar_projected_xy=[0, 0],
        projected_dem_bounds=[0, 0, 10, 10],
        projected_dem_resolution_m=[10, 10],
        max_range_m=1000,
        scan_mode="omni",
        azimuth_deg=0,
        beam_width_deg=360,
        simplify_tolerance_m=10,
    )

    _write_output_manifest(path, files, metrics, model, ["extent warning"])

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["files"][0]["kind"] == "visible_geojson"
    assert payload["metrics"]["blocked_ratio"] == 0.4
    assert payload["model"]["target_epsg"] == 32648
    assert payload["warnings"] == ["extent warning"]
    assert not list(tmp_path.glob("*.tmp"))


def test_output_manifest_can_describe_all_public_outputs(tmp_path: Path) -> None:
    staging_dir = tmp_path / ".staging"
    staging_dir.mkdir()
    for filename in OUTPUT_FILENAMES.values():
        (staging_dir / filename).write_text(filename, encoding="utf-8")
    output_paths = {kind: staging_dir / filename for kind, filename in OUTPUT_FILENAMES.items()}
    files = describe_output_files("task_a", output_paths)
    metrics = CoverageMetrics()
    model = CoverageModelMetadata(
        target_epsg=32648,
        radar_projected_xy=[0, 0],
        projected_dem_bounds=[0, 0, 10, 10],
        projected_dem_resolution_m=[10, 10],
        max_range_m=1000,
        scan_mode="omni",
        azimuth_deg=0,
        beam_width_deg=360,
        simplify_tolerance_m=10,
    )

    _write_output_manifest(staging_dir / "output_manifest.json", files, metrics, model, [])

    payload = json.loads((staging_dir / "output_manifest.json").read_text(encoding="utf-8"))
    assert [item["kind"] for item in payload["files"]] == list(OUTPUT_FILENAMES)


def test_ensure_finished_outputs_exist_rejects_missing_file() -> None:
    files = [
        CoverageOutputFile(
            kind="blocked_geojson",
            label="Blocked Area GeoJSON",
            url="/outputs/task_a/blocked.geojson",
            download_url="/api/radar/coverage/task_a/outputs/blocked_geojson",
            filename="blocked.geojson",
            media_type="application/geo+json",
            exists=False,
        )
    ]

    with pytest.raises(AppError) as exc_info:
        _ensure_finished_outputs_exist(files)

    assert exc_info.value.code == "OUTPUT_INCOMPLETE"
    assert "blocked_geojson" in exc_info.value.message


def test_ensure_finished_outputs_exist_rejects_empty_file() -> None:
    files = [
        CoverageOutputFile(
            kind="visible_geojson",
            label="Visible Area GeoJSON",
            url="/outputs/task_a/visible.geojson",
            download_url="/api/radar/coverage/task_a/outputs/visible_geojson",
            filename="visible.geojson",
            media_type="application/geo+json",
            size_bytes=0,
            exists=True,
        )
    ]

    with pytest.raises(AppError) as exc_info:
        _ensure_finished_outputs_exist(files)

    assert exc_info.value.code == "OUTPUT_INCOMPLETE"


def test_ensure_staged_outputs_exist_requires_all_public_outputs(tmp_path: Path) -> None:
    staging_dir = tmp_path / ".staging"
    staging_dir.mkdir()
    (staging_dir / "viewshed.tif").write_bytes(b"abc")

    with pytest.raises(AppError) as exc_info:
        _ensure_staged_outputs_exist(staging_dir)

    assert exc_info.value.code == "OUTPUT_INCOMPLETE"
    assert "visible_geojson" in exc_info.value.message


def test_commit_staged_outputs_replaces_public_outputs(tmp_path: Path) -> None:
    staging_dir = tmp_path / ".staging"
    output_dir = tmp_path / "task_a"
    staging_dir.mkdir()
    for filename in OUTPUT_FILENAMES.values():
        (staging_dir / filename).write_text(filename, encoding="utf-8")
    (staging_dir / "visible_h_0.geojson").write_text("height-layer", encoding="utf-8")

    _ensure_staged_outputs_exist(staging_dir)
    _commit_staged_outputs(staging_dir, output_dir)

    assert (output_dir / "viewshed.tif").read_text(encoding="utf-8") == "viewshed.tif"
    assert not (staging_dir / "viewshed.tif").exists()
    assert all((output_dir / filename).exists() for filename in [
        "viewshed.tif",
        "visible.geojson",
        "blocked.geojson",
        "radar_range.geojson",
        "model_metadata.json",
        "output_manifest.json",
    ])
    assert (output_dir / "visible_h_0.geojson").read_text(encoding="utf-8") == "height-layer"


def test_commit_staged_outputs_moves_blocked_height_layers(tmp_path: Path) -> None:
    staging_dir = tmp_path / ".staging"
    output_dir = tmp_path / "task_a"
    staging_dir.mkdir()
    for filename in OUTPUT_FILENAMES.values():
        (staging_dir / filename).write_text(filename, encoding="utf-8")
    (staging_dir / "blocked_h_0.geojson").write_text("blocked-height-layer", encoding="utf-8")

    _commit_staged_outputs(staging_dir, output_dir)

    assert (output_dir / "blocked_h_0.geojson").read_text(encoding="utf-8") == "blocked-height-layer"


def test_generate_height_layers_writes_visible_and_blocked_manifests(tmp_path: Path) -> None:
    min_visible_height = tmp_path / "min_visible_height.tif"
    data = numpy.array(
        [
            [0, 30, 0, 30],
            [0, 30, 0, 30],
            [0, 30, 0, 30],
            [0, 30, 0, 30],
        ],
        dtype=numpy.float32,
    )
    transform = from_origin(-20, 20, 10, 10)
    with rasterio.open(
        min_visible_height,
        "w",
        driver="GTiff",
        width=4,
        height=4,
        count=1,
        dtype=data.dtype,
        crs="EPSG:32648",
        transform=transform,
        nodata=-9999,
    ) as dataset:
        dataset.write(data, 1)

    request = CoverageRequest.model_validate(
        {
            "dem_id": "dem_test",
            "radar": {"lon": 105, "lat": 0, "height_m": 10},
            "target": {"height_m": 0},
            "coverage": {
                "max_range_m": 100,
                "scan_mode": "omni",
                "azimuth_deg": 0,
                "beam_width_deg": 360,
            },
            "advanced": {
                "height_layers_m": [0],
                "min_elevation_deg": 0,
                "max_elevation_deg": 89,
            },
        }
    )
    prepared = PreparedCoverageDem(
        source_dem=tmp_path / "source.tif",
        projected_dem=tmp_path / "projected.tif",
        target_epsg=32648,
        radar_x=0,
        radar_y=0,
        projected_bounds=BoundingBox(-20, -20, 20, 20),
        resolution_m=(10, 10),
        dem_coverage_ratio=1,
    )

    _generate_height_layers(tmp_path, min_visible_height, prepared, request)

    manifest = json.loads((tmp_path / "height_layers_manifest.json").read_text(encoding="utf-8"))
    layer = manifest["height_layers"][0]
    assert layer["visible_filename"] == "visible_h_0.geojson"
    assert layer["blocked_filename"] == "blocked_h_0.geojson"
    assert layer["visible_area_m2"] > 0
    assert layer["blocked_area_m2"] > 0
    assert (tmp_path / layer["visible_filename"]).exists()
    assert (tmp_path / layer["blocked_filename"]).exists()
