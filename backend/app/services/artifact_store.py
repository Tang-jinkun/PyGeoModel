import hashlib
import json
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.artifacts import (
    ArtifactDescriptor,
    ArtifactManifest,
    ArtifactManifestEntry,
    ArtifactReconciliationResult,
    ResultAvailability,
)
from app.services.artifact_contracts import ArtifactSpec, OutputContract


LOGGER = logging.getLogger(__name__)
TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
MANIFEST_FILENAME = "artifact-manifest.json"
HASH_CHUNK_SIZE = 1024 * 1024


class ArtifactStore:
    def __init__(self, outputs_dir: Path) -> None:
        self.outputs_dir = Path(outputs_dir)

    def create_staging_dir(self, task_id: str) -> Path:
        self._validate_task_id(task_id)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        staging = self.outputs_dir / f".{task_id}.staging-{uuid4().hex}"
        staging.mkdir(exist_ok=False)
        return staging

    def publish(
        self,
        task_id: str,
        contract: OutputContract,
        staging_dir: Path,
        *,
        dynamic_artifacts: tuple[ArtifactSpec, ...] = (),
    ) -> ArtifactManifest:
        final_dir = self._task_dir(task_id)
        staging = self._validated_staging_path(task_id, staging_dir)
        if final_dir.exists():
            raise AppError(
                "ARTIFACT_RESULT_EXISTS",
                f"Artifact result for '{task_id}' already exists.",
                status_code=409,
            )

        specs = self._publication_specs(contract, dynamic_artifacts)
        self._reject_undeclared_files(staging, specs)
        entries = self._entries_for_directory(staging, specs, require_declared=True)
        manifest = ArtifactManifest(
            task_id=task_id,
            model_id=contract.model_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            contract_version=contract.version,
            artifacts=entries,
        )
        self._write_manifest(staging / MANIFEST_FILENAME, manifest)
        self._fsync_directory(staging)
        staging.replace(final_dir)
        self._fsync_directory(self.outputs_dir)
        LOGGER.info(
            "artifact result published",
            extra={
                "task_id": task_id,
                "model_id": contract.model_id,
                "manifest_version": manifest.schema_version,
                "result_state": "ready",
            },
        )
        return manifest

    def inspect(
        self,
        task_id: str,
        contract: OutputContract,
        *,
        computation_status: str,
    ) -> ResultAvailability:
        self._validate_task_id(task_id)
        if computation_status in {"pending", "running"}:
            return ResultAvailability(state="pending")
        try:
            self._validated_manifest(task_id, contract)
        except AppError as exc:
            LOGGER.warning(
                "artifact result unavailable",
                extra={
                    "task_id": task_id,
                    "model_id": contract.model_id,
                    "result_state": "unavailable",
                    "reason_code": exc.code,
                },
            )
            return ResultAvailability(state="unavailable", reason_code=exc.code)
        return ResultAvailability(state="ready")

    def list_descriptors(self, task_id: str, contract: OutputContract) -> list[ArtifactDescriptor]:
        self._validate_task_id(task_id)
        try:
            manifest = self._validated_manifest(task_id, contract)
        except AppError:
            return [self._missing_descriptor(item) for item in contract.artifacts if item.public]

        entries = {item.kind: item for item in manifest.artifacts}
        descriptors: list[ArtifactDescriptor] = []
        for spec in contract.artifacts:
            if not spec.public:
                continue
            entry = entries.pop(spec.kind, None)
            descriptors.append(
                self._descriptor(task_id, spec, entry, contract)
                if entry
                else self._missing_descriptor(spec)
            )
        for entry in manifest.artifacts:
            if entry.kind in entries and entry.public:
                spec = ArtifactSpec(
                    kind=entry.kind,
                    filename=entry.filename,
                    media_type=entry.media_type,
                    label=entry.label,
                    required=entry.required,
                    public=entry.public,
                )
                descriptors.append(self._descriptor(task_id, spec, entry, contract))
                entries.pop(entry.kind, None)
        return descriptors

    def resolve_download(
        self,
        task_id: str,
        kind: str,
        contract: OutputContract,
        *,
        computation_status: str,
    ) -> tuple[Path, ArtifactDescriptor]:
        self._validate_task_id(task_id)
        if computation_status in {"pending", "running"}:
            raise AppError(
                "TASK_NOT_FINISHED",
                "Task artifacts are available only after computation finishes.",
                status_code=409,
            )
        availability = self.inspect(task_id, contract, computation_status=computation_status)
        if availability.state != "ready":
            code = availability.reason_code or "ARTIFACT_UNAVAILABLE"
            raise AppError(code, "The requested task result is unavailable.", status_code=410)
        descriptor = next(
            (item for item in self.list_descriptors(task_id, contract) if item.kind == kind),
            None,
        )
        if descriptor is None:
            raise AppError(
                "OUTPUT_KIND_NOT_FOUND",
                f"Output kind '{kind}' is not supported.",
                status_code=404,
            )
        if not descriptor.exists:
            raise AppError("ARTIFACT_UNAVAILABLE", "The requested artifact is unavailable.", status_code=410)
        return self._contained_file(self._task_dir(task_id), descriptor.filename), descriptor

    def delete(self, task_id: str) -> bool:
        target = self._task_dir(task_id)
        if not target.exists():
            return False
        shutil.rmtree(target)
        self._fsync_directory(self.outputs_dir)
        return True

    def reconcile(
        self,
        task_id: str,
        contract: OutputContract,
        *,
        verify_checksums: bool = False,
        upgrade_legacy: bool = False,
    ) -> ArtifactReconciliationResult:
        task_dir = self._task_dir(task_id)
        manifest_path = task_dir / MANIFEST_FILENAME
        if task_dir.exists() and not manifest_path.exists() and upgrade_legacy:
            try:
                entries = self._entries_for_directory(
                    task_dir, contract.artifacts, require_declared=True
                )
            except AppError as exc:
                return self._reconciliation_result(task_id, contract, exc.code)
            manifest = ArtifactManifest(
                task_id=task_id,
                model_id=contract.model_id,
                created_at=datetime.now(timezone.utc).isoformat(),
                contract_version=contract.version,
                artifacts=entries,
            )
            self._write_manifest(manifest_path, manifest)
            self._fsync_directory(task_dir)
            return ArtifactReconciliationResult(
                task_id=task_id,
                model_id=contract.model_id,
                state="ready",
                action="manifest_upgraded",
            )
        try:
            manifest = self._validated_manifest(task_id, contract)
            if verify_checksums:
                for entry in manifest.artifacts:
                    path = self._contained_file(task_dir, entry.filename)
                    if self._sha256(path) != entry.sha256:
                        raise AppError(
                            "ARTIFACT_CHECKSUM_MISMATCH",
                            f"Artifact '{entry.kind}' checksum does not match its manifest.",
                        )
        except AppError as exc:
            return self._reconciliation_result(task_id, contract, exc.code)
        return ArtifactReconciliationResult(
            task_id=task_id,
            model_id=contract.model_id,
            state="ready",
        )

    def _validated_manifest(self, task_id: str, contract: OutputContract) -> ArtifactManifest:
        task_dir = self._task_dir(task_id)
        if not task_dir.is_dir():
            raise AppError(
                "ARTIFACT_DIRECTORY_MISSING",
                f"Artifact directory for '{task_id}' is missing.",
            )
        path = task_dir / MANIFEST_FILENAME
        if not path.is_file():
            raise AppError("ARTIFACT_MANIFEST_MISSING", "Artifact manifest is missing.")
        try:
            manifest = ArtifactManifest.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValidationError, ValueError) as exc:
            raise AppError("ARTIFACT_MANIFEST_INVALID", "Artifact manifest is invalid.") from exc
        if (
            manifest.task_id != task_id
            or manifest.model_id != contract.model_id
            or manifest.contract_version != contract.version
        ):
            raise AppError("ARTIFACT_MANIFEST_MISMATCH", "Artifact manifest identity does not match.")
        entries = {item.kind: item for item in manifest.artifacts}
        if len(entries) != len(manifest.artifacts):
            raise AppError("ARTIFACT_MANIFEST_INVALID", "Artifact manifest contains duplicate kinds.")
        for spec in contract.artifacts:
            entry = entries.get(spec.kind)
            if spec.required and entry is None:
                raise AppError(
                    "ARTIFACT_REQUIRED_FILE_MISSING",
                    f"Required artifact '{spec.kind}' is absent from the manifest.",
                )
            if entry is not None and (
                entry.filename != spec.filename
                or entry.media_type != spec.media_type
                or entry.required != spec.required
                or entry.public != spec.public
            ):
                raise AppError(
                    "ARTIFACT_MANIFEST_MISMATCH",
                    f"Artifact '{spec.kind}' does not match its output contract.",
                )
        static_kinds = {item.kind for item in contract.artifacts}
        for entry in manifest.artifacts:
            if entry.kind not in static_kinds:
                dynamic = ArtifactSpec(
                    entry.kind,
                    entry.filename,
                    entry.media_type,
                    entry.label,
                    entry.required,
                    entry.public,
                )
                if not contract.accepts_dynamic(dynamic):
                    raise AppError(
                        "ARTIFACT_DYNAMIC_KIND_INVALID",
                        f"Dynamic artifact '{entry.kind}' is not allowed.",
                    )
            artifact_path = self._contained_file(task_dir, entry.filename)
            if not artifact_path.is_file():
                raise AppError(
                    "ARTIFACT_REQUIRED_FILE_MISSING" if entry.required else "ARTIFACT_FILE_MISSING",
                    f"Artifact '{entry.kind}' is missing.",
                )
            if artifact_path.stat().st_size != entry.size_bytes:
                raise AppError(
                    "ARTIFACT_SIZE_MISMATCH",
                    f"Artifact '{entry.kind}' size does not match its manifest.",
                )
        return manifest

    def _publication_specs(
        self, contract: OutputContract, dynamic_artifacts: tuple[ArtifactSpec, ...]
    ) -> tuple[ArtifactSpec, ...]:
        specs = list(contract.artifacts)
        kinds = {item.kind for item in specs}
        filenames = {item.filename for item in specs}
        for item in dynamic_artifacts:
            if not contract.accepts_dynamic(item):
                raise AppError(
                    "ARTIFACT_DYNAMIC_KIND_INVALID",
                    f"Dynamic artifact '{item.kind}' is not allowed.",
                )
            if item.kind in kinds or item.filename in filenames:
                raise AppError(
                    "ARTIFACT_DYNAMIC_KIND_INVALID",
                    f"Dynamic artifact '{item.kind}' conflicts with the output contract.",
                )
            kinds.add(item.kind)
            filenames.add(item.filename)
            specs.append(item)
        return tuple(specs)

    @staticmethod
    def _reject_undeclared_files(directory: Path, specs: tuple[ArtifactSpec, ...]) -> None:
        declared = {item.filename for item in specs}
        undeclared = sorted(item.name for item in directory.iterdir() if item.name not in declared)
        if undeclared:
            raise AppError(
                "ARTIFACT_UNDECLARED_FILE",
                f"Staging directory contains undeclared entries: {', '.join(undeclared)}.",
            )

    def _entries_for_directory(
        self,
        directory: Path,
        specs: tuple[ArtifactSpec, ...],
        *,
        require_declared: bool,
    ) -> list[ArtifactManifestEntry]:
        entries: list[ArtifactManifestEntry] = []
        for spec in specs:
            path = self._contained_file(directory, spec.filename)
            if not path.is_file():
                if spec.required and require_declared:
                    raise AppError(
                        "ARTIFACT_REQUIRED_FILE_MISSING",
                        f"Required artifact '{spec.kind}' is missing.",
                    )
                continue
            size = path.stat().st_size
            if spec.required and size <= 0:
                raise AppError(
                    "ARTIFACT_REQUIRED_FILE_EMPTY",
                    f"Required artifact '{spec.kind}' is empty.",
                )
            entries.append(
                ArtifactManifestEntry(
                    kind=spec.kind,
                    filename=spec.filename,
                    label=spec.label,
                    media_type=spec.media_type,
                    required=spec.required,
                    public=spec.public,
                    size_bytes=size,
                    sha256=self._sha256(path),
                )
            )
        return entries

    def _descriptor(
        self,
        task_id: str,
        spec: ArtifactSpec,
        entry: ArtifactManifestEntry,
        contract: OutputContract,
    ) -> ArtifactDescriptor:
        download_path = spec_download_path(task_id, spec.kind, contract)
        return ArtifactDescriptor(
            kind=spec.kind,
            label=spec.label,
            filename=spec.filename,
            media_type=spec.media_type,
            required=spec.required,
            size_bytes=entry.size_bytes,
            exists=True,
            download_path=download_path,
            download_url=download_path,
        )

    @staticmethod
    def _missing_descriptor(spec: ArtifactSpec) -> ArtifactDescriptor:
        return ArtifactDescriptor(
            kind=spec.kind,
            label=spec.label,
            filename=spec.filename,
            media_type=spec.media_type,
            required=spec.required,
        )

    def _task_dir(self, task_id: str) -> Path:
        self._validate_task_id(task_id)
        root = self.outputs_dir.resolve()
        path = (self.outputs_dir / task_id).resolve()
        if path.parent != root:
            raise AppError("INVALID_OUTPUT_PATH", "Resolved task directory escapes output root.")
        return path

    def _validated_staging_path(self, task_id: str, staging_dir: Path) -> Path:
        root = self.outputs_dir.resolve()
        path = Path(staging_dir).resolve()
        if path.parent != root or not path.name.startswith(f".{task_id}.staging-"):
            raise AppError("INVALID_OUTPUT_PATH", "Staging directory is not owned by this task.")
        if not path.is_dir():
            raise AppError("ARTIFACT_STAGING_MISSING", "Artifact staging directory is missing.")
        return path

    @staticmethod
    def _contained_file(directory: Path, filename: str) -> Path:
        root = directory.resolve()
        path = (directory / filename).resolve()
        if path.parent != root:
            raise AppError("INVALID_OUTPUT_PATH", "Resolved artifact path escapes task directory.")
        return path

    @staticmethod
    def _validate_task_id(task_id: str) -> None:
        if not TASK_ID_PATTERN.fullmatch(task_id):
            raise AppError("INVALID_TASK_ID", "Task id contains unsupported characters.", status_code=400)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(HASH_CHUNK_SIZE):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _write_manifest(path: Path, manifest: ArtifactManifest) -> None:
        temp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temp.open("w", encoding="utf-8") as target:
                json.dump(manifest.model_dump(mode="json"), target, ensure_ascii=False, indent=2)
                target.flush()
                os.fsync(target.fileno())
            temp.replace(path)
        finally:
            if temp.exists():
                temp.unlink()

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        if os.name == "nt" or not path.exists():
            return
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _reconciliation_result(
        task_id: str, contract: OutputContract, reason_code: str
    ) -> ArtifactReconciliationResult:
        return ArtifactReconciliationResult(
            task_id=task_id,
            model_id=contract.model_id,
            state="unavailable",
            reason_code=reason_code,
            action=(
                "repair_eligible"
                if reason_code
                in {
                    "ARTIFACT_DIRECTORY_MISSING",
                    "ARTIFACT_MANIFEST_MISSING",
                    "ARTIFACT_REQUIRED_FILE_MISSING",
                    "ARTIFACT_SIZE_MISMATCH",
                    "ARTIFACT_CHECKSUM_MISMATCH",
                }
                else "repair_ineligible"
            ),
        )

def spec_download_path(task_id: str, kind: str, contract: OutputContract) -> str:
    return contract.download_path_template.format(task_id=task_id, kind=kind)


def get_artifact_store() -> ArtifactStore:
    return ArtifactStore(settings.outputs_dir)
