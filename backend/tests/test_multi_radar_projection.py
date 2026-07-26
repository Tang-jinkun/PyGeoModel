from app.services.multi_radar_projection import prepare_multi_radar_projection


def test_batch_projection_uses_one_centroid_utm_frame() -> None:
    projection = prepare_multi_radar_projection(
        [(79.0, 31.5), (79.4, 31.7), (79.2, 31.6)]
    )

    assert projection.target_epsg == 32644
    assert len(projection.projected_points) == 3
    assert len({point[0] for point in projection.projected_points}) == 3
