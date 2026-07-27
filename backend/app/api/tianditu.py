from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response

from app.core.config import settings
from app.core.errors import AppError
from app.services.tianditu import TiandituService

router = APIRouter()
_service = TiandituService(settings)


def get_tianditu_service() -> TiandituService:
    return _service


@router.get("/tianditu/{node}/wmts")
async def read_tianditu_tile(
    node: Annotated[str, Path(pattern=r"^t[0-7]$")],
    wmts_service: Annotated[Literal["WMTS"], Query(alias="SERVICE")],
    request: Annotated[Literal["GetTile"], Query(alias="REQUEST")],
    version: Annotated[Literal["1.0.0"], Query(alias="VERSION")],
    layer: Annotated[Literal["vec", "cva"], Query(alias="LAYER")],
    style: Annotated[Literal["default"], Query(alias="STYLE")],
    matrix_set: Annotated[Literal["w"], Query(alias="TILEMATRIXSET")],
    tile_format: Annotated[Literal["tiles"], Query(alias="FORMAT")],
    tile_matrix: Annotated[int, Query(alias="TILEMATRIX", ge=0)],
    tile_row: Annotated[int, Query(alias="TILEROW", ge=0)],
    tile_col: Annotated[int, Query(alias="TILECOL", ge=0)],
    proxy: Annotated[TiandituService, Depends(get_tianditu_service)],
    tk: Annotated[str | None, Query()] = None,
) -> Response:
    del wmts_service, request, version, style, matrix_set, tile_format, tk
    try:
        content, content_type = await proxy.fetch_tile(
            node=node,
            layer=layer,
            tile_matrix=tile_matrix,
            tile_row=tile_row,
            tile_col=tile_col,
        )
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc
    return Response(
        content=content,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
