from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status

from app.core.errors import AppError
from app.schemas.dem import DemChunkUploadResult, DemDeleteResult, DemMetadata, DemUploadSession, DemUploadSessionCreate
from app.services.dem_tiles import render_dem_tile, render_terrain_tile
from app.services.dem_store import (
    complete_upload_session,
    create_upload_session,
    delete_dem,
    list_dem_metadata,
    read_dem_metadata,
    save_dem_upload,
    save_upload_chunk,
)

router = APIRouter()


@router.post("/upload", response_model=DemMetadata, status_code=status.HTTP_201_CREATED)
async def upload_dem(file: UploadFile = File(...)) -> DemMetadata:
    if not file.filename:
        raise HTTPException(status_code=400, detail={"code": "INVALID_DEM", "message": "Missing file name."})

    try:
        return await save_dem_upload(file)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.post("/uploads", response_model=DemUploadSession, status_code=status.HTTP_201_CREATED)
def start_chunked_upload(payload: DemUploadSessionCreate) -> DemUploadSession:
    try:
        return create_upload_session(payload)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.put("/uploads/{upload_id}/chunks/{chunk_index}", response_model=DemChunkUploadResult)
async def upload_chunk(upload_id: str, chunk_index: int, file: UploadFile = File(...)) -> DemChunkUploadResult:
    try:
        return await save_upload_chunk(upload_id, chunk_index, file)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.post("/uploads/{upload_id}/complete", response_model=DemMetadata, status_code=status.HTTP_201_CREATED)
def complete_chunked_upload(upload_id: str) -> DemMetadata:
    try:
        return complete_upload_session(upload_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("", response_model=list[DemMetadata])
def list_dems() -> list[DemMetadata]:
    return list_dem_metadata()


@router.get("/{dem_id}", response_model=DemMetadata)
def get_dem(dem_id: str) -> DemMetadata:
    try:
        return read_dem_metadata(dem_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.get("/{dem_id}/tiles/{z}/{x}/{y}.png")
def get_dem_tile(dem_id: str, z: int, x: int, y: int) -> Response:
    try:
        tile = render_dem_tile(dem_id, z, x, y)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc
    return Response(
        content=tile,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/{dem_id}/terrain/{z}/{x}/{y}.png")
def get_dem_terrain_tile(dem_id: str, z: int, x: int, y: int) -> Response:
    try:
        tile = render_terrain_tile(dem_id, z, x, y)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc
    return Response(
        content=tile,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.delete("/{dem_id}", response_model=DemDeleteResult)
def remove_dem(dem_id: str) -> DemDeleteResult:
    try:
        return delete_dem(dem_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc
