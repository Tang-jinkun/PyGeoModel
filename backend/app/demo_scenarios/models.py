from dataclasses import dataclass, field
from typing import Any


JsonObject = dict[str, Any]


@dataclass(frozen=True)
class ScenarioEnvelope:
    scenario_id: str
    model_id: str
    version: int
    dem_id: str
    candidate_index: int
    request: JsonObject
    artifacts: tuple[str, ...] = ()

    def to_dict(self) -> JsonObject:
        return {
            "scenario": {
                "id": self.scenario_id,
                "model_id": self.model_id,
                "version": self.version,
                "synthetic": True,
                "dem_id": self.dem_id,
                "candidate_index": self.candidate_index,
                "artifacts": list(self.artifacts),
            },
            "request": self.request,
        }


@dataclass(frozen=True)
class ScenarioIndexEntry:
    scenario_id: str
    model_id: str
    version: int
    dem_id: str
    request_file: str
    request_hash: str
    task_id: str
    status: str
    duration_seconds: float
    retries: int
    candidate_index: int
    candidate_attempts: int
    metrics: JsonObject = field(default_factory=dict)
    outputs: tuple[JsonObject, ...] = ()
    accepted: bool = False
    failure_reason: str | None = None

    def to_dict(self) -> JsonObject:
        return {
            **self.__dict__,
            "outputs": list(self.outputs),
            "synthetic": True,
        }
