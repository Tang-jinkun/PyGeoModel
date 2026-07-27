from dataclasses import dataclass
from typing import Iterable

import numpy


@dataclass(frozen=True)
class StationMask:
    radar_id: str
    visible_mask: numpy.ndarray
    range_mask: numpy.ndarray


@dataclass(frozen=True)
class MultiRadarAggregate:
    coverage_count: numpy.ndarray
    visible_union: numpy.ndarray
    overlap: numpy.ndarray
    blind: numpy.ndarray


def accumulate_station_masks(results: Iterable[StationMask]) -> MultiRadarAggregate:
    items = list(results)
    if not items:
        raise ValueError("Multi-radar aggregation requires at least one station mask")
    shape = items[0].visible_mask.shape
    coverage_count = numpy.zeros(shape, dtype=numpy.uint16)
    theoretical_union = numpy.zeros(shape, dtype=bool)
    for item in items:
        if item.visible_mask.shape != shape or item.range_mask.shape != shape:
            raise ValueError("Station masks must share one grid shape")
        coverage_count += numpy.asarray(item.visible_mask, dtype=numpy.uint16)
        theoretical_union |= numpy.asarray(item.range_mask, dtype=bool)
    visible_union = coverage_count >= 1
    return MultiRadarAggregate(
        coverage_count=coverage_count,
        visible_union=visible_union,
        overlap=coverage_count >= 2,
        blind=theoretical_union & ~visible_union,
    )
