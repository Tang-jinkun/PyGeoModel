from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.radar import MultiRadarRequest
from app.services.multi_radar_task_store import create_multi_task, get_multi_task


def station(radar_id: str) -> dict:
    return {
        "radar_id": radar_id,
        "radar": {"lon": 79.0, "lat": 31.5, "height_m": 30},
        "coverage": {"max_range_m": 1_000},
    }


def test_multi_radar_request_rejects_duplicate_station_ids() -> None:
    with pytest.raises(ValidationError, match="radar_id"):
        MultiRadarRequest.model_validate(
            {"dem_id": "dem_a", "radars": [station("north"), station("north")]}
        )


def test_multi_task_round_trip_preserves_station_requests(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    payload = MultiRadarRequest.model_validate(
        {"dem_id": "dem_a", "radars": [station("north"), station("south")]}
    )

    task = create_multi_task(payload)
    stored = get_multi_task(task.task_id)

    assert task.task_id.startswith("multi_task_")
    assert stored.request is not None
    assert [item.radar_id for item in stored.request.radars] == ["north", "south"]
