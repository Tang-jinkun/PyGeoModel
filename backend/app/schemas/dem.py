from typing import Literal

from pydantic import BaseModel, Field


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
    source_type: str | None = None
    source_tile_count: int | None = None
    source_filenames: list[str] = Field(default_factory=list)


class DemDeleteResult(BaseModel):
    dem_id: str
    deleted: bool = False


class DemUploadSessionCreate(BaseModel):
    filename: str
    file_size_bytes: int
    chunk_size_bytes: int
    total_chunks: int


class DemBatchCreate(BaseModel):
    dem_id: str | None = None
    label: str | None = None


class DemBatchStatus(BaseModel):
    batch_id: str
    dem_id: str
    label: str | None = None
    status: Literal["uploading", "validating", "merging", "ready", "failed"]
    filenames: list[str] = Field(default_factory=list)
    file_count: int = 0
    error: str | None = None


class DemBatchUploadResult(BaseModel):
    batch_id: str
    filenames: list[str]
    file_count: int


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
