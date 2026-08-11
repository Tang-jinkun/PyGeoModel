import pytest

from app.core.errors import AppError
from app.services.artifact_contracts import OUTPUT_CONTRACTS, get_output_contract


def test_all_task_models_register_output_contracts() -> None:
    assert set(OUTPUT_CONTRACTS) == {
        "radar",
        "uav",
        "watchpost",
        "artillery",
        "recon_vehicle",
        "mobility",
        "air_corridor",
        "multi_radar",
    }
    for contract in OUTPUT_CONTRACTS.values():
        assert contract.version == 1
        assert len({item.kind for item in contract.artifacts}) == len(contract.artifacts)
        assert len({item.filename for item in contract.artifacts}) == len(contract.artifacts)
        assert contract.download_path_template.startswith("/api/")


def test_radar_contract_allows_only_registered_height_layer_pattern() -> None:
    contract = get_output_contract("radar")

    assert contract.dynamic_kind_pattern == r"height_(visible|blocked)_[0-9A-Za-z_]+"
    assert contract.spec("range_geojson").filename == "radar_range.geojson"


def test_multi_radar_contract_marks_internal_and_conditional_files() -> None:
    contract = get_output_contract("multi_radar")

    assert contract.spec("station_masks_npz").public is False
    assert contract.spec("grid_json").public is False
    assert contract.spec("fusion_scene_glb").required is False
    assert contract.spec("cooperative_intersection_glb").required is False


def test_artillery_trajectory_scene_is_optional() -> None:
    contract = get_output_contract("artillery")

    assert contract.spec("scene_glb").filename == "artillery_trajectory.glb"
    assert contract.spec("scene_glb").required is False


def test_unknown_model_contract_returns_not_found() -> None:
    with pytest.raises(AppError) as raised:
        get_output_contract("unknown")

    assert raised.value.status_code == 404
    assert raised.value.code == "OUTPUT_CONTRACT_NOT_FOUND"
