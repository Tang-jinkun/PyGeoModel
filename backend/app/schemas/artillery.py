from typing import Literal

from pydantic import BaseModel, Field, model_validator


ArtilleryOutputKind = Literal[
    "theoretical_geojson",
    "reachable_geojson",
    "terrain_masked_geojson",
    "sample_points_geojson",
    "model_metadata_json",
    "output_manifest_json",
]


class ArtilleryPositionInput(BaseModel):
    lon: float = Field(default=79.80513693057287, ge=-180, le=180)
    lat: float = Field(default=31.4827708959419, ge=-90, le=90)
    height_m: float = Field(default=0, ge=0, le=1000)
    altitude_mode: Literal["agl", "amsl"] = "agl"


class ArtilleryTargetInput(BaseModel):
    target_height_m: float = Field(default=0, ge=0, le=200)


class ArtilleryWeaponInput(BaseModel):
    min_range_m: float = Field(default=1000, ge=0, le=200000)
    max_range_m: float = Field(default=15000, gt=0, le=300000)
    azimuth_deg: float = Field(default=0, ge=0, lt=360)
    traverse_deg: float = Field(default=360, gt=0, le=360)
    muzzle_velocity_mps: float = Field(default=500, gt=1, le=3000)
    elevation_deg: float = Field(default=45, gt=0, lt=90)

    @model_validator(mode="after")
    def validate_ranges(self) -> "ArtilleryWeaponInput":
        if self.min_range_m >= self.max_range_m:
            raise ValueError("min_range_m must be less than max_range_m")
        return self


class ArtilleryMunitionInput(BaseModel):
    munition_type: Literal["he", "smoke", "illumination", "generic"] = "he"
    lethal_radius_m: float = Field(default=50, ge=0, le=5000)
    effective_radius_m: float = Field(default=120, ge=0, le=10000)


class ArtilleryAnalysisInput(BaseModel):
    use_dem_elevation: bool = True
    use_terrain_masking: bool = True
    sample_resolution_m: float | None = Field(default=None, gt=0, le=5000)
    trajectory_samples: int = Field(default=80, ge=8, le=400)
    clearance_margin_m: float = Field(default=0, ge=-100, le=1000)
    output_simplify_tolerance_m: float | None = Field(default=None, ge=0)


class ArtilleryCoverageRequest(BaseModel):
    dem_id: str
    battery: ArtilleryPositionInput = Field(default_factory=ArtilleryPositionInput)
    target: ArtilleryTargetInput = Field(default_factory=ArtilleryTargetInput)
    weapon: ArtilleryWeaponInput = Field(default_factory=ArtilleryWeaponInput)
    munition: ArtilleryMunitionInput = Field(default_factory=ArtilleryMunitionInput)
    analysis: ArtilleryAnalysisInput = Field(default_factory=ArtilleryAnalysisInput)


class ArtilleryCoverageMetrics(BaseModel):
    theoretical_area_m2: float = 0
    reachable_area_m2: float = 0
    terrain_masked_area_m2: float = 0
    terrain_masked_ratio: float = 0
    lethal_area_m2: float = 0
    effective_area_m2: float = 0
    min_range_m: float = 0
    max_range_m: float = 0
    effective_traverse_deg: float = 360
    lethal_radius_m: float = 0
    effective_radius_m: float = 0
    sample_point_count: int = 0
    reachable_sample_count: int = 0
    masked_sample_count: int = 0
    min_clearance_m: float | None = None
    mean_clearance_m: float | None = None
    battery_ground_elevation_m: float = 0
    battery_altitude_m: float = 0


class ArtilleryCoverageOutputs(BaseModel):
    theoretical_geojson: str | None = None
    reachable_geojson: str | None = None
    terrain_masked_geojson: str | None = None
    sample_points_geojson: str | None = None
    model_metadata_json: str | None = None
    output_manifest_json: str | None = None


class ArtilleryOutputFile(BaseModel):
    kind: ArtilleryOutputKind
    label: str
    url: str
    download_url: str
    filename: str
    media_type: str
    size_bytes: int | None = None
    exists: bool = False


class ArtilleryModelMetadata(BaseModel):
    target_epsg: int
    battery_projected_xy: list[float]
    projected_dem_bounds: list[float]
    projected_dem_resolution_m: list[float]
    battery_ground_elevation_m: float
    battery_altitude_m: float
    min_range_m: float
    max_range_m: float
    azimuth_deg: float
    traverse_deg: float
    muzzle_velocity_mps: float
    elevation_deg: float
    target_height_m: float
    sample_resolution_m: float
    trajectory_samples: int
    clearance_margin_m: float
    use_dem_elevation: bool
    use_terrain_masking: bool
    simplify_tolerance_m: float


class ArtilleryCoverageTaskSummary(BaseModel):
    task_id: str
    dem_id: str | None = None
    status: Literal["pending", "running", "finished", "failed"]
    progress: int = Field(default=0, ge=0, le=100)
    message: str = ""
    created_at: str | None = None
    updated_at: str | None = None
    metrics: ArtilleryCoverageMetrics | None = None
    outputs: ArtilleryCoverageOutputs | None = None
    output_files: list[ArtilleryOutputFile] = Field(default_factory=list)
    model: ArtilleryModelMetadata | None = None
    warnings: list[str] = Field(default_factory=list)


class ArtilleryCoverageTaskStatus(ArtilleryCoverageTaskSummary):
    request: ArtilleryCoverageRequest | None = None


class ArtilleryCoverageTaskDeleteResult(BaseModel):
    task_id: str
    deleted_task_record: bool = False
    deleted_output_dir: bool = False
