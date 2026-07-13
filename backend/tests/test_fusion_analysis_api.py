import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

from app.core.config import settings
from app.main import app


@pytest.mark.parametrize("coverage_contract_version", [None, 2], ids=["legacy-v1", "v2"])
def test_fusion_analysis_returns_union_overlap_and_blind_area(
    tmp_path: Path,
    coverage_contract_version: int | None,
) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_finished_task(tmp_path, "task_a", coverage_contract_version=coverage_contract_version)
    write_finished_task(tmp_path, "task_b", coverage_contract_version=coverage_contract_version)
    write_task_outputs(
        tmp_path,
        "task_a",
        visible=box(0.0, 0.0, 1.0, 1.0),
        theoretical=box(0.0, 0.0, 2.0, 2.0),
    )
    write_task_outputs(
        tmp_path,
        "task_b",
        visible=box(0.5, 0.0, 1.5, 1.0),
        theoretical=box(0.0, 0.0, 2.0, 2.0),
    )

    response = TestClient(app).post("/api/radar/fusion", json={"task_ids": ["task_a", "task_b"]})

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_ids"] == ["task_a", "task_b"]
    assert payload["metrics"]["task_count"] == 2
    assert payload["metrics"]["union_visible_area_m2"] > payload["metrics"]["overlap_visible_area_m2"] > 0
    assert payload["metrics"]["blind_area_m2"] > 0
    assert payload["visible_union_geojson"]["features"]
    assert payload["overlap_geojson"]["features"]
    assert payload["blind_geojson"]["features"]
    blind = unary_union([shape(feature["geometry"]) for feature in payload["blind_geojson"]["features"]])
    assert blind.bounds == pytest.approx((0.0, 0.0, 2.0, 2.0), abs=1e-9)


def test_fusion_analysis_rejects_mixed_contract_versions(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_finished_task(tmp_path, "task_legacy")
    write_finished_task(tmp_path, "task_v2", coverage_contract_version=2)

    response = TestClient(app).post(
        "/api/radar/fusion",
        json={"task_ids": ["task_legacy", "task_v2"]},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "FUSION_CONTRACT_MISMATCH"


def test_fusion_analysis_rejects_unfinished_task(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_finished_task(tmp_path, "task_a")
    write_finished_task(tmp_path, "task_b", status="running")
    write_task_outputs(
        tmp_path,
        "task_a",
        visible=box(0.0, 0.0, 1.0, 1.0),
        theoretical=box(0.0, 0.0, 2.0, 2.0),
    )

    response = TestClient(app).post("/api/radar/fusion", json={"task_ids": ["task_a", "task_b"]})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "TASK_NOT_FINISHED"


def write_finished_task(
    root: Path,
    task_id: str,
    status: str = "finished",
    coverage_contract_version: int | None = None,
) -> None:
    task_dir = root / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    task = {
        "task_id": task_id,
        "dem_id": "dem_a",
        "status": status,
        "progress": 100 if status == "finished" else 50,
        "message": status,
        "warnings": [],
    }
    if coverage_contract_version is not None:
        task["model"] = {
            "coverage_contract_version": coverage_contract_version,
            "target_epsg": 32631,
            "radar_projected_xy": [0, 0],
            "projected_dem_bounds": [0, 0, 10, 10],
            "projected_dem_resolution_m": [10, 10],
            "max_range_m": 1000,
            "scan_mode": "omni",
            "azimuth_deg": 0,
            "beam_width_deg": 360,
            "simplify_tolerance_m": 10,
        }
    (task_dir / f"{task_id}.json").write_text(
        json.dumps(
            {
                "task": task,
                "payload": {
                    "dem_id": "dem_a",
                    "radar": {"lon": 0.5, "lat": 0.5, "height_m": 10},
                    "target": {"height_m": 0},
                    "coverage": {
                        "max_range_m": 1000,
                        "scan_mode": "omni",
                        "azimuth_deg": 0,
                        "beam_width_deg": 360,
                    },
                },
            }
        ),
        encoding="utf-8",
    )


def write_task_outputs(root: Path, task_id: str, *, visible, theoretical) -> None:
    output_dir = root / "outputs" / task_id
    output_dir.mkdir(parents=True, exist_ok=True)
    write_geojson(output_dir / "visible.geojson", visible, "visible")
    write_geojson(output_dir / "radar_range.geojson", theoretical, "theoretical")


def write_geojson(path: Path, geometry, kind: str) -> None:
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"kind": kind},
                        "geometry": mapping(geometry),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
