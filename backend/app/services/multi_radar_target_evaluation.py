import json
from pathlib import Path

import numpy
from affine import Affine
from pyproj import Transformer

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.radar import TargetEvaluationRequest
from app.services.multi_radar_task_store import get_multi_task


def evaluate_multi_radar_target(task_id: str, target: TargetEvaluationRequest) -> dict:
    task = get_multi_task(task_id)
    if task.status not in {"finished", "partial"}:
        raise AppError("TASK_NOT_FINISHED", "Target evaluation is available after coverage completes.", status_code=409)
    output_dir = settings.outputs_dir / task_id
    grid_path = output_dir / "grid.json"
    masks_path = output_dir / "station_masks.npz"
    if not grid_path.exists() or not masks_path.exists():
        raise AppError("MULTI_TARGET_DATA_NOT_FOUND", "Station visibility data is unavailable.", status_code=409)
    grid = json.loads(grid_path.read_text(encoding="utf-8"))
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{grid['target_epsg']}", always_xy=True)
    x, y = transformer.transform(target.x, target.y)
    column, row = ~Affine(*grid["transform"]) * (x, y)
    row, column = int(row), int(column)
    shape = tuple(grid["shape"])
    contributors = []
    with numpy.load(masks_path) as masks:
        for station in task.stations:
            detected = bool(
                station.status == "finished"
                and 0 <= row < shape[0]
                and 0 <= column < shape[1]
                and station.radar_id in masks.files
                and masks[station.radar_id][row, column]
            )
            contributors.append({"radar_id": station.radar_id, "detected": detected})
    return {"task_id": task_id, "detected": any(item["detected"] for item in contributors), "contributors": contributors}
