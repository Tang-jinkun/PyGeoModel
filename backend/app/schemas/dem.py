from pydantic import BaseModel


class DemMetadata(BaseModel):
    dem_id: str
    filename: str
    crs: str
    bounds: list[float]
    resolution: list[float]
    width: int
    height: int
    nodata: float | None = None
