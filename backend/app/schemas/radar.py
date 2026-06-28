from typing import Literal

from pydantic import BaseModel, Field


class RadarInput(BaseModel):
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    height_m: float = Field(ge=0)


class TargetInput(BaseModel):
    height_m: float = Field(ge=0)


class CoverageInput(BaseModel):
    max_range_m: float = Field(gt=0, le=100_000)
    scan_mode: Literal["omni", "sector"] = "omni"
    azimuth_deg: float = Field(default=0, ge=0, lt=360)
    beam_width_deg: float = Field(default=360, gt=0, le=360)


class AdvancedInput(BaseModel):
    use_curvature: bool = True
    curvature_coeff: float = Field(default=0.75, ge=0, le=1)
    output_simplify_tolerance_m: float | None = Field(default=None, ge=0)


class ReservedRadarParams(BaseModel):
    frequency_hz: float | None = None
    transmit_power_w: float | None = None
    antenna_gain_db: float | None = None
    receiver_sensitivity_dbm: float | None = None
    target_rcs_m2: float | None = None
    pulse_width_s: float | None = None
    prf_hz: float | None = None
    noise_figure_db: float | None = None
    detection_probability: float | None = None
    false_alarm_probability: float | None = None


class CoverageRequest(BaseModel):
    dem_id: str
    radar: RadarInput
    target: TargetInput
    coverage: CoverageInput
    advanced: AdvancedInput = Field(default_factory=AdvancedInput)
    reserved_radar_params: ReservedRadarParams = Field(default_factory=ReservedRadarParams)


class CoverageMetrics(BaseModel):
    theoretical_area_m2: float = 0
    visible_area_m2: float = 0
    blocked_area_m2: float = 0
    blocked_ratio: float = 0


class CoverageOutputs(BaseModel):
    viewshed_tif: str | None = None
    visible_geojson: str | None = None
    blocked_geojson: str | None = None
    range_geojson: str | None = None
    model_metadata_json: str | None = None


class CoverageModelMetadata(BaseModel):
    target_epsg: int
    radar_projected_xy: list[float]
    projected_dem_bounds: list[float]
    projected_dem_resolution_m: list[float]
    max_range_m: float
    scan_mode: str
    azimuth_deg: float
    beam_width_deg: float
    simplify_tolerance_m: float
    gdal_viewshed_command: list[str] = Field(default_factory=list)


class CoverageTaskStatus(BaseModel):
    task_id: str
    status: Literal["pending", "running", "finished", "failed"]
    progress: int = Field(default=0, ge=0, le=100)
    message: str = ""
    metrics: CoverageMetrics | None = None
    outputs: CoverageOutputs | None = None
    model: CoverageModelMetadata | None = None
    warnings: list[str] = Field(default_factory=list)
