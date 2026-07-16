import json
from pathlib import Path

from app.demo_scenarios.models import ScenarioEnvelope
from app.demo_scenarios.storage import canonical_request_hash, read_json, write_json_atomic


def test_scenario_envelope_keeps_metadata_outside_request() -> None:
    envelope = ScenarioEnvelope(
        scenario_id="uav-recon",
        model_id="uav",
        version=1,
        dem_id="dem_a",
        candidate_index=0,
        request={"dem_id": "dem_a", "route": {"waypoints": []}},
    )

    payload = envelope.to_dict()

    assert payload["scenario"]["synthetic"] is True
    assert "synthetic" not in payload["request"]


def test_request_hash_is_stable_across_key_order() -> None:
    left = {"b": 2, "a": {"y": 1, "x": 0}}
    right = {"a": {"x": 0, "y": 1}, "b": 2}

    assert canonical_request_hash(left) == canonical_request_hash(right)


def test_atomic_json_write_leaves_no_partial_file(tmp_path: Path) -> None:
    target = tmp_path / "scenario-index.json"

    write_json_atomic(target, {"version": 1, "models": {}})

    assert read_json(target) == {"version": 1, "models": {}}
    assert list(tmp_path.glob("*.tmp")) == []
    assert json.loads(target.read_text(encoding="utf-8"))["version"] == 1
