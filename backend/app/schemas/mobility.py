from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


MobilityOutputKind = Literal[
    "wheeled_path_geojson",
    "tracked_path_geojson",
    "road_mask_geojson",
    "cost_summary_json",
    "model_metadata_json",
    "output_manifest_json",
]


class MobilityPointInput(BaseModel):
    lon: float = Field(default=79.80513693057287, ge=-180, le=180)
    lat: float = Field(default=31.4827708959419, ge=-90, le=90)


class MobilityVehicleInput(BaseModel):
    enabled: bool = True
    base_speed_kph: float = Field(default=35, gt=0, le=150)
    max_slope_deg: float = Field(default=25, ge=0, le=60)
    slope_penalty: float = Field(default=1.5, ge=0, le=10)
    road_speed_multiplier: float = Field(default=1.25, gt=0, le=5)
    offroad_speed_multiplier: float = Field(default=0.8, gt=0, le=5)


class MobilityVehiclesInput(BaseModel):
    wheeled: MobilityVehicleInput = Field(
        default_factory=lambda: MobilityVehicleInput(
            base_speed_kph=45,
            max_slope_deg=18,
            slope_penalty=2.2,
            road_speed_multiplier=1.5,
            offroad_speed_multiplier=0.65,
        )
    )
    tracked: MobilityVehicleInput = Field(
        default_factory=lambda: MobilityVehicleInput(
            base_speed_kph=35,
            max_slope_deg=30,
            slope_penalty=1.4,
            road_speed_multiplier=1.25,
            offroad_speed_multiplier=0.85,
        )
    )

    @model_validator(mode="after")
    def validate_enabled_vehicle(self) -> "MobilityVehiclesInput":
        if not self.wheeled.enabled and not self.tracked.enabled:
            raise ValueError("At least one vehicle type must be enabled")
        return self


class MobilityRoadNetworkInput(BaseModel):
    geojson: dict[str, Any] | None = None
    road_buffer_m: float = Field(default=20, ge=0, le=500)
    road_classes: dict[str, float] = Field(default_factory=lambda: {"primary": 1.4, "secondary": 1.25, "track": 1.1})


class MobilityAnalysisInput(BaseModel):
    allow_diagonal: bool = True
    max_search_radius_m: float | None = Field(default=None, gt=0, le=500000)
    output_simplify_tolerance_m: float | None = Field(default=None, ge=0)


class MobilityAccessibilityRequest(BaseModel):
    dem_id: str
    start: MobilityPointInput
    end: MobilityPointInput
    vehicles: MobilityVehiclesInput = Field(default_factory=MobilityVehiclesInput)
    road_network: MobilityRoadNetworkInput | None = None
    analysis: MobilityAnalysisInput = Field(default_factory=MobilityAnalysisInput)


class MobilityVehicleMetrics(BaseModel):
    reachable: bool = False
    travel_time_seconds: float | None = None
    travel_distance_m: float = 0
    average_speed_kph: float = 0
    road_distance_m: float = 0
    offroad_distance_m: float = 0
    max_slope_deg: float | None = None
    mean_slope_deg: float | None = None
    failure_reason: str | None = None


class MobilityAccessibilityMetrics(BaseModel):
    winner: Literal["wheeled", "tracked", "tie", "none"] = "none"
    time_saving_seconds: float | None = None
    time_saving_ratio: float | None = None
    wheeled: MobilityVehicleMetrics = Field(default_factory=MobilityVehicleMetrics)
    tracked: MobilityVehicleMetrics = Field(default_factory=MobilityVehicleMetrics)


class MobilityAccessibilityOutputs(BaseModel):
    wheeled_path_geojson: str | None = None
    tracked_path_geojson: str | None = None
    road_mask_geojson: str | None = None
    cost_summary_json: str | None = None
    model_metadata_json: str | None = None
    output_manifest_json: str | None = None


class MobilityOutputFile(BaseModel):
    kind: MobilityOutputKind
    label: str
    url: str
    download_url: str
    filename: str
    media_type: str
    size_bytes: int | None = None
    exists: bool = False


class MobilityModelMetadata(BaseModel):
    target_epsg: int
    start_projected_xy: list[float]
    end_projected_xy: list[float]
    projected_dem_bounds: list[float]
    projected_dem_resolution_m: list[float]
    start_ground_elevation_m: float
    end_ground_elevation_m: float
    allow_diagonal: bool
    max_search_radius_m: float | None = None
    simplify_tolerance_m: float
    road_network_used: bool = False
    road_buffer_m: float = 0


class MobilityAccessibilityTaskSummary(BaseModel):
    task_id: str
    dem_id: str | None = None
    status: Literal["pending", "running", "finished", "failed"]
    progress: int = Field(default=0, ge=0, le=100)
    message: str = ""
    created_at: str | None = None
    updated_at: str | None = None
    metrics: MobilityAccessibilityMetrics | None = None
    outputs: MobilityAccessibilityOutputs | None = None
    output_files: list[MobilityOutputFile] = Field(default_factory=list)
    model: MobilityModelMetadata | None = None
    warnings: list[str] = Field(default_factory=list)


class MobilityAccessibilityTaskStatus(MobilityAccessibilityTaskSummary):
    request: MobilityAccessibilityRequest | None = None


class MobilityAccessibilityTaskDeleteResult(BaseModel):
    task_id: str
    deleted_task_record: bool = False
    deleted_output_dir: bool = False
