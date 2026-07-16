from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.warp import transform as transform_points


Profile = Literal["ridge", "rough", "valley", "flat"]
Cell = tuple[int, int]


@dataclass
class TerrainGrid:
    elevation: numpy.ndarray
    valid: numpy.ndarray
    slope_deg: numpy.ndarray
    relief_m: numpy.ndarray
    transform: Affine
    crs: object

    @classmethod
    def load(cls, path: Path, max_dimension: int = 512) -> "TerrainGrid":
        with rasterio.open(path) as source:
            scale = max(source.width / max_dimension, source.height / max_dimension, 1)
            width = max(1, round(source.width / scale))
            height = max(1, round(source.height / scale))
            band = source.read(
                1,
                out_shape=(height, width),
                masked=True,
                resampling=Resampling.bilinear,
            )
            transform = source.transform * Affine.scale(
                source.width / width,
                source.height / height,
            )
            crs = source.crs

        elevation = band.filled(numpy.nan).astype("float64")
        valid = (~numpy.ma.getmaskarray(band)) & numpy.isfinite(elevation)
        if not numpy.any(valid):
            raise ValueError(f"DEM contains no finite valid cells: {path}")

        center_lat = transform.f + transform.e * height / 2
        x_m = abs(transform.a) * 111_320 * numpy.cos(numpy.deg2rad(center_lat))
        y_m = abs(transform.e) * 110_540
        safe = numpy.where(valid, elevation, numpy.nanmedian(elevation[valid]))
        dy, dx = numpy.gradient(safe, y_m, x_m)
        slope = numpy.degrees(numpy.arctan(numpy.hypot(dx, dy)))

        relief = numpy.zeros_like(safe)
        for row_shift, col_shift in (
            (-1, 0),
            (1, 0),
            (0, -1),
            (0, 1),
            (-1, -1),
            (1, 1),
        ):
            relief = numpy.maximum(
                relief,
                numpy.abs(safe - numpy.roll(safe, (row_shift, col_shift), (0, 1))),
            )

        return cls(elevation, valid, slope, relief, transform, crs)

    def select(
        self,
        profile: Profile,
        candidate_index: int,
        margin: int = 6,
        required_offsets: list[Cell] | tuple[Cell, ...] = (),
    ) -> Cell:
        rows, cols = numpy.indices(self.elevation.shape)
        interior = self.valid & (rows >= margin) & (cols >= margin)
        interior &= rows < self.elevation.shape[0] - margin
        interior &= cols < self.elevation.shape[1] - margin
        for row_offset, col_offset in required_offsets:
            target_rows = rows + row_offset
            target_cols = cols + col_offset
            in_bounds = (
                (target_rows >= 0)
                & (target_rows < self.valid.shape[0])
                & (target_cols >= 0)
                & (target_cols < self.valid.shape[1])
            )
            offset_valid = numpy.zeros_like(self.valid)
            offset_valid[in_bounds] = self.valid[
                target_rows[in_bounds],
                target_cols[in_bounds],
            ]
            interior &= offset_valid

        valid_elevation = self.elevation[self.valid]
        elevation_span = numpy.nanmax(valid_elevation) - numpy.nanmin(valid_elevation)
        normalized_elevation = (
            self.elevation - numpy.nanmin(valid_elevation)
        ) / max(elevation_span, 1)
        normalized_relief = self.relief_m / max(numpy.nanmax(self.relief_m[self.valid]), 1)
        rules = {
            "ridge": (interior & (self.slope_deg <= 25), normalized_elevation + normalized_relief),
            "rough": (
                interior & (self.slope_deg >= 4) & (self.slope_deg <= 35),
                normalized_relief + self.slope_deg / 90,
            ),
            "valley": (
                interior & (self.slope_deg <= 15),
                -normalized_elevation - self.slope_deg / 90,
            ),
            "flat": (
                interior & (self.slope_deg <= 10),
                -self.slope_deg / 90 + 0.25 * normalized_relief,
            ),
        }
        mask, score = rules[profile]
        cells = numpy.argwhere(mask)
        if len(cells) == 0:
            raise ValueError(f"No DEM candidates for profile '{profile}'")

        order = sorted(
            cells.tolist(),
            key=lambda cell: (-float(score[cell[0], cell[1]]), cell[0], cell[1]),
        )
        position = candidate_index * 32
        if position >= len(order):
            raise IndexError(
                f"Candidate {candidate_index} is unavailable for profile '{profile}'"
            )
        return tuple(order[position])

    def lonlat(self, row: int, col: int) -> tuple[float, float]:
        x, y = rasterio.transform.xy(self.transform, row, col, offset="center")
        if str(self.crs).upper() == "EPSG:4326":
            return float(x), float(y)
        lon, lat = transform_points(self.crs, "EPSG:4326", [x], [y])
        return float(lon[0]), float(lat[0])

    def route(self, anchor: Cell, offsets: list[Cell]) -> list[tuple[float, float]]:
        points: list[tuple[float, float]] = []
        for row_offset, col_offset in offsets:
            row, col = anchor[0] + row_offset, anchor[1] + col_offset
            if not (
                0 <= row < self.valid.shape[0]
                and 0 <= col < self.valid.shape[1]
                and self.valid[row, col]
            ):
                raise ValueError("Route point falls outside valid DEM data")
            points.append(self.lonlat(row, col))
        return points
