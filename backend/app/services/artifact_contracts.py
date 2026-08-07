import re
from dataclasses import dataclass
from pathlib import Path

from app.core.errors import AppError


KIND_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")


@dataclass(frozen=True)
class ArtifactSpec:
    kind: str
    filename: str
    media_type: str
    label: str
    required: bool = True
    public: bool = True


@dataclass(frozen=True)
class OutputContract:
    model_id: str
    version: int
    download_path_template: str
    artifacts: tuple[ArtifactSpec, ...]
    dynamic_kind_pattern: str | None = None

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("Output contract version must be at least 1.")
        if self.download_path_template.count("{task_id}") != 1 or self.download_path_template.count("{kind}") != 1:
            raise ValueError("Download path template must contain task_id and kind exactly once.")
        kinds: set[str] = set()
        filenames: set[str] = set()
        for item in self.artifacts:
            self.validate_spec(item)
            if item.kind in kinds:
                raise ValueError(f"Duplicate artifact kind '{item.kind}'.")
            if item.filename in filenames:
                raise ValueError(f"Duplicate artifact filename '{item.filename}'.")
            kinds.add(item.kind)
            filenames.add(item.filename)
        if self.dynamic_kind_pattern is not None:
            re.compile(self.dynamic_kind_pattern)

    @staticmethod
    def validate_spec(spec: ArtifactSpec) -> None:
        if not KIND_PATTERN.fullmatch(spec.kind):
            raise ValueError(f"Invalid artifact kind '{spec.kind}'.")
        path = Path(spec.filename)
        if path.name != spec.filename or path.is_absolute() or spec.filename in {"", ".", ".."}:
            raise ValueError(f"Artifact filename '{spec.filename}' must be a basename.")
        if not spec.media_type or not spec.label:
            raise ValueError("Artifact media type and label are required.")

    def spec(self, kind: str) -> ArtifactSpec:
        for item in self.artifacts:
            if item.kind == kind:
                return item
        raise AppError("OUTPUT_KIND_NOT_FOUND", f"Output kind '{kind}' is not supported.", status_code=404)

    def accepts_dynamic(self, spec: ArtifactSpec) -> bool:
        self.validate_spec(spec)
        return bool(self.dynamic_kind_pattern and re.fullmatch(self.dynamic_kind_pattern, spec.kind))


def _artifact(
    kind: str,
    filename: str,
    media_type: str,
    label: str,
    *,
    required: bool = True,
    public: bool = True,
) -> ArtifactSpec:
    return ArtifactSpec(kind, filename, media_type, label, required, public)


OUTPUT_CONTRACTS: dict[str, OutputContract] = {
    "radar": OutputContract(
        model_id="radar",
        version=1,
        download_path_template="/api/radar/coverage/{task_id}/outputs/{kind}",
        artifacts=(
            _artifact("viewshed_tif", "viewshed.tif", "image/tiff", "Viewshed GeoTIFF"),
            _artifact("visible_geojson", "visible.geojson", "application/geo+json", "Visible Area GeoJSON"),
            _artifact("blocked_geojson", "blocked.geojson", "application/geo+json", "Blocked Area GeoJSON"),
            _artifact("range_geojson", "radar_range.geojson", "application/geo+json", "Theoretical Range GeoJSON"),
            _artifact("model_metadata_json", "model_metadata.json", "application/json", "Model Metadata JSON"),
            _artifact("output_manifest_json", "output_manifest.json", "application/json", "Output Manifest JSON"),
            _artifact("min_visible_height_tif", "min_visible_height.tif", "image/tiff", "Min Visible Height GeoTIFF"),
            _artifact("voxel_manifest_json", "voxel_manifest.json", "application/json", "Voxel Manifest JSON"),
            _artifact("voxel_points_bin", "voxel_points.bin", "application/octet-stream", "Voxel Points Binary"),
            _artifact("clipped_volume_manifest_json", "clipped_volume_manifest.json", "application/json", "Clipped Volume Manifest JSON"),
            _artifact("clipped_volume_cells_bin", "clipped_volume_cells.bin", "application/octet-stream", "Clipped Volume Cells Binary"),
            _artifact("height_layers_manifest_json", "height_layers_manifest.json", "application/json", "Height Layers Manifest JSON"),
            _artifact("scene_glb", "radar_detection_domain.glb", "model/gltf-binary", "Radar Maximum Detection Domain GLB"),
            _artifact("radar_platform_glb", "radar_platform.glb", "model/gltf-binary", "Radar Platform GLB"),
        ),
        dynamic_kind_pattern=r"height_(visible|blocked)_[0-9A-Za-z_]+",
    ),
    "uav": OutputContract(
        model_id="uav",
        version=1,
        download_path_template="/api/uav/recon/{task_id}/outputs/{kind}",
        artifacts=(
            _artifact("footprint_geojson", "footprint.geojson", "application/geo+json", "UAV Sensor Footprint GeoJSON"),
            _artifact("visible_geojson", "visible.geojson", "application/geo+json", "UAV Visible Recon Area GeoJSON"),
            _artifact("blocked_geojson", "blocked.geojson", "application/geo+json", "UAV Terrain Blocked Area GeoJSON"),
            _artifact("model_metadata_json", "model_metadata.json", "application/json", "UAV Model Metadata JSON"),
            _artifact("output_manifest_json", "output_manifest.json", "application/json", "UAV Output Manifest JSON"),
        ),
    ),
    "watchpost": OutputContract(
        model_id="watchpost",
        version=1,
        download_path_template="/api/watchpost/detection/{task_id}/outputs/{kind}",
        artifacts=(
            _artifact("viewshed_tif", "viewshed.tif", "image/tiff", "Watchpost Viewshed GeoTIFF"),
            _artifact("visible_geojson", "visible.geojson", "application/geo+json", "Watchpost Visible Area GeoJSON"),
            _artifact("blocked_geojson", "blocked.geojson", "application/geo+json", "Watchpost Blocked Area GeoJSON"),
            _artifact("range_geojson", "range.geojson", "application/geo+json", "Watchpost Theoretical Range GeoJSON"),
            _artifact("model_metadata_json", "model_metadata.json", "application/json", "Watchpost Model Metadata JSON"),
            _artifact("output_manifest_json", "output_manifest.json", "application/json", "Watchpost Output Manifest JSON"),
        ),
    ),
    "artillery": OutputContract(
        model_id="artillery",
        version=1,
        download_path_template="/api/artillery/coverage/{task_id}/outputs/{kind}",
        artifacts=(
            _artifact("theoretical_geojson", "theoretical.geojson", "application/geo+json", "Artillery Theoretical Coverage GeoJSON"),
            _artifact("reachable_geojson", "reachable.geojson", "application/geo+json", "Artillery Terrain-Cleared Coverage GeoJSON"),
            _artifact("terrain_masked_geojson", "terrain_masked.geojson", "application/geo+json", "Artillery Terrain-Masked Area GeoJSON"),
            _artifact("sample_points_geojson", "sample_points.geojson", "application/geo+json", "Artillery Trajectory Sample Points GeoJSON"),
            _artifact("scene_glb", "artillery_trajectory.glb", "model/gltf-binary", "Artillery Trajectory 3D GLB", required=False),
            _artifact("model_metadata_json", "model_metadata.json", "application/json", "Artillery Model Metadata JSON"),
            _artifact("output_manifest_json", "output_manifest.json", "application/json", "Artillery Output Manifest JSON"),
        ),
    ),
    "recon_vehicle": OutputContract(
        model_id="recon_vehicle",
        version=1,
        download_path_template="/api/recon-vehicle/coverage/{task_id}/outputs/{kind}",
        artifacts=(
            _artifact("footprint_geojson", "footprint.geojson", "application/geo+json", "Recon Vehicle Sensor Footprint GeoJSON"),
            _artifact("visible_geojson", "visible.geojson", "application/geo+json", "Recon Vehicle Visible Area GeoJSON"),
            _artifact("blocked_geojson", "blocked.geojson", "application/geo+json", "Recon Vehicle Terrain Blocked Area GeoJSON"),
            _artifact("model_metadata_json", "model_metadata.json", "application/json", "Recon Vehicle Model Metadata JSON"),
            _artifact("output_manifest_json", "output_manifest.json", "application/json", "Recon Vehicle Output Manifest JSON"),
        ),
    ),
    "mobility": OutputContract(
        model_id="mobility",
        version=1,
        download_path_template="/api/mobility/accessibility/{task_id}/outputs/{kind}",
        artifacts=(
            _artifact("wheeled_path_geojson", "wheeled_path.geojson", "application/geo+json", "Wheeled Vehicle Path GeoJSON"),
            _artifact("tracked_path_geojson", "tracked_path.geojson", "application/geo+json", "Tracked Vehicle Path GeoJSON"),
            _artifact("road_mask_geojson", "road_mask.geojson", "application/geo+json", "Road Mask GeoJSON"),
            _artifact("cost_summary_json", "cost_summary.json", "application/json", "Mobility Cost Summary JSON"),
            _artifact("model_metadata_json", "model_metadata.json", "application/json", "Mobility Model Metadata JSON"),
            _artifact("output_manifest_json", "output_manifest.json", "application/json", "Mobility Output Manifest JSON"),
        ),
    ),
    "air_corridor": OutputContract(
        model_id="air_corridor",
        version=1,
        download_path_template="/api/air-corridor/planning/{task_id}/outputs/{kind}",
        artifacts=(
            _artifact("corridor_path_geojson", "corridor_path.geojson", "application/geo+json", "Air Corridor Path GeoJSON"),
            _artifact("corridor_buffer_geojson", "corridor_buffer.geojson", "application/geo+json", "Air Corridor Buffer GeoJSON"),
            _artifact("threat_zones_geojson", "threat_zones.geojson", "application/geo+json", "Air Defense Threat Zones GeoJSON"),
            _artifact("risk_samples_geojson", "risk_samples.geojson", "application/geo+json", "Air Corridor Risk Samples GeoJSON"),
            _artifact("cost_summary_json", "cost_summary.json", "application/json", "Air Corridor Cost Summary JSON"),
            _artifact("scene_glb", "air_corridor_result.glb", "model/gltf-binary", "Air Corridor 3D Result GLB"),
            _artifact("model_metadata_json", "model_metadata.json", "application/json", "Air Corridor Model Metadata JSON"),
            _artifact("output_manifest_json", "output_manifest.json", "application/json", "Air Corridor Output Manifest JSON"),
        ),
    ),
    "multi_radar": OutputContract(
        model_id="multi_radar",
        version=1,
        download_path_template="/api/radar/multi-coverage/{task_id}/outputs/{kind}",
        artifacts=(
            _artifact("visible_union_geojson", "visible_union.geojson", "application/geo+json", "Visible Union GeoJSON"),
            _artifact("overlap_geojson", "overlap.geojson", "application/geo+json", "Overlap GeoJSON"),
            _artifact("blind_geojson", "blind.geojson", "application/geo+json", "Blind Area GeoJSON"),
            _artifact("coverage_count_geojson", "coverage_count.geojson", "application/geo+json", "Coverage Count GeoJSON"),
            _artifact("stations_geojson", "stations.geojson", "application/geo+json", "Radar Stations GeoJSON"),
            _artifact("station_summaries_json", "station_summaries.json", "application/json", "Radar Station Summaries JSON"),
            _artifact("station_masks_npz", "station_masks.npz", "application/octet-stream", "Radar Station Masks", public=False),
            _artifact("grid_json", "grid.json", "application/json", "Radar Grid Metadata", public=False),
            _artifact("fusion_scene_glb", "fusion_scene.glb", "model/gltf-binary", "Multi-Radar Fusion Scene GLB", required=False),
            _artifact("cooperative_intersection_glb", "cooperative_intersection.glb", "model/gltf-binary", "Cooperative Intersection GLB", required=False),
        ),
    ),
}


def get_output_contract(model_id: str) -> OutputContract:
    try:
        return OUTPUT_CONTRACTS[model_id]
    except KeyError as exc:
        raise AppError(
            "OUTPUT_CONTRACT_NOT_FOUND",
            f"Output contract '{model_id}' was not found.",
            status_code=404,
        ) from exc
