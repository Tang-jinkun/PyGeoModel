from typing import Literal

from pydantic import BaseModel, Field, model_validator


AirCorridorOutputKind = Literal[
    "corridor_path_geojson",
    "corridor_buffer_geojson",
    "threat_zones_geojson",
    "risk_samples_geojson",
    "cost_summary_json",
    "model_metadata_json",
    "output_manifest_json",
]


class AirCorridorPointInput(BaseModel):
    lon: float = Field(default=79.80513693057287, ge=-180, le=180)
    lat: float = Field(default=31.4827708959419, ge=-90, le=90)
    altitude_m: float = Field(default=1200, ge=0, le=20000)
    altitude_mode: Literal["agl", "amsl"] = "agl"


class AirCorridorAircraftInput(BaseModel):
    cruise_speed_kph: float = Field(default=180, gt=0, le=1200)
    min_agl_m: float = Field(default=100, ge=0, le=20000)
    max_agl_m: float = Field(default=3000, gt=0, le=30000)
    max_climb_rate_mps: float = Field(default=8, gt=0, le=100)
    max_descent_rate_mps: float = Field(default=10, gt=0, le=100)

    @model_validator(mode="after")
    def validate_altitudes(self) -> "AirCorridorAircraftInput":
        if self.min_agl_m >= self.max_agl_m:
            raise ValueError("min_agl_m must be less than max_agl_m")
        return self


class AirDefenseThreatInput(BaseModel):
    id: str
    name: str | None = None
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    min_range_m: float = Field(default=0, ge=0, le=500000)
    max_range_m: float = Field(gt=0, le=500000)
    min_altitude_m: float = Field(default=0, ge=0, le=50000)
    max_altitude_m: float = Field(default=10000, gt=0, le=50000)
    threat_level: float = Field(default=1, ge=0, le=10)
    kill_zone_radius_m: float | None = Field(default=None, ge=0, le=500000)
    warning_zone_radius_m: float | None = Field(default=None, ge=0, le=500000)

    @model_validator(mode="after")
    def validate_threat(self) -> "AirDefenseThreatInput":
        if self.min_range_m >= self.max_range_m:
            raise ValueError("min_range_m must be less than max_range_m")
        if self.min_altitude_m >= self.max_altitude_m:
            raise ValueError("min_altitude_m must be less than max_altitude_m")
        if self.kill_zone_radius_m is not None and self.warning_zone_radius_m is not None:
            if self.kill_zone_radius_m > self.warning_zone_radius_m:
                raise ValueError("kill_zone_radius_m must be less than or equal to warning_zone_radius_m")
        return self


class AirCorridorPlanningInput(BaseModel):
    corridor_width_m: float = Field(default=500, gt=0, le=10000)
    horizontal_resolution_m: float = Field(default=250, gt=0, le=5000)
    allow_altitude_change: bool = True
    threat_weight: float = Field(default=1, ge=0, le=100)
    distance_weight: float = Field(default=0.25, ge=0, le=100)
    altitude_change_weight: float = Field(default=0.15, ge=0, le=100)
    terrain_clearance_weight: float = Field(default=0.4, ge=0, le=100)
    output_simplify_tolerance_m: float | None = Field(default=None, ge=0)


class AirCorridorPlanningRequest(BaseModel):
    dem_id: str
    start: AirCorridorPointInput
    end: AirCorridorPointInput
    aircraft: AirCorridorAircraftInput = Field(default_factory=AirCorridorAircraftInput)
    altitude_layers_m: list[float] = Field(default_factory=lambda: [300, 600, 900, 1200, 1800, 2400], min_length=1, max_length=30)
    threats: list[AirDefenseThreatInput] = Field(default_factory=list, max_length=500)
    planning: AirCorridorPlanningInput = Field(default_factory=AirCorridorPlanningInput)

    @model_validator(mode="after")
    def validate_altitude_layers(self) -> "AirCorridorPlanningRequest":
        self.altitude_layers_m = sorted({float(value) for value in self.altitude_layers_m})
        return self


class AirCorridorPlanningMetrics(BaseModel):
    route_found: bool = False
    failure_reason: str | None = None
    risk_score: float | None = None
    max_segment_risk: float | None = None
    mean_segment_risk: float | None = None
    corridor_length_m: float = 0
    estimated_time_seconds: float | None = None
    min_terrain_clearance_m: float | None = None
    mean_terrain_clearance_m: float | None = None
    altitude_change_count: int = 0
    min_altitude_m: float | None = None
    max_altitude_m: float | None = None
    threat_intersection_count: int = 0
    nearest_threat_distance_m: float | None = None


class AirCorridorPlanningOutputs(BaseModel):
    corridor_path_geojson: str | None = None
    corridor_buffer_geojson: str | None = None
    threat_zones_geojson: str | None = None
    risk_samples_geojson: str | None = None
    cost_summary_json: str | None = None
    model_metadata_json: str | None = None
    output_manifest_json: str | None = None


class AirCorridorOutputFile(BaseModel):
    kind: AirCorridorOutputKind
    label: str
    url: str
    download_url: str
    filename: str
    media_type: str
    size_bytes: int | None = None
    exists: bool = False


class AirCorridorModelMetadata(BaseModel):
    target_epsg: int
    start_projected_xy: list[float]
    end_projected_xy: list[float]
    projected_dem_bounds: list[float]
    projected_dem_resolution_m: list[float]
    start_ground_elevation_m: float
    end_ground_elevation_m: float
    altitude_layers_m: list[float]
    threat_count: int
    horizontal_resolution_m: float
    corridor_width_m: float
    allow_altitude_change: bool
    simplify_tolerance_m: float


class AirCorridorPlanningTaskSummary(BaseModel):
    task_id: str
    dem_id: str | None = None
    status: Literal["pending", "running", "finished", "failed"]
    progress: int = Field(default=0, ge=0, le=100)
    message: str = ""
    created_at: str | None = None
    updated_at: str | None = None
    metrics: AirCorridorPlanningMetrics | None = None
    outputs: AirCorridorPlanningOutputs | None = None
    output_files: list[AirCorridorOutputFile] = Field(default_factory=list)
    model: AirCorridorModelMetadata | None = None
    warnings: list[str] = Field(default_factory=list)


class AirCorridorPlanningTaskStatus(AirCorridorPlanningTaskSummary):
    request: AirCorridorPlanningRequest | None = None


class AirCorridorPlanningTaskDeleteResult(BaseModel):
    task_id: str
    deleted_task_record: bool = False
    deleted_output_dir: bool = False
