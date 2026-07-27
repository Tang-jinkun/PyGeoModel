import logging
from typing import Literal

import httpx

from app.core.config import Settings, settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)
IntegrationStatus = Literal["configured", "available", "unavailable"]
_last_status: IntegrationStatus | None = None


class _RedactingTransport(httpx.AsyncBaseTransport):
    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self.inner = inner

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        try:
            return await self.inner.handle_async_request(request)
        finally:
            request.url = request.url.copy_set_param("tk", "REDACTED")

    async def aclose(self) -> None:
        await self.inner.aclose()


class TiandituService:
    def __init__(
        self,
        config: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self.transport = transport

    async def fetch_tile(
        self,
        *,
        node: str,
        layer: str,
        tile_matrix: int,
        tile_row: int,
        tile_col: int,
    ) -> tuple[bytes, str]:
        global _last_status
        token = self.config.tianditu_token
        secret = token.get_secret_value() if token is not None else ""
        if not secret:
            _last_status = "unavailable"
            raise AppError(
                "TIANDITU_NOT_CONFIGURED",
                "TianDiTu integration is not configured.",
                status_code=503,
            )
        headers = {"User-Agent": "PyGeoModel/0.1"}
        if self.config.tianditu_referer:
            headers["Referer"] = self.config.tianditu_referer
        params = {
            "SERVICE": "WMTS",
            "REQUEST": "GetTile",
            "VERSION": "1.0.0",
            "LAYER": layer,
            "STYLE": "default",
            "TILEMATRIXSET": "w",
            "FORMAT": "tiles",
            "TILEMATRIX": str(tile_matrix),
            "TILEROW": str(tile_row),
            "TILECOL": str(tile_col),
            "tk": secret,
        }
        try:
            transport = _RedactingTransport(self.transport or httpx.AsyncHTTPTransport())
            async with httpx.AsyncClient(
                transport=transport,
                timeout=httpx.Timeout(10.0, connect=5.0),
                follow_redirects=False,
                headers=headers,
            ) as client:
                response = await client.get(
                    f"https://{node}.tianditu.gov.cn/{layer}_w/wmts",
                    params=params,
                )
        except httpx.TransportError as exc:
            _last_status = "unavailable"
            logger.warning("TianDiTu tile request unavailable", extra={"node": node, "layer": layer})
            raise AppError(
                "TIANDITU_UPSTREAM_UNAVAILABLE",
                "TianDiTu tile service is unavailable.",
                status_code=502,
            ) from exc
        if response.status_code in {401, 403}:
            _last_status = "unavailable"
            logger.warning("TianDiTu upstream authentication failed", extra={"node": node, "layer": layer})
            raise AppError(
                "TIANDITU_UPSTREAM_AUTH_FAILED",
                "TianDiTu upstream authentication failed.",
                status_code=502,
            )
        if not response.is_success:
            _last_status = "unavailable"
            logger.warning(
                "TianDiTu upstream request failed",
                extra={"node": node, "layer": layer, "upstream_status": response.status_code},
            )
            raise AppError(
                "TIANDITU_UPSTREAM_ERROR",
                "TianDiTu tile service returned an error.",
                status_code=502,
            )
        _last_status = "available"
        return response.content, response.headers.get("Content-Type", "application/octet-stream")


def tianditu_integration_status(config: Settings = settings) -> IntegrationStatus:
    token = config.tianditu_token
    if token is None or not token.get_secret_value():
        return "unavailable"
    return _last_status or "configured"
