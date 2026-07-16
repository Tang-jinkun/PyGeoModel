from dataclasses import dataclass
from math import floor

import numpy
from pyproj import Transformer


ProjectedPoint = tuple[float, float, float]


@dataclass(frozen=True)
class SceneFrame:
    target_epsg: int
    origin_x: float
    origin_y: float
    origin_altitude_m: float
    origin_longitude: float
    origin_latitude: float

    @classmethod
    def from_projected_points(
        cls,
        target_epsg: int,
        points: list[ProjectedPoint],
    ) -> "SceneFrame":
        values = numpy.asarray(points, dtype=numpy.float64)
        if (
            values.ndim != 2
            or values.shape[1] != 3
            or len(values) == 0
            or not numpy.isfinite(values).all()
        ):
            raise ValueError("Scene frame requires finite projected XYZ points")
        origin_x = float((values[:, 0].min() + values[:, 0].max()) / 2)
        origin_y = float((values[:, 1].min() + values[:, 1].max()) / 2)
        origin_altitude_m = float(floor(values[:, 2].min() / 100.0) * 100.0)
        to_wgs84 = Transformer.from_crs(
            f"EPSG:{target_epsg}",
            "EPSG:4326",
            always_xy=True,
        )
        longitude, latitude = to_wgs84.transform(origin_x, origin_y)
        return cls(
            target_epsg,
            origin_x,
            origin_y,
            origin_altitude_m,
            float(longitude),
            float(latitude),
        )

    def to_gltf(self, point: ProjectedPoint) -> numpy.ndarray:
        east, north, altitude = point
        result = numpy.asarray(
            [
                east - self.origin_x,
                altitude - self.origin_altitude_m,
                -(north - self.origin_y),
            ],
            dtype=numpy.float64,
        )
        if not numpy.isfinite(result).all():
            raise ValueError("Scene point contains a non-finite coordinate")
        return result

    def metadata(self, task_id: str, model_id: str) -> dict:
        return {
            "schema_version": 1,
            "task_id": task_id,
            "model_id": model_id,
            "units": "metre",
            "source_crs": f"EPSG:{self.target_epsg}",
            "geographic_crs": "EPSG:4326",
            "origin": {
                "projected_x": self.origin_x,
                "projected_y": self.origin_y,
                "longitude": self.origin_longitude,
                "latitude": self.origin_latitude,
                "altitude_amsl_m": self.origin_altitude_m,
            },
            "axes": {"x": "east", "y": "up", "z": "south"},
        }
