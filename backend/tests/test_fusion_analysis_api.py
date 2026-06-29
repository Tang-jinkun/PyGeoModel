import json
from pathlib import Path

from fastapi.testclient import TestClient
from shapely.geometry import box, mapping

from app.core.config import settings
from app.main import app


def test_fusion_analysis_returns_union_overlap_and_blind_area(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    write_finished_task(tmp_path, "task_a")
    write_finished_task(tmp_path, "task_b")
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


def write_finished_task(root: Path, task_id: str, status: str = "finished") -> None:
    task_dir = root / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / f"{task_id}.json").write_text(
        json.dumps(
            {
                "task": {
                    "task_id": task_id,
                    "dem_id": "dem_a",
                    "status": status,
                    "progress": 100 if status == "finished" else 50,
                    "message": status,
                    "warnings": [],
                },
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
