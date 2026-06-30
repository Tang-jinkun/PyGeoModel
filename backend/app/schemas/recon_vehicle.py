from typing import Literal

from pydantic import BaseModel, Field, model_validator


ReconVehicleOutputKind = Literal[
    "footprint_geojson",
    "visible_geojson",
    "blocked_geojson",
    "model_metadata_json",
    "output_manifest_json",
]


class ReconVehiclePositionInput(BaseModel):
    lon: float = Field(default=79.80513693057287, ge=-180, le=180)
    lat: float = Field(default=31.4827708959419, ge=-90, le=90)
    heading_deg: float = Field(default=0, ge=0, lt=360)
    mast_height_m: float = Field(default=3, ge=0, le=50)


class ReconVehicleRouteInput(BaseModel):
    waypoints: list[ReconVehiclePositionInput] = Field(default_factory=list, max_length=100)
    sample_interval_m: float = Field(default=500, gt=0, le=5000)

    @model_validator(mode="after")
    def validate_waypoints(self) -> "ReconVehicleRouteInput":
        if self.waypoints and len(self.waypoints) < 2:
            raise ValueError("route.waypoints must contain at least two points when provided")
        return self


class ReconVehicleSensorInput(BaseModel):
    sensor_type: Literal["optical", "thermal", "radar", "generic"] = "optical"
    max_range_m: float = Field(default=5000, gt=0, le=100000)
    min_range_m: float = Field(default=0, ge=0, le=100000)
    scan_mode: Literal["omni", "sector"] = "sector"
    view_angle_deg: float = Field(default=120, gt=0, le=360)

    @model_validator(mode="after")
    def validate_range(self) -> "ReconVehicleSensorInput":
        if self.min_range_m >= self.max_range_m:
            raise ValueError("min_range_m must be less than max_range_m")
        return self


class ReconVehicleTargetInput(BaseModel):
    height_m: float = Field(default=1.7, ge=0, le=100)


class ReconVehicleAnalysisInput(BaseModel):
    use_terrain_occlusion: bool = True
    use_curvature: bool = True
    curvature_coeff: float = Field(default=0.75, ge=0, le=1)
    output_simplify_tolerance_m: float | None = Field(default=None, ge=0)


class ReconVehicleCoverageRequest(BaseModel):
    dem_id: str
    vehicle: ReconVehiclePositionInput = Field(default_factory=ReconVehiclePositionInput)
    route: ReconVehicleRouteInput | None = None
    sensor: ReconVehicleSensorInput = Field(default_factory=ReconVehicleSensorInput)
    target: ReconVehicleTargetInput = Field(default_factory=ReconVehicleTargetInput)
    analysis: ReconVehicleAnalysisInput = Field(default_factory=ReconVehicleAnalysisInput)


class ReconVehicleCoverageMetrics(BaseModel):
    theoretical_area_m2: float = 0
    visible_area_m2: float = 0
    blocked_area_m2: float = 0
    blocked_ratio: float = 0
    max_range_m: float = 0
    effective_view_angle_deg: float = 360
    coverage_point_count: int = 1
    route_length_m: float = 0
    average_visible_area_m2: float = 0
    overlap_area_m2: float = 0
    vehicle_ground_elevation_m: float = 0
    sensor_altitude_m: float = 0


class ReconVehicleCoverageOutputs(BaseModel):
    footprint_geojson: str | None = None
    visible_geojson: str | None = None
    blocked_geojson: str | None = None
    model_metadata_json: str | None = None
    output_manifest_json: str | None = None


class ReconVehicleOutputFile(BaseModel):
    kind: ReconVehicleOutputKind
    label: str
    url: str
    download_url: str
    filename: str
    media_type: str
    size_bytes: int | None = None
    exists: bool = False


class ReconVehicleModelMetadata(BaseModel):
    target_epsg: int
    vehicle_projected_xy: list[float]
    projected_dem_bounds: list[float]
    projected_dem_resolution_m: list[float]
    vehicle_ground_elevation_m: float
    sensor_altitude_m: float
    mast_height_m: float
    sensor_type: str
    min_range_m: float
    max_range_m: float
    scan_mode: str
    heading_deg: float
    view_angle_deg: float
    target_height_m: float
    use_terrain_occlusion: bool
    use_curvature: bool
    curvature_coeff: float
    simplify_tolerance_m: float
    coverage_mode: Literal["single", "route"] = "single"
    coverage_point_count: int = 1
    route_length_m: float = 0
    gdal_viewshed_commands: list[list[str]] = Field(default_factory=list)


class ReconVehicleCoverageTaskSummary(BaseModel):
    task_id: str
    dem_id: str | None = None
    status: Literal["pending", "running", "finished", "failed"]
    progress: int = Field(default=0, ge=0, le=100)
    message: str = ""
    created_at: str | None = None
    updated_at: str | None = None
    metrics: ReconVehicleCoverageMetrics | None = None
    outputs: ReconVehicleCoverageOutputs | None = None
    output_files: list[ReconVehicleOutputFile] = Field(default_factory=list)
    model: ReconVehicleModelMetadata | None = None
    warnings: list[str] = Field(default_factory=list)


class ReconVehicleCoverageTaskStatus(ReconVehicleCoverageTaskSummary):
    request: ReconVehicleCoverageRequest | None = None


class ReconVehicleCoverageTaskDeleteResult(BaseModel):
    task_id: str
    deleted_task_record: bool = False
    deleted_output_dir: bool = False
