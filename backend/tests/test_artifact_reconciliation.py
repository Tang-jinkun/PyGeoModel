import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.core.errors import AppError
from app.services.artifact_contracts import get_output_contract
from app.services.reconciliation import (
    ModelReconciliationAdapter,
    cleanup_stale_staging_dirs,
    reconcile_all,
    repair_selected,
)


def _adapter(builder, getter) -> ModelReconciliationAdapter:
    return ModelReconciliationAdapter(
        model_id="radar",
        task_glob="task_*.json",
        get_task=getter,
        build_artifacts=builder,
    )


def test_dry_run_reports_missing_without_calling_worker(tmp_path: Path, monkeypatch) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    (settings.tasks_dir / "task_missing.json").write_text("{}", encoding="utf-8")
    calls: list[str] = []
    adapter = _adapter(lambda task_id, *_: calls.append(task_id), lambda _: SimpleNamespace(request=None))
    monkeypatch.setattr("app.services.reconciliation.MODEL_ADAPTERS", {"radar": adapter})

    report = reconcile_all(dry_run=True, verify_checksums=True)

    assert report[0].reason_code == "ARTIFACT_DIRECTORY_MISSING"
    assert report[0].action == "repair_ineligible"
    assert calls == []
    assert not settings.outputs_dir.exists() or not any(settings.outputs_dir.iterdir())


def test_upgrade_legacy_only_writes_manifest_for_complete_directory(tmp_path: Path, monkeypatch) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    task_id = "task_complete"
    (settings.tasks_dir / f"{task_id}.json").write_text("{}", encoding="utf-8")
    output_dir = settings.outputs_dir / task_id
    output_dir.mkdir()
    for spec in get_output_contract("radar").artifacts:
        if spec.required:
            (output_dir / spec.filename).write_bytes(b"x")
    adapter = _adapter(lambda *_: None, lambda _: SimpleNamespace(request=None))
    monkeypatch.setattr("app.services.reconciliation.MODEL_ADAPTERS", {"radar": adapter})

    dry_run = reconcile_all(dry_run=True, upgrade_legacy=True)
    assert dry_run[0].reason_code == "ARTIFACT_MANIFEST_MISSING"
    assert not (output_dir / "artifact-manifest.json").exists()

    upgraded = reconcile_all(dry_run=False, upgrade_legacy=True)
    assert upgraded[0].action == "manifest_upgraded"
    assert (output_dir / "artifact-manifest.json").exists()


def test_repair_calls_only_explicit_selected_builder(tmp_path: Path, monkeypatch) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    for task_id in ("task_selected", "task_other"):
        (settings.tasks_dir / f"{task_id}.json").write_text("{}", encoding="utf-8")
    calls: list[str] = []
    request = SimpleNamespace(dem_id="dem-a")
    adapter = _adapter(lambda task_id, *_: calls.append(task_id), lambda _: SimpleNamespace(request=request))
    monkeypatch.setattr("app.services.reconciliation.MODEL_ADAPTERS", {"radar": adapter})
    monkeypatch.setattr("app.services.reconciliation.find_dem_file", lambda _: tmp_path / "dem.tif")

    repaired = repair_selected("radar", ["task_selected"])

    assert repaired == ["task_selected"]
    assert calls == ["task_selected"]


def test_repair_rejects_existing_final_directory(tmp_path: Path, monkeypatch) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    (settings.tasks_dir / "task_existing.json").write_text("{}", encoding="utf-8")
    (settings.outputs_dir / "task_existing").mkdir()
    adapter = _adapter(lambda *_: None, lambda _: SimpleNamespace(request=SimpleNamespace(dem_id="dem-a")))
    monkeypatch.setattr("app.services.reconciliation.MODEL_ADAPTERS", {"radar": adapter})

    with pytest.raises(AppError, match="already exists"):
        repair_selected("radar", ["task_existing"])


def test_cleanup_removes_only_stale_sibling_staging_dirs(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    stale = outputs / ".task_old.staging-abc"
    fresh = outputs / ".task_new.staging-def"
    final = outputs / "task_final"
    for path in (stale, fresh, final):
        path.mkdir()
    old = 1_700_000_000
    os.utime(stale, (old, old))

    removed = cleanup_stale_staging_dirs(outputs, now_timestamp=old + 25 * 3600)

    assert removed == 1
    assert not stale.exists()
    assert fresh.exists()
    assert final.exists()
