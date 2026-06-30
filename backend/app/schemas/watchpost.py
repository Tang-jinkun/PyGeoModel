from typing import Literal

from pydantic import BaseModel, Field


WatchpostOutputKind = Literal[
    "viewshed_tif",
    "visible_geojson",
    "blocked_geojson",
    "range_geojson",
    "model_metadata_json",
    "output_manifest_json",
]


class WatchpostObserverInput(BaseModel):
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    height_m: float = Field(default=2, ge=0, le=500)


class WatchpostTargetInput(BaseModel):
    height_m: float = Field(default=1.7, ge=0, le=100)


class WatchpostCoverageInput(BaseModel):
    max_range_m: float = Field(default=5000, gt=0, le=100000)
    scan_mode: Literal["omni", "sector"] = "omni"
    azimuth_deg: float = Field(default=0, ge=0, lt=360)
    view_angle_deg: float = Field(default=360, gt=0, le=360)


class WatchpostAnalysisInput(BaseModel):
    use_curvature: bool = True
    curvature_coeff: float = Field(default=0.75, ge=0, le=1)
    output_simplify_tolerance_m: float | None = Field(default=None, ge=0)


class WatchpostDetectionRequest(BaseModel):
    dem_id: str
    observer: WatchpostObserverInput
    target: WatchpostTargetInput = Field(default_factory=WatchpostTargetInput)
    coverage: WatchpostCoverageInput = Field(default_factory=WatchpostCoverageInput)
    analysis: WatchpostAnalysisInput = Field(default_factory=WatchpostAnalysisInput)


class WatchpostDetectionMetrics(BaseModel):
    theoretical_area_m2: float = 0
    visible_area_m2: float = 0
    blocked_area_m2: float = 0
    blocked_ratio: float = 0
    max_range_m: float = 0
    effective_view_angle_deg: float = 360
    observer_ground_elevation_m: float = 0
    observer_altitude_m: float = 0


class WatchpostDetectionOutputs(BaseModel):
    viewshed_tif: str | None = None
    visible_geojson: str | None = None
    blocked_geojson: str | None = None
    range_geojson: str | None = None
    model_metadata_json: str | None = None
    output_manifest_json: str | None = None


class WatchpostOutputFile(BaseModel):
    kind: WatchpostOutputKind
    label: str
    url: str
    download_url: str
    filename: str
    media_type: str
    size_bytes: int | None = None
    exists: bool = False


class WatchpostModelMetadata(BaseModel):
    target_epsg: int
    observer_projected_xy: list[float]
    projected_dem_bounds: list[float]
    projected_dem_resolution_m: list[float]
    max_range_m: float
    scan_mode: str
    azimuth_deg: float
    view_angle_deg: float
    observer_ground_elevation_m: float
    observer_altitude_m: float
    target_height_m: float
    use_curvature: bool
    curvature_coeff: float
    simplify_tolerance_m: float
    gdal_viewshed_command: list[str] = Field(default_factory=list)


class WatchpostDetectionTaskSummary(BaseModel):
    task_id: str
    dem_id: str | None = None
    status: Literal["pending", "running", "finished", "failed"]
    progress: int = Field(default=0, ge=0, le=100)
    message: str = ""
    created_at: str | None = None
    updated_at: str | None = None
    metrics: WatchpostDetectionMetrics | None = None
    outputs: WatchpostDetectionOutputs | None = None
    output_files: list[WatchpostOutputFile] = Field(default_factory=list)
    model: WatchpostModelMetadata | None = None
    warnings: list[str] = Field(default_factory=list)


class WatchpostDetectionTaskStatus(WatchpostDetectionTaskSummary):
    request: WatchpostDetectionRequest | None = None


class WatchpostDetectionTaskDeleteResult(BaseModel):
    task_id: str
    deleted_task_record: bool = False
    deleted_output_dir: bool = False
