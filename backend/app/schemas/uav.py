from typing import Literal

from pydantic import BaseModel, Field, model_validator


UavOutputKind = Literal[
    "footprint_geojson",
    "visible_geojson",
    "blocked_geojson",
    "model_metadata_json",
    "output_manifest_json",
]


class UavPlatformInput(BaseModel):
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    altitude_m: float = Field(default=500, ge=1, le=10000)
    altitude_mode: Literal["agl", "amsl"] = "agl"
    heading_deg: float = Field(default=0, ge=0, lt=360)
    pitch_deg: float = Field(default=-45, ge=-89, le=10)
    roll_deg: float = Field(default=0, ge=-45, le=45)


class UavRouteInput(BaseModel):
    waypoints: list[UavPlatformInput] = Field(default_factory=list, max_length=200)
    sample_interval_m: float = Field(default=500, gt=0, le=5000)

    @model_validator(mode="after")
    def validate_waypoints(self) -> "UavRouteInput":
        if self.waypoints and len(self.waypoints) < 2:
            raise ValueError("route.waypoints must contain at least two points when provided")
        return self


class UavSensorInput(BaseModel):
    sensor_type: Literal["camera", "thermal", "eo"] = "camera"
    h_fov_deg: float = Field(default=60, gt=0, le=160)
    v_fov_deg: float = Field(default=40, gt=0, le=120)
    max_range_m: float = Field(default=5000, gt=1, le=50000)
    min_range_m: float = Field(default=0, ge=0, le=50000)
    ground_resolution_m: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> "UavSensorInput":
        if self.min_range_m >= self.max_range_m:
            raise ValueError("min_range_m must be less than max_range_m")
        return self


class UavAnalysisInput(BaseModel):
    target_height_m: float = Field(default=0, ge=0, le=100)
    use_terrain_occlusion: bool = True
    sample_resolution_m: float | None = Field(default=None, gt=0, le=1000)
    output_simplify_tolerance_m: float | None = Field(default=None, ge=0)


class UavReconRequest(BaseModel):
    dem_id: str
    uav: UavPlatformInput
    route: UavRouteInput | None = None
    sensor: UavSensorInput = Field(default_factory=UavSensorInput)
    analysis: UavAnalysisInput = Field(default_factory=UavAnalysisInput)


class UavReconMetrics(BaseModel):
    theoretical_area_m2: float = 0
    visible_area_m2: float = 0
    blocked_area_m2: float = 0
    blocked_ratio: float = 0
    max_ground_distance_m: float = 0
    coverage_point_count: int = 1
    route_length_m: float = 0
    average_visible_area_m2: float = 0
    overlap_area_m2: float = 0


class UavReconOutputs(BaseModel):
    footprint_geojson: str | None = None
    visible_geojson: str | None = None
    blocked_geojson: str | None = None
    model_metadata_json: str | None = None
    output_manifest_json: str | None = None


class UavOutputFile(BaseModel):
    kind: UavOutputKind
    label: str
    url: str
    download_url: str
    filename: str
    media_type: str
    size_bytes: int | None = None
    exists: bool = False


class UavModelMetadata(BaseModel):
    target_epsg: int
    uav_projected_xy: list[float]
    uav_altitude_amsl_m: float
    ground_elevation_m: float
    projected_dem_bounds: list[float]
    projected_dem_resolution_m: list[float]
    heading_deg: float
    pitch_deg: float
    roll_deg: float
    h_fov_deg: float
    v_fov_deg: float
    min_range_m: float
    max_range_m: float
    target_height_m: float
    sample_resolution_m: float
    centerline_ground_point: list[float] | None = None
    coverage_mode: Literal["single", "route"] = "single"
    coverage_point_count: int = 1
    route_length_m: float = 0


class UavReconTaskSummary(BaseModel):
    task_id: str
    dem_id: str | None = None
    status: Literal["pending", "running", "finished", "failed"]
    progress: int = Field(default=0, ge=0, le=100)
    message: str = ""
    created_at: str | None = None
    updated_at: str | None = None
    metrics: UavReconMetrics | None = None
    outputs: UavReconOutputs | None = None
    output_files: list[UavOutputFile] = Field(default_factory=list)
    model: UavModelMetadata | None = None
    warnings: list[str] = Field(default_factory=list)


class UavReconTaskStatus(UavReconTaskSummary):
    request: UavReconRequest | None = None


class UavReconTaskDeleteResult(BaseModel):
    task_id: str
    deleted_task_record: bool = False
    deleted_output_dir: bool = False
