from typing import Literal

from pydantic import BaseModel, Field


ResultState = Literal["pending", "ready", "unavailable"]


class ArtifactManifestEntry(BaseModel):
    kind: str
    filename: str
    label: str
    media_type: str
    required: bool = True
    public: bool = True
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ArtifactManifest(BaseModel):
    schema_version: Literal[1] = 1
    task_id: str
    model_id: str
    created_at: str
    contract_version: int = Field(ge=1)
    artifacts: list[ArtifactManifestEntry]


class ArtifactDescriptor(BaseModel):
    kind: str
    label: str
    filename: str
    media_type: str
    required: bool = True
    size_bytes: int | None = None
    exists: bool = False
    download_path: str | None = None
    url: str | None = None
    download_url: str | None = None


class ResultAvailability(BaseModel):
    state: ResultState
    reason_code: str | None = None


class ArtifactReconciliationResult(BaseModel):
    task_id: str
    model_id: str
    state: ResultState
    reason_code: str | None = None
    action: Literal[
        "none",
        "manifest_upgraded",
        "repair_eligible",
        "repair_ineligible",
    ] = "none"


class TaskResultFields(BaseModel):
    result_state: ResultState = "pending"
    result_reason_code: str | None = None
    rerun_of: str | None = None
