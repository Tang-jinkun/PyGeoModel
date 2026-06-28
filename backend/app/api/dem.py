from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.core.errors import AppError
from app.schemas.dem import DemMetadata
from app.services.dem_store import save_dem_upload

router = APIRouter()


@router.post("/upload", response_model=DemMetadata, status_code=status.HTTP_201_CREATED)
async def upload_dem(file: UploadFile = File(...)) -> DemMetadata:
    if not file.filename:
        raise HTTPException(status_code=400, detail={"code": "INVALID_DEM", "message": "Missing file name."})

    try:
        return await save_dem_upload(file)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc
