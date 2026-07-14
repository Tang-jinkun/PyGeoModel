from pathlib import Path

from app.demo_scenarios.models import ScenarioEnvelope
from app.demo_scenarios.runner import run_scenarios


MODEL_ORDER = [
    "uav",
    "watchpost",
    "artillery",
    "recon_vehicle",
    "mobility",
    "air_corridor",
]


class FakeClient:
    def __init__(self) -> None:
        self.created: list[str] = []
        self.retry_count = 0

    def health(self) -> None:
        pass

    def find_matching_task(self, spec, request_hash):
        return None

    def create_task(self, spec, request):
        candidate_index = request.get("candidate_index", 0)
        self.created.append(spec.model_id)
        return f"{spec.model_id}_task_{candidate_index}"

    def wait_for_task(self, spec, task_id):
        return {"status": "finished", "task_id": task_id}

    def task_result(self, spec, task_id):
        metrics = {
            "uav": {
                "route_length_m": 1,
                "coverage_point_count": 2,
                "visible_area_m2": 1,
                "blocked_area_m2": 1,
            },
            "watchpost": {"blocked_ratio": 0.4},
            "artillery": {
                "theoretical_area_m2": 1,
                "reachable_area_m2": 1,
                "terrain_masked_area_m2": 1,
                "sample_point_count": 1,
            },
            "recon_vehicle": {
                "route_length_m": 1,
                "coverage_point_count": 2,
                "visible_area_m2": 1,
                "blocked_area_m2": 1,
            },
            "mobility": {
                "wheeled": {"reachable": True, "travel_time_seconds": 100},
                "tracked": {"reachable": True, "travel_time_seconds": 140},
            },
            "air_corridor": {
                "route_found": True,
                "corridor_length_m": 1,
                "altitude_change_count": 1,
            },
        }[spec.model_id]
        outputs = [
            {
                "kind": kind,
                "filename": f"{kind}.geojson",
                "media_type": "application/geo+json",
            }
            for kind in spec.required_outputs
        ]
        return metrics, outputs


def fake_scenario(
    _data_dir: Path,
    dem_id: str,
    model_id: str,
    candidate_index: int,
) -> ScenarioEnvelope:
    return ScenarioEnvelope(
        model_id,
        model_id,
        1,
        dem_id,
        candidate_index,
        {"dem_id": dem_id, "candidate_index": candidate_index},
    )


def test_runner_submits_models_in_fixed_order_and_writes_index(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.demo_scenarios.runner.generate_one", fake_scenario)
    client = FakeClient()

    index = run_scenarios(tmp_path, "dem_a", client, max_candidates=1)

    assert client.created == MODEL_ORDER
    assert all(item["accepted"] for item in index["models"].values())
    assert (tmp_path / "demo-scenarios" / "dem_a" / "scenario-index.json").exists()


def test_failed_model_does_not_block_later_models(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("app.demo_scenarios.runner.generate_one", fake_scenario)
    client = FakeClient()
    original_result = client.task_result

    def fail_watchpost(spec, task_id):
        if spec.model_id == "watchpost":
            raise RuntimeError("synthetic watchpost failure")
        return original_result(spec, task_id)

    client.task_result = fail_watchpost

    index = run_scenarios(tmp_path, "dem_a", client, max_candidates=1)

    assert index["models"]["watchpost"]["accepted"] is False
    assert "synthetic watchpost failure" in index["models"]["watchpost"][
        "failure_reason"
    ]
    assert client.created[-4:] == [
        "artillery",
        "recon_vehicle",
        "mobility",
        "air_corridor",
    ]


def test_runner_uses_next_candidate_after_acceptance_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.demo_scenarios.runner.generate_one", fake_scenario)
    client = FakeClient()
    original_result = client.task_result

    def reject_first_watchpost(spec, task_id):
        metrics, outputs = original_result(spec, task_id)
        if spec.model_id == "watchpost" and task_id.endswith("_0"):
            metrics = {"blocked_ratio": 0}
        return metrics, outputs

    client.task_result = reject_first_watchpost

    index = run_scenarios(tmp_path, "dem_a", client, max_candidates=2)

    watchpost = index["models"]["watchpost"]
    assert watchpost["accepted"] is True
    assert watchpost["candidate_index"] == 1
    assert watchpost["candidate_attempts"] == 2
    assert client.created.count("watchpost") == 2
