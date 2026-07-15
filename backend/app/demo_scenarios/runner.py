import time
from pathlib import Path
from typing import Any

from app.demo_scenarios.api_client import DemoApiClient
from app.demo_scenarios.generator import MODEL_ORDER, generate_one
from app.demo_scenarios.models import ScenarioEnvelope, ScenarioIndexEntry
from app.demo_scenarios.registry import MODEL_SPECS
from app.demo_scenarios.storage import canonical_request_hash, write_json_atomic


def _run_one(
    client: DemoApiClient,
    scenario: ScenarioEnvelope,
    rebuild: bool,
) -> ScenarioIndexEntry:
    spec = MODEL_SPECS[scenario.model_id]
    request_hash = canonical_request_hash(scenario.request)
    started = time.monotonic()
    retries_before = client.retry_count
    task_id = None if rebuild else client.find_matching_task(spec, request_hash)
    if task_id is None:
        task_id = client.create_task(spec, scenario.request)
    client.wait_for_task(spec, task_id)
    metrics, outputs = client.task_result(spec, task_id)
    available_output_kinds = {
        str(item["kind"])
        for item in outputs
        if item.get("exists") is True
    }
    errors = spec.validate(metrics, available_output_kinds)
    return ScenarioIndexEntry(
        scenario_id=scenario.scenario_id,
        model_id=scenario.model_id,
        version=scenario.version,
        dem_id=scenario.dem_id,
        request_file=f"{scenario.scenario_id}.json",
        request_hash=request_hash,
        task_id=task_id,
        status="finished",
        duration_seconds=round(time.monotonic() - started, 3),
        retries=client.retry_count - retries_before,
        candidate_index=scenario.candidate_index,
        candidate_attempts=scenario.candidate_index + 1,
        metrics=metrics,
        outputs=tuple(outputs),
        accepted=not errors,
        failure_reason="; ".join(errors) or None,
    )


def run_scenarios(
    data_dir: Path,
    dem_id: str,
    client: DemoApiClient,
    *,
    rebuild: bool = False,
    max_candidates: int = 4,
) -> dict[str, Any]:
    client.health()
    results: dict[str, Any] = {}
    for model_id in MODEL_ORDER:
        last_error: str | None = None
        for candidate_index in range(max_candidates):
            try:
                scenario = generate_one(
                    data_dir,
                    dem_id,
                    model_id,
                    candidate_index,
                )
                entry = _run_one(client, scenario, rebuild)
                results[model_id] = entry.to_dict()
                if entry.accepted:
                    break
                last_error = entry.failure_reason
            except Exception as exc:
                last_error = str(exc)
                results[model_id] = {
                    "model_id": model_id,
                    "status": "failed",
                    "accepted": False,
                    "candidate_index": candidate_index,
                    "candidate_attempts": candidate_index + 1,
                    "failure_reason": last_error,
                    "synthetic": True,
                }
        if not results[model_id].get("accepted"):
            results[model_id]["failure_reason"] = last_error

    index = {
        "version": 1,
        "synthetic": True,
        "dem_id": dem_id,
        "models": results,
    }
    write_json_atomic(
        data_dir / "demo-scenarios" / dem_id / "scenario-index.json",
        index,
    )
    return index
