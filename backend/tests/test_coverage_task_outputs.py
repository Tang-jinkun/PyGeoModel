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
    _beam_clip_profile_for_range,
    _build_coverage_metrics,
    _commit_staged_outputs,
    _coverage_masks,
    _dem_coverage_ratio,
    _ensure_finished_outputs_exist,
    _ensure_staged_outputs_exist,
    _generate_height_layers,
    _write_feature_collection,
    _write_json_atomic,
    _write_output_manifest,
    _write_text_atomic,
)


def test_coverage_masks_partition_unknown_from_blocked() -> None:
    data = numpy.full((4, 4), 10, dtype=numpy.float32)
    domain = numpy.ones((4, 4), dtype=bool)
    domain[:, 2:] = False
    request = CoverageRequest.model_validate(
        {
            "dem_id": "dem_test",
            "radar": {"lon": 105, "lat": 0, "height_m": 10},
            "target": {"height_m": 100},
            "coverage": {
                "max_range_m": 100,
                "scan_mode": "omni",
                "azimuth_deg": 0,
                "beam_width_deg": 360,
            },
            "advanced": {"min_elevation_deg": 0, "max_elevation_deg": 89},
        }
    )

    masks = _coverage_masks(
        data,
        from_origin(-20, 20, 10, 10),
        radar_x=0,
        radar_y=0,
        payload=request,
        target_height_m=100,
        effective_range_m=100,
        analysis_domain=domain,
    )

    assert numpy.array_equal(masks["raw_theoretical"], masks["theoretical"] | masks["unknown"])
    assert not numpy.any(masks["unknown"] & masks["blocked"])
    assert numpy.array_equal(masks["theoretical"], masks["visible"] | masks["blocked"])


def test_coverage_masks_build_coordinate_grids_in_row_chunks(monkeypatch) -> None:
    data = numpy.zeros((1025, 4), dtype=numpy.float32)
    domain = numpy.ones_like(data, dtype=bool)
    original_meshgrid = numpy.meshgrid
    row_chunk_sizes: list[int] = []

    def bounded_meshgrid(xs, ys, *args, **kwargs):
        row_chunk_sizes.append(len(ys))
        assert len(ys) <= 256
        return original_meshgrid(xs, ys, *args, **kwargs)

    monkeypatch.setattr(numpy, "meshgrid", bounded_meshgrid)

    masks = _coverage_masks(
        data,
        from_origin(-20, 5125, 10, 10),
        radar_x=5,
        radar_y=5,
        payload=CoverageRequest.model_validate(
            {
                "dem_id": "dem_test",
                "radar": {"lon": 105, "lat": 0, "height_m": 10},
                "target": {"height_m": 0},
                "coverage": {"max_range_m": 100, "scan_mode": "omni"},
                "advanced": {"min_elevation_deg": 0, "max_elevation_deg": 89},
            }
        ),
        target_height_m=0,
        effective_range_m=100,
        analysis_domain=domain,
    )

    assert masks["theoretical"].shape == data.shape
    assert len(row_chunk_sizes) > 1


def test_build_coverage_metrics_preserves_area_identities() -> None:
    true = numpy.ones((2, 2), dtype=bool)
    false = numpy.zeros((2, 2), dtype=bool)
    theoretical = numpy.array([[True, False], [True, False]])
    visible = numpy.array([[True, False], [False, False]])
    masks = {
        "raw_theoretical": true,
        "theoretical": theoretical,
        "unknown": true & ~theoretical,
        "visible": visible,
        "blocked": theoretical & ~visible,
        "terrain": visible,
        "sector": true,
        "requested_range": true,
        "effective_range": true,
        "elevation": true,
        "analysis_domain": theoretical,
    }

    metrics = _build_coverage_metrics(masks, from_origin(0, 20, 10, 10), radar_equation_limited_area=0)

    assert metrics.requested_theoretical_area_m2 == 400
    assert metrics.theoretical_area_m2 == 200
    assert metrics.unknown_area_m2 == 200
    assert metrics.visible_area_m2 == 100
    assert metrics.blocked_area_m2 == 100
    assert metrics.blocked_ratio == 0.5


def test_dem_coverage_ratio_is_one_when_requested_area_is_empty() -> None:
    metrics = CoverageMetrics(
        requested_theoretical_area_m2=0,
        theoretical_area_m2=0,
    )

    assert _dem_coverage_ratio(metrics) == 1


def test_beam_clip_profile_is_capped_to_effective_range(tmp_path: Path) -> None:
    prepared = PreparedCoverageDem(
        source_dem=tmp_path / "source.tif",
        projected_dem=tmp_path / "projected.tif",
        target_epsg=32648,
        radar_x=0,
        radar_y=0,
        projected_bounds=BoundingBox(-20, -20, 20, 20),
        resolution_m=(10, 10),
        dem_coverage_ratio=1,
        beam_clip_profile_m=(1000, 800, 600),
        beam_clip_azimuth_step_deg=2,
    )

    profile = _beam_clip_profile_for_range(prepared, effective_range_m=750)

    assert profile is not None
    assert profile.azimuth_step_deg == 2
    assert profile.radius_m == [750, 750, 600]


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


def test_coverage_metrics_and_model_include_dem_clip_contract() -> None:
    metrics = CoverageMetrics(
        requested_theoretical_area_m2=1600,
        theoretical_area_m2=800,
        unknown_area_m2=800,
        visible_area_m2=500,
        blocked_area_m2=300,
    )
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
        beam_clip_profile={"azimuth_step_deg": 2, "radius_m": [1000, 900]},
    )

    assert metrics.requested_theoretical_area_m2 == metrics.theoretical_area_m2 + metrics.unknown_area_m2
    assert model.beam_clip_profile is not None
    assert model.beam_clip_profile.radius_m == [1000, 900]


def test_legacy_coverage_contract_defaults_new_fields() -> None:
    metrics = CoverageMetrics.model_validate({"theoretical_area_m2": 100})

    assert metrics.requested_theoretical_area_m2 == 100
    assert metrics.unknown_area_m2 == 0


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
