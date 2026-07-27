import json
from pathlib import Path

import pytest

from app.core.errors import AppError
from app.services.artifact_contracts import ArtifactSpec, OutputContract
from app.services.artifact_store import ArtifactStore


@pytest.fixture
def contract() -> OutputContract:
    return OutputContract(
        model_id="test_model",
        version=1,
        download_path_template="/api/test/tasks/{task_id}/outputs/{kind}",
        artifacts=(
            ArtifactSpec("required_json", "required.json", "application/json", "Required"),
            ArtifactSpec(
                "optional_bin",
                "optional.bin",
                "application/octet-stream",
                "Optional",
                required=False,
            ),
            ArtifactSpec(
                "internal_json",
                "internal.json",
                "application/json",
                "Internal",
                public=False,
            ),
        ),
        dynamic_kind_pattern=r"height_(visible|blocked)_[0-9A-Za-z_]+",
    )


def write_required(staging: Path) -> None:
    (staging / "required.json").write_text('{"ok":true}', encoding="utf-8")
    (staging / "internal.json").write_text("{}", encoding="utf-8")


def test_publish_renames_complete_sibling_and_writes_checksums(
    tmp_path: Path, contract: OutputContract
) -> None:
    store = ArtifactStore(tmp_path / "outputs")
    staging = store.create_staging_dir("task_valid")
    write_required(staging)

    manifest = store.publish("task_valid", contract, staging)

    final = tmp_path / "outputs" / "task_valid"
    assert not staging.exists()
    assert manifest.schema_version == 1
    required = next(item for item in manifest.artifacts if item.kind == "required_json")
    assert required.sha256 == "4062edaf750fb8074e7e83e0c9028c94e32468a8b6f1614774328ef045150f93"
    assert (final / "artifact-manifest.json").exists()
    assert store.inspect("task_valid", contract, computation_status="finished").state == "ready"


def test_publish_rejects_missing_required_artifact_without_visible_result(
    tmp_path: Path, contract: OutputContract
) -> None:
    store = ArtifactStore(tmp_path / "outputs")
    staging = store.create_staging_dir("task_missing")
    (staging / "internal.json").write_text("{}", encoding="utf-8")

    with pytest.raises(AppError, match="required_json"):
        store.publish("task_missing", contract, staging)

    assert staging.exists()
    assert not (tmp_path / "outputs" / "task_missing").exists()


def test_optional_and_dynamic_artifacts_are_described_from_manifest(
    tmp_path: Path, contract: OutputContract
) -> None:
    store = ArtifactStore(tmp_path / "outputs")
    staging = store.create_staging_dir("task_dynamic")
    write_required(staging)
    (staging / "visible_h_0.geojson").write_text(
        '{"type":"FeatureCollection","features":[]}', encoding="utf-8"
    )
    dynamic = ArtifactSpec(
        "height_visible_0",
        "visible_h_0.geojson",
        "application/geo+json",
        "Visible at 0 m",
    )

    store.publish("task_dynamic", contract, staging, dynamic_artifacts=(dynamic,))
    descriptors = store.list_descriptors("task_dynamic", contract)

    assert [item.kind for item in descriptors] == [
        "required_json",
        "optional_bin",
        "height_visible_0",
    ]
    optional = next(item for item in descriptors if item.kind == "optional_bin")
    assert optional.exists is False
    assert optional.size_bytes is None
    assert optional.download_path is None
    dynamic_info = next(item for item in descriptors if item.kind == "height_visible_0")
    assert dynamic_info.download_path == "/api/test/tasks/task_dynamic/outputs/height_visible_0"
    assert dynamic_info.download_url == dynamic_info.download_path
    assert dynamic_info.url is None


def test_publish_rejects_unregistered_dynamic_kind(tmp_path: Path, contract: OutputContract) -> None:
    store = ArtifactStore(tmp_path / "outputs")
    staging = store.create_staging_dir("task_bad_dynamic")
    write_required(staging)
    (staging / "other.json").write_text("{}", encoding="utf-8")

    with pytest.raises(AppError) as raised:
        store.publish(
            "task_bad_dynamic",
            contract,
            staging,
            dynamic_artifacts=(ArtifactSpec("other", "other.json", "application/json", "Other"),),
        )

    assert raised.value.code == "ARTIFACT_DYNAMIC_KIND_INVALID"


def test_publish_rejects_undeclared_staging_files(tmp_path: Path, contract: OutputContract) -> None:
    store = ArtifactStore(tmp_path / "outputs")
    staging = store.create_staging_dir("task_undeclared")
    write_required(staging)
    (staging / "dem_projected.tif").write_bytes(b"temporary")

    with pytest.raises(AppError) as raised:
        store.publish("task_undeclared", contract, staging)

    assert raised.value.code == "ARTIFACT_UNDECLARED_FILE"
    assert staging.exists()
    assert not (tmp_path / "outputs" / "task_undeclared").exists()


def test_inspect_marks_finished_result_unavailable_when_size_changes(
    tmp_path: Path, contract: OutputContract
) -> None:
    store = ArtifactStore(tmp_path / "outputs")
    staging = store.create_staging_dir("task_stale")
    write_required(staging)
    store.publish("task_stale", contract, staging)
    (tmp_path / "outputs" / "task_stale" / "required.json").write_text("changed", encoding="utf-8")

    state = store.inspect("task_stale", contract, computation_status="finished")

    assert state.state == "unavailable"
    assert state.reason_code == "ARTIFACT_SIZE_MISMATCH"


def test_pending_task_does_not_advertise_existing_uncommitted_result(
    tmp_path: Path, contract: OutputContract
) -> None:
    store = ArtifactStore(tmp_path / "outputs")
    assert store.inspect("task_pending", contract, computation_status="running").state == "pending"


def test_resolve_download_rejects_traversal_and_unavailable_result(
    tmp_path: Path, contract: OutputContract
) -> None:
    store = ArtifactStore(tmp_path / "outputs")
    with pytest.raises(AppError) as invalid:
        store.resolve_download("../task", "required_json", contract, computation_status="finished")
    assert invalid.value.status_code == 400

    with pytest.raises(AppError) as missing:
        store.resolve_download("task_missing", "required_json", contract, computation_status="finished")
    assert missing.value.status_code == 410
    assert missing.value.code == "ARTIFACT_DIRECTORY_MISSING"


def test_resolve_download_distinguishes_pending_and_unknown_kind(
    tmp_path: Path, contract: OutputContract
) -> None:
    store = ArtifactStore(tmp_path / "outputs")
    with pytest.raises(AppError) as pending:
        store.resolve_download("task_pending", "required_json", contract, computation_status="running")
    assert pending.value.status_code == 409

    staging = store.create_staging_dir("task_ready")
    write_required(staging)
    store.publish("task_ready", contract, staging)
    with pytest.raises(AppError) as unknown:
        store.resolve_download("task_ready", "unknown", contract, computation_status="finished")
    assert unknown.value.status_code == 404


def test_reconcile_detects_checksum_mismatch(tmp_path: Path, contract: OutputContract) -> None:
    store = ArtifactStore(tmp_path / "outputs")
    staging = store.create_staging_dir("task_corrupt")
    write_required(staging)
    store.publish("task_corrupt", contract, staging)
    target = tmp_path / "outputs" / "task_corrupt" / "required.json"
    target.write_text('{"no":true}', encoding="utf-8")
    manifest_path = target.parent / "artifact-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = next(item for item in manifest["artifacts"] if item["kind"] == "required_json")
    entry["size_bytes"] = target.stat().st_size
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = store.reconcile("task_corrupt", contract, verify_checksums=True)

    assert result.state == "unavailable"
    assert result.reason_code == "ARTIFACT_CHECKSUM_MISMATCH"


def test_reconcile_can_upgrade_complete_legacy_directory(
    tmp_path: Path, contract: OutputContract
) -> None:
    store = ArtifactStore(tmp_path / "outputs")
    legacy = tmp_path / "outputs" / "task_legacy"
    legacy.mkdir(parents=True)
    write_required(legacy)

    dry_run = store.reconcile("task_legacy", contract)
    upgraded = store.reconcile("task_legacy", contract, upgrade_legacy=True)

    assert dry_run.reason_code == "ARTIFACT_MANIFEST_MISSING"
    assert upgraded.state == "ready"
    assert upgraded.action == "manifest_upgraded"
    assert (legacy / "artifact-manifest.json").exists()


def test_delete_is_retry_safe(tmp_path: Path, contract: OutputContract) -> None:
    store = ArtifactStore(tmp_path / "outputs")
    staging = store.create_staging_dir("task_delete")
    write_required(staging)
    store.publish("task_delete", contract, staging)

    assert store.delete("task_delete") is True
    assert store.delete("task_delete") is False


@pytest.mark.parametrize(
    "filename",
    ["../escape.json", "/absolute.json", "nested/file.json"],
)
def test_contract_rejects_non_basename_artifacts(filename: str) -> None:
    with pytest.raises(ValueError):
        OutputContract(
            model_id="unsafe",
            version=1,
            download_path_template="/api/test/{task_id}/{kind}",
            artifacts=(ArtifactSpec("unsafe", filename, "application/json", "Unsafe"),),
        )
