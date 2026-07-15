import math
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


CoverageOutputKind = Literal[
    "viewshed_tif",
    "visible_geojson",
    "blocked_geojson",
    "range_geojson",
    "model_metadata_json",
    "output_manifest_json",
    "min_visible_height_tif",
    "voxel_manifest_json",
    "voxel_points_bin",
    "clipped_volume_manifest_json",
    "clipped_volume_cells_bin",
    "height_layers_manifest_json",
    "scene_glb",
]


class RadarInput(BaseModel):
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    height_m: float = Field(ge=0)


class TargetInput(BaseModel):
    height_m: float = Field(default=0, ge=0)


class CoverageInput(BaseModel):
    max_range_m: float = Field(gt=0, le=100_000)
    scan_mode: Literal["omni", "sector"] = "omni"
    azimuth_deg: float = Field(default=0, ge=0, lt=360)
    beam_width_deg: float = Field(default=360, gt=0, le=360)


class AdvancedInput(BaseModel):
    use_curvature: bool = True
    curvature_coeff: float = Field(default=0.75, ge=0, le=1)
    output_simplify_tolerance_m: float | None = Field(default=None, ge=0)
    voxel_grid_size: int = Field(default=128, ge=32, le=512)
    voxel_vertical_levels: int = Field(default=16, ge=4, le=64)
    voxel_max_height_m: float = Field(default=3000, ge=500, le=10000)
    min_elevation_deg: float = Field(default=0, ge=-10, le=89)
    max_elevation_deg: float = Field(default=32, ge=0, le=90)
    vertical_beam_width_deg: float = Field(default=32, ge=0, le=100)
    visual_dome_mode: bool = True
    height_layers_m: list[float] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_elevation_range(self) -> "AdvancedInput":
        if self.max_elevation_deg < self.min_elevation_deg:
            raise ValueError("max_elevation_deg must be greater than or equal to min_elevation_deg")
        self.vertical_beam_width_deg = self.max_elevation_deg - self.min_elevation_deg
        normalized_layers = sorted({
            float(height)
            for height in self.height_layers_m
            if math.isfinite(float(height)) and 0 <= float(height) <= self.voxel_max_height_m
        })
        if len(normalized_layers) > 20:
            raise ValueError("height_layers_m cannot contain more than 20 values")
        self.height_layers_m = normalized_layers
        return self


class ReservedRadarParams(BaseModel):
    frequency_hz: float | None = None
    transmit_power_w: float | None = None
    antenna_gain_db: float | None = None
    receiver_sensitivity_dbm: float | None = None
    target_rcs_m2: float | None = None
    system_loss_db: float | None = None
    pulse_width_s: float | None = None
    prf_hz: float | None = None
    noise_figure_db: float | None = None
    detection_probability: float | None = None
    false_alarm_probability: float | None = None


class CoverageRequest(BaseModel):
    dem_id: str
    radar: RadarInput
    target: TargetInput = Field(default_factory=TargetInput)
    coverage: CoverageInput
    advanced: AdvancedInput = Field(default_factory=AdvancedInput)
    reserved_radar_params: ReservedRadarParams = Field(default_factory=ReservedRadarParams)


class CoverageMetrics(BaseModel):
    requested_theoretical_area_m2: float = 0
    theoretical_area_m2: float = 0
    unknown_area_m2: float = 0
    visible_area_m2: float = 0
    blocked_area_m2: float = 0
    blocked_ratio: float = 0
    terrain_visible_area_m2: float = 0
    beam_eligible_area_m2: float = 0
    radar_equation_limited_area_m2: float = 0

    @model_validator(mode="before")
    @classmethod
    def preserve_legacy_theoretical_area(cls, value: Any) -> Any:
        if isinstance(value, dict) and "requested_theoretical_area_m2" not in value:
            return {
                **value,
                "requested_theoretical_area_m2": value.get("theoretical_area_m2", 0),
            }
        return value


class CoverageDiagnostics(BaseModel):
    radar_equation_active: bool = False
    radar_equation_max_range_m: float | None = None
    effective_max_range_m: float = 0
    terrain_blocked_area_m2: float = 0
    elevation_limited_area_m2: float = 0
    radar_equation_limited_area_m2: float = 0
    notes: list[str] = Field(default_factory=list)


class CoverageOutputs(BaseModel):
    viewshed_tif: str | None = None
    visible_geojson: str | None = None
    blocked_geojson: str | None = None
    range_geojson: str | None = None
    model_metadata_json: str | None = None
    output_manifest_json: str | None = None
    min_visible_height_tif: str | None = None
    voxel_manifest_json: str | None = None
    voxel_points_bin: str | None = None
    clipped_volume_manifest_json: str | None = None
    clipped_volume_cells_bin: str | None = None
    height_layers_manifest_json: str | None = None
    scene_glb: str | None = None


class CoverageOutputFile(BaseModel):
    kind: CoverageOutputKind
    label: str
    url: str
    download_url: str
    filename: str
    media_type: str
    size_bytes: int | None = None
    exists: bool = False


class BeamClipProfile(BaseModel):
    azimuth_step_deg: float = Field(default=2, gt=0, le=10)
    radius_m: list[float] = Field(default_factory=list)


class CoverageModelMetadata(BaseModel):
    coverage_contract_version: int = 1
    target_epsg: int
    radar_projected_xy: list[float]
    projected_dem_bounds: list[float]
    projected_dem_resolution_m: list[float]
    dem_coverage_ratio: float = 1
    max_range_m: float
    scan_mode: str
    azimuth_deg: float
    beam_width_deg: float
    simplify_tolerance_m: float
    gdal_viewshed_command: list[str] = Field(default_factory=list)
    voxel_grid_size: int = 128
    voxel_vertical_levels: int = 16
    voxel_max_height_m: float = 3000
    min_elevation_deg: float = 0
    max_elevation_deg: float = 32
    vertical_beam_width_deg: float = 32
    visual_dome_mode: bool = True
    height_layers_m: list[float] = Field(default_factory=list)
    radar_equation_active: bool = False
    radar_equation_max_range_m: float | None = None
    effective_max_range_m: float = 0
    beam_clip_profile: BeamClipProfile | None = None
    range_basis: Literal["radar_equation", "nominal"] = "nominal"
    reference_rcs_m2: float = 1
    scene3d: dict[str, Any] | None = None


class CoverageTaskSummary(BaseModel):
    task_id: str
    dem_id: str | None = None
    status: Literal["pending", "running", "finished", "failed"]
    progress: int = Field(default=0, ge=0, le=100)
    message: str = ""
    created_at: str | None = None
    updated_at: str | None = None
    metrics: CoverageMetrics | None = None
    outputs: CoverageOutputs | None = None
    output_files: list[CoverageOutputFile] = Field(default_factory=list)
    model: CoverageModelMetadata | None = None
    diagnostics: CoverageDiagnostics | None = None
    warnings: list[str] = Field(default_factory=list)


class CoverageTaskStatus(CoverageTaskSummary):
    request: CoverageRequest | None = None


class CoverageTaskDeleteResult(BaseModel):
    task_id: str
    deleted_task_record: bool = False
    deleted_output_dir: bool = False


class CoverageProfileSample(BaseModel):
    distance_m: float
    lon: float
    lat: float
    terrain_m: float
    line_of_sight_m: float
    clearance_m: float


class CoverageProfileResult(BaseModel):
    task_id: str
    target_lon: float
    target_lat: float
    distance_m: float
    azimuth_deg: float
    elevation_deg: float
    radar_ground_m: float
    target_ground_m: float
    radar_altitude_m: float
    target_altitude_m: float
    blocked: bool
    obstruction_distance_m: float | None = None
    obstruction_lon: float | None = None
    obstruction_lat: float | None = None
    obstruction_clearance_m: float | None = None
    min_required_target_height_m: float
    required_height_delta_m: float
    reason: str
    samples: list[CoverageProfileSample] = Field(default_factory=list)


class FusionRequest(BaseModel):
    task_ids: list[str] = Field(min_length=2, max_length=12)


class FusionMetrics(BaseModel):
    task_count: int
    union_visible_area_m2: float = 0
    overlap_visible_area_m2: float = 0
    union_theoretical_area_m2: float = 0
    blind_area_m2: float = 0
    overlap_ratio: float = 0
    blind_ratio: float = 0


class FusionResult(BaseModel):
    task_ids: list[str]
    metrics: FusionMetrics
    visible_union_geojson: dict[str, Any]
    overlap_geojson: dict[str, Any]
    blind_geojson: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)
