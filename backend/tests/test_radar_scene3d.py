from pathlib import Path

import numpy
import rasterio
from rasterio.coords import BoundingBox
from rasterio.transform import from_origin

from app.schemas.radar import CoverageRequest
from app.scene3d.exporter import read_glb_document
from app.scene3d.radar import RayResult, _shell_mesh, _trace_ray, write_radar_coverage_glb
from app.services.coverage_model import PreparedCoverageDem
from app.services.output_files import OUTPUT_FILENAMES, OUTPUT_MEDIA_TYPES


def test_shell_does_not_bridge_terrain_shadow_to_full_range() -> None:
    points = [
        [numpy.array([0, 0, 0]), numpy.array([1, 0, 0]), numpy.array([2, 0, 0])],
        [numpy.array([0, 1, 0]), numpy.array([1, 1, 0]), numpy.array([2, 1, 0])],
    ]
    nominal = RayResult(1_000, (0, 0, 0), "nominal", True)
    terrain = RayResult(100, (0, 0, 0), "terrain", True)

    mesh = _shell_mesh(
        points,
        [[nominal, nominal, terrain], [nominal, nominal, terrain]],
        False,
    )

    assert len(mesh.faces) == 2


def test_target_independent_radar_glb_is_self_contained_and_open_at_nodata(
    tmp_path: Path,
) -> None:
    defaults = CoverageRequest.model_validate(
        {
            "dem_id": "dem_radar",
            "radar": {"lon": 79.0, "lat": 31.5, "height_m": 30},
            "coverage": {"max_range_m": 1_000},
        }
    )
    assert defaults.advanced.min_elevation_deg == -8
    assert defaults.advanced.max_elevation_deg == 24

    dem_path = tmp_path / "radar-dem.tif"
    dem = numpy.full((21, 21), 1_000, dtype=numpy.float32)
    dem[9:12, 14] = 1_450
    dem[0:5, 17:21] = -9999
    transform = from_origin(-1_050, 1_050, 100, 100)
    with rasterio.open(
        dem_path,
        "w",
        driver="GTiff",
        width=dem.shape[1],
        height=dem.shape[0],
        count=1,
        dtype=dem.dtype,
        crs="EPSG:32644",
        transform=transform,
        nodata=-9999,
    ) as dataset:
        dataset.write(dem, 1)

    payload = CoverageRequest.model_validate(
        {
            "dem_id": "dem_radar",
            "radar": {"lon": 79.0, "lat": 31.5, "height_m": 30},
            "coverage": {
                "max_range_m": 1_000,
                "scan_mode": "sector",
                "azimuth_deg": 90,
                "beam_width_deg": 120,
            },
            "advanced": {
                "min_elevation_deg": 0,
                "max_elevation_deg": 36,
                "use_curvature": True,
                "curvature_coeff": 0.75,
            },
        }
    )
    prepared = PreparedCoverageDem(
        source_dem=dem_path,
        projected_dem=dem_path,
        target_epsg=32644,
        radar_x=0,
        radar_y=0,
        projected_bounds=BoundingBox(-1_050, -1_050, 1_050, 1_050),
        resolution_m=(100, 100),
        dem_coverage_ratio=0.9,
        analysis_domain=dem != -9999,
    )
    output = tmp_path / "radar_detection_domain.glb"

    terrain_contact = _trace_ray(
        dem,
        dem != -9999,
        transform,
        -9999,
        prepared,
        payload,
        90,
        0,
        1_030,
        1_000,
        "nominal",
        100,
    )
    assert terrain_contact.termination == "terrain"
    assert terrain_contact.point[2] == 1_450

    metadata = write_radar_coverage_glb(
        output,
        task_id="radar_task_demo",
        prepared=prepared,
        payload=payload,
    )

    document = read_glb_document(output.read_bytes())
    node_names = {node.get("name") for node in document["nodes"]}
    assert {
        "radar_result",
        "radar_result/radar_origin",
        "radar_result/detectable_shell",
        "radar_result/shell_grid",
        "radar_result/diagnostics",
    } <= node_names
    assert metadata["model_id"] == "radar"
    assert metadata["range_basis"] == "nominal"
    assert metadata["reference_rcs_m2"] == 1
    assert metadata["ray_grid"]["azimuth_count"] > 2
    assert metadata["ray_grid"]["elevation_count"] > 2
    assert metadata["terminations"]["terrain"] > 0
    assert metadata["terminations"]["nodata"] > 0
    assert metadata["open_ray_count"] > 0
    assert document.get("buffers", [{}])[0].get("uri") is None
    assert all(image.get("uri") is None for image in document.get("images", []))
    assert OUTPUT_FILENAMES["scene_glb"] == "radar_detection_domain.glb"
    assert OUTPUT_MEDIA_TYPES["scene_glb"] == "model/gltf-binary"
