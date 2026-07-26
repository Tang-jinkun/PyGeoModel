from dataclasses import dataclass

from pyproj import Transformer

from app.services.projection import utm_epsg_from_lonlat


@dataclass(frozen=True)
class MultiRadarProjection:
    target_epsg: int
    projected_points: list[tuple[float, float]]


def prepare_multi_radar_projection(
    coordinates: list[tuple[float, float]],
) -> MultiRadarProjection:
    if not coordinates:
        raise ValueError("Multi-radar projection requires at least one coordinate")
    longitude = sum(point[0] for point in coordinates) / len(coordinates)
    latitude = sum(point[1] for point in coordinates) / len(coordinates)
    target_epsg = utm_epsg_from_lonlat(longitude, latitude)
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{target_epsg}", always_xy=True)
    return MultiRadarProjection(
        target_epsg=target_epsg,
        projected_points=[tuple(transformer.transform(*point)) for point in coordinates],
    )
