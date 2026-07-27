import re
from dataclasses import dataclass
from pathlib import Path

from app.core.errors import AppError


KIND_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")


@dataclass(frozen=True)
class ArtifactSpec:
    kind: str
    filename: str
    media_type: str
    label: str
    required: bool = True
    public: bool = True


@dataclass(frozen=True)
class OutputContract:
    model_id: str
    version: int
    download_path_template: str
    artifacts: tuple[ArtifactSpec, ...]
    dynamic_kind_pattern: str | None = None

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("Output contract version must be at least 1.")
        if self.download_path_template.count("{task_id}") != 1 or self.download_path_template.count("{kind}") != 1:
            raise ValueError("Download path template must contain task_id and kind exactly once.")
        kinds: set[str] = set()
        filenames: set[str] = set()
        for item in self.artifacts:
            self.validate_spec(item)
            if item.kind in kinds:
                raise ValueError(f"Duplicate artifact kind '{item.kind}'.")
            if item.filename in filenames:
                raise ValueError(f"Duplicate artifact filename '{item.filename}'.")
            kinds.add(item.kind)
            filenames.add(item.filename)
        if self.dynamic_kind_pattern is not None:
            re.compile(self.dynamic_kind_pattern)

    @staticmethod
    def validate_spec(spec: ArtifactSpec) -> None:
        if not KIND_PATTERN.fullmatch(spec.kind):
            raise ValueError(f"Invalid artifact kind '{spec.kind}'.")
        path = Path(spec.filename)
        if path.name != spec.filename or path.is_absolute() or spec.filename in {"", ".", ".."}:
            raise ValueError(f"Artifact filename '{spec.filename}' must be a basename.")
        if not spec.media_type or not spec.label:
            raise ValueError("Artifact media type and label are required.")

    def spec(self, kind: str) -> ArtifactSpec:
        for item in self.artifacts:
            if item.kind == kind:
                return item
        raise AppError("OUTPUT_KIND_NOT_FOUND", f"Output kind '{kind}' is not supported.", status_code=404)

    def accepts_dynamic(self, spec: ArtifactSpec) -> bool:
        self.validate_spec(spec)
        return bool(self.dynamic_kind_pattern and re.fullmatch(self.dynamic_kind_pattern, spec.kind))
