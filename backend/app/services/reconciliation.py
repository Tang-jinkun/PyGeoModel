import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.artifacts import ArtifactReconciliationResult
from app.services.air_corridor_task_store import get_air_corridor_task
from app.services.artifact_contracts import get_output_contract
from app.services.artifact_store import get_artifact_store
from app.services.artillery_task_store import get_artillery_task
from app.services.dem_store import find_dem_file
from app.services.mobility_task_store import get_mobility_task
from app.services.multi_radar_task_store import get_multi_task
from app.services.recon_vehicle_task_store import get_recon_vehicle_task
from app.services.task_store import get_task
from app.services.uav_task_store import get_uav_task
from app.services.watchpost_task_store import get_watchpost_task
from app.workers.air_corridor_task import build_air_corridor_artifacts
from app.workers.artillery_task import build_artillery_artifacts
from app.workers.coverage_task import build_coverage_artifacts
from app.workers.mobility_task import build_mobility_artifacts
from app.workers.multi_radar_coverage_task import build_multi_radar_artifacts
from app.workers.recon_vehicle_task import build_recon_vehicle_artifacts
from app.workers.uav_recon_task import build_uav_artifacts
from app.workers.watchpost_task import build_watchpost_artifacts

TaskGetter = Callable[[str], Any]
ArtifactBuilder = Callable[[str, Any, Callable[[str, int], None]], Any]


@dataclass(frozen=True)
class ModelReconciliationAdapter:
    model_id: str
    task_glob: str
    get_task: TaskGetter
    build_artifacts: ArtifactBuilder


MODEL_ADAPTERS: dict[str, ModelReconciliationAdapter] = {
    "radar": ModelReconciliationAdapter("radar", "task_*.json", get_task, build_coverage_artifacts),
    "uav": ModelReconciliationAdapter("uav", "uav_task_*.json", get_uav_task, build_uav_artifacts),
    "watchpost": ModelReconciliationAdapter("watchpost", "watchpost_task_*.json", get_watchpost_task, build_watchpost_artifacts),
    "artillery": ModelReconciliationAdapter("artillery", "artillery_task_*.json", get_artillery_task, build_artillery_artifacts),
    "recon_vehicle": ModelReconciliationAdapter("recon_vehicle", "recon_vehicle_task_*.json", get_recon_vehicle_task, build_recon_vehicle_artifacts),
    "mobility": ModelReconciliationAdapter("mobility", "mobility_task_*.json", get_mobility_task, build_mobility_artifacts),
    "air_corridor": ModelReconciliationAdapter("air_corridor", "air_corridor_task_*.json", get_air_corridor_task, build_air_corridor_artifacts),
    "multi_radar": ModelReconciliationAdapter("multi_radar", "multi_task_*.json", get_multi_task, build_multi_radar_artifacts),
}


def reconcile_all(
    *,
    dry_run: bool = True,
    verify_checksums: bool = False,
    upgrade_legacy: bool = False,
) -> list[ArtifactReconciliationResult]:
    store = get_artifact_store()
    report: list[ArtifactReconciliationResult] = []
    for model_id, adapter in MODEL_ADAPTERS.items():
        contract = get_output_contract(model_id)
        for path in sorted(settings.tasks_dir.glob(adapter.task_glob)):
            result = store.reconcile(
                path.stem,
                contract,
                verify_checksums=verify_checksums,
                upgrade_legacy=upgrade_legacy and not dry_run,
            )
            if result.state == "unavailable" and result.action == "repair_eligible":
                if not _repair_prerequisites_available(adapter, path.stem):
                    result.action = "repair_ineligible"
            report.append(result)
    return report


def repair_selected(model_id: str, task_ids: list[str]) -> list[str]:
    adapter = MODEL_ADAPTERS.get(model_id)
    if adapter is None:
        raise AppError("RECONCILIATION_MODEL_UNKNOWN", f"Unknown model '{model_id}'.")
    if not task_ids:
        raise AppError("RECONCILIATION_SELECTION_REQUIRED", "At least one task ID is required.")
    repaired: list[str] = []
    for task_id in task_ids:
        final_dir = settings.outputs_dir / task_id
        if final_dir.exists():
            raise AppError(
                "ARTIFACT_RESULT_EXISTS",
                f"Artifact directory for '{task_id}' already exists.",
                status_code=409,
            )
        task = adapter.get_task(task_id)
        request = getattr(task, "request", None)
        if request is None:
            raise AppError(
                "TASK_REQUEST_UNAVAILABLE",
                f"Saved request for '{task_id}' is unavailable.",
                status_code=409,
            )
        dem_id = getattr(request, "dem_id", None)
        if not isinstance(dem_id, str) or not dem_id:
            raise AppError("TASK_DEM_UNAVAILABLE", f"Saved DEM for '{task_id}' is unavailable.", status_code=409)
        find_dem_file(dem_id)
        adapter.build_artifacts(task_id, request, lambda _message, _progress: None)
        repaired.append(task_id)
    return repaired


def cleanup_stale_staging_dirs(
    outputs_dir: Path | None = None,
    *,
    max_age_seconds: int = 24 * 3600,
    now_timestamp: float | None = None,
) -> int:
    root = outputs_dir or settings.outputs_dir
    if not root.exists():
        return 0
    cutoff = (time.time() if now_timestamp is None else now_timestamp) - max_age_seconds
    removed = 0
    for candidate in root.glob(".*.staging-*"):
        if candidate.is_dir() and candidate.stat().st_mtime < cutoff:
            shutil.rmtree(candidate)
            removed += 1
    return removed


def _repair_prerequisites_available(adapter: ModelReconciliationAdapter, task_id: str) -> bool:
    try:
        task = adapter.get_task(task_id)
        request = getattr(task, "request", None)
        dem_id = getattr(request, "dem_id", None) if request is not None else None
        if not isinstance(dem_id, str) or not dem_id:
            return False
        find_dem_file(dem_id)
    except (AppError, OSError, ValueError):
        return False
    return True
