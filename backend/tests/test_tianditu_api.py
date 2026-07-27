import logging

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.tianditu import get_tianditu_service
from app.core.config import Settings, settings
from app.main import create_app
from app.services.tianditu import TiandituService


def _query() -> dict[str, str]:
    return {
        "SERVICE": "WMTS",
        "REQUEST": "GetTile",
        "VERSION": "1.0.0",
        "LAYER": "vec",
        "STYLE": "default",
        "TILEMATRIXSET": "w",
        "FORMAT": "tiles",
        "TILEMATRIX": "9",
        "TILEROW": "207",
        "TILECOL": "367",
        "tk": "client-token-must-be-ignored",
    }


def _client(handler, token: str = "server-secret") -> TestClient:
    service = TiandituService(
        Settings(tianditu_token=token),
        transport=httpx.MockTransport(handler),
    )
    app = create_app()
    app.dependency_overrides[get_tianditu_service] = lambda: service
    return TestClient(app)


def test_proxy_uses_server_token_and_passes_tile_bytes() -> None:
    captured: list[dict[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append({
            "host": request.url.host,
            "path": request.url.path,
            "token": request.url.params.get("tk"),
        })
        return httpx.Response(200, content=b"tile", headers={"Content-Type": "image/png"})

    response = _client(handler).get("/api/map/tianditu/t6/wmts", params=_query())

    assert response.status_code == 200
    assert response.content == b"tile"
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "public, max-age=86400"
    assert captured[0]["host"] == "t6.tianditu.gov.cn"
    assert captured[0]["path"] == "/vec_w/wmts"
    assert captured[0]["token"] == "server-secret"


@pytest.mark.parametrize("node", ["t8", "t00", "other"])
def test_proxy_rejects_unknown_nodes(node: str) -> None:
    response = _client(lambda _: httpx.Response(200, content=b"tile")).get(
        f"/api/map/tianditu/{node}/wmts", params=_query()
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("field", "value"),
    [("REQUEST", "GetCapabilities"), ("LAYER", "img"), ("TILEMATRIXSET", "c"),
     ("TILEMATRIX", "-1"), ("TILEROW", "x"), ("SERVICE", "bad")],
)
def test_proxy_rejects_non_allowlisted_wmts_parameters(field: str, value: str) -> None:
    query = _query()
    query[field] = value
    response = _client(lambda _: httpx.Response(200, content=b"tile")).get(
        "/api/map/tianditu/t0/wmts", params=query
    )
    assert response.status_code == 422


@pytest.mark.parametrize("upstream_status", [401, 403])
def test_proxy_maps_upstream_auth_failure_without_leaking_token(
    upstream_status: int, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    response = _client(lambda _: httpx.Response(upstream_status), token="do-not-leak").get(
        "/api/map/tianditu/t0/wmts", params=_query()
    )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "TIANDITU_UPSTREAM_AUTH_FAILED"
    assert "do-not-leak" not in response.text
    assert "do-not-leak" not in caplog.text


def test_proxy_requires_server_configuration() -> None:
    response = _client(lambda _: httpx.Response(200), token="").get(
        "/api/map/tianditu/t0/wmts", params=_query()
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "TIANDITU_NOT_CONFIGURED"


def test_health_stays_ok_independently_of_tianditu(monkeypatch) -> None:
    monkeypatch.setattr(settings, "tianditu_token", None, raising=False)
    response = TestClient(create_app()).get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["integrations"]["tianditu"] in {
        "configured", "available", "unavailable"
    }


@pytest.mark.parametrize(
    "referer",
    ["javascript:alert(1)", "https://u:p@example.com", "https://example.com?x=1", "https://example.com/#x"],
)
def test_settings_reject_unsafe_tianditu_referers(referer: str) -> None:
    with pytest.raises(ValidationError):
        Settings(tianditu_referer=referer)


def test_settings_normalize_tianditu_referer_origin() -> None:
    assert Settings(tianditu_referer="https://example.com/").tianditu_referer == "https://example.com"
