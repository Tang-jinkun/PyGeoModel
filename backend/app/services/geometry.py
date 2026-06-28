from math import cos, radians, sin

from shapely.geometry import Point, Polygon
from shapely.ops import transform


def make_range_geometry(x: float, y: float, radius_m: float, scan_mode: str, azimuth_deg: float, beam_width_deg: float):
    center = Point(x, y)
    if scan_mode == "omni" or beam_width_deg >= 360:
        return center.buffer(radius_m, resolution=128)

    start = azimuth_deg - beam_width_deg / 2
    end = azimuth_deg + beam_width_deg / 2
    steps = max(16, int(beam_width_deg / 2))
    points = [(x, y)]

    for index in range(steps + 1):
        azimuth = start + (end - start) * index / steps
        math_angle = radians(90 - azimuth)
        points.append((x + radius_m * cos(math_angle), y + radius_m * sin(math_angle)))

    points.append((x, y))
    return Polygon(points)


def project_geometry(geometry, transformer):
    return transform(transformer.transform, geometry)
