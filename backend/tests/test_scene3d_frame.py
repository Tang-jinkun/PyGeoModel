import numpy

from app.scene3d.frame import SceneFrame


def test_frame_maps_enu_to_gltf_y_up() -> None:
    frame = SceneFrame.from_projected_points(
        32644,
        [
            (500_000.0, 3_500_000.0, 6123.0),
            (500_200.0, 3_500_400.0, 6380.0),
        ],
    )

    assert frame.origin_x == 500_100.0
    assert frame.origin_y == 3_500_200.0
    assert frame.origin_altitude_m == 6100.0
    assert numpy.allclose(
        frame.to_gltf((500_200.0, 3_500_400.0, 6380.0)),
        [100.0, 280.0, -200.0],
    )


def test_frame_metadata_round_trips_origin() -> None:
    frame = SceneFrame.from_projected_points(
        32644,
        [
            (500_000.0, 3_500_000.0, 6200.0),
            (501_000.0, 3_501_000.0, 6400.0),
        ],
    )
    metadata = frame.metadata("air_corridor_task_a", "air_corridor")

    assert metadata["schema_version"] == 1
    assert metadata["source_crs"] == "EPSG:32644"
    assert metadata["axes"] == {"x": "east", "y": "up", "z": "south"}
    assert metadata["origin"]["altitude_amsl_m"] == 6200.0
    assert -180 <= metadata["origin"]["longitude"] <= 180
    assert -90 <= metadata["origin"]["latitude"] <= 90
