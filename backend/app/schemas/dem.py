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
    cog_path: str | None = None
    cog_file_size_bytes: int | None = None
    uploaded_at: str | None = None
    task_count: int = 0
    active_task_count: int = 0


class DemDeleteResult(BaseModel):
    dem_id: str
    deleted: bool = False


class DemUploadSessionCreate(BaseModel):
    filename: str
    file_size_bytes: int
    chunk_size_bytes: int
    total_chunks: int


class DemUploadSession(BaseModel):
    upload_id: str
    filename: str
    file_size_bytes: int
    chunk_size_bytes: int
    total_chunks: int
    uploaded_chunks: list[int] = []


class DemChunkUploadResult(BaseModel):
    upload_id: str
    chunk_index: int
    uploaded_chunks: int
    total_chunks: int
