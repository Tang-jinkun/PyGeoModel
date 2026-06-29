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
    file_size_bytes: int | None = None
    uploaded_at: str | None = None
    task_count: int = 0
    active_task_count: int = 0


class DemDeleteResult(BaseModel):
    dem_id: str
    deleted: bool = False
