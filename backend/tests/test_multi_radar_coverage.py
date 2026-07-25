import numpy

from app.services.multi_radar_coverage import StationMask, accumulate_station_masks


def test_accumulate_station_masks_counts_union_overlap_and_blind() -> None:
    aggregate = accumulate_station_masks(
        [
            StationMask(
                "north",
                numpy.array([[True, False], [True, False]]),
                numpy.ones((2, 2), dtype=bool),
            ),
            StationMask(
                "south",
                numpy.array([[True, True], [False, False]]),
                numpy.ones((2, 2), dtype=bool),
            ),
        ]
    )

    assert aggregate.coverage_count.tolist() == [[2, 1], [1, 0]]
    assert aggregate.visible_union.tolist() == [[True, True], [True, False]]
    assert aggregate.overlap.tolist() == [[True, False], [False, False]]
    assert aggregate.blind.tolist() == [[False, False], [False, True]]
