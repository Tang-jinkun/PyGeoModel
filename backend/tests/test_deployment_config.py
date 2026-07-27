from pathlib import Path

import httpx
import yaml

from scripts.verify_deployment import verify_deployment

ROOT = Path(__file__).resolve().parents[2]


def test_compose_uses_runtime_api_and_configurable_backend_environment() -> None:
    compose_text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    compose = yaml.safe_load(compose_text)
    frontend = compose["services"]["frontend"]
    backend = compose["services"]["backend"]

    assert "VITE_API_BASE" not in compose_text
    assert "VITE_BASE_PATH" not in compose_text
    assert "PYGEOMODEL_API_BASE_URL" in frontend["environment"]
    assert "${PYGEOMODEL_API_BASE_URL-/PyGeoModel}" in compose_text
    assert "PYGEOMODEL_CORS_ORIGINS" in backend["environment"]
    assert "PYGEOMODEL_TIANDITU_TOKEN" in backend["environment"]
    assert "PYGEOMODEL_BACKEND_BIND" in backend["ports"][0]
    assert "PYGEOMODEL_FRONTEND_BIND" in frontend["ports"][0]
    assert {key for key in frontend["build"]["args"] if key.startswith("VITE_")} == {
        "VITE_MAP_ENGINE", "VITE_MAPBOX_ACCESS_TOKEN"
    }


def test_nginx_example_contains_only_generic_frontend_and_api_routes() -> None:
    config = (ROOT / "deploy/nginx/pygeomodel.conf.example").read_text(encoding="utf-8")
    assert "location /PyGeoModel/api/" in config
    assert "location /PyGeoModel/" in config
    assert "/outputs" not in config
    assert "/tianditu" not in config


def test_verifier_checks_runtime_health_artifact_and_tile_without_exposing_query(capsys) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/PyGeoModel/runtime-config.js":
            return httpx.Response(200, text='window.__PYGEOMODEL_RUNTIME_CONFIG__ = {"apiBaseUrl":"/PyGeoModel"};')
        if path == "/PyGeoModel/api/health":
            return httpx.Response(200, json={"status": "ok"})
        if path == "/PyGeoModel/api/radar/coverage/task_a":
            return httpx.Response(200, json={"task_id": "task_a", "result_state": "ready"})
        if path == "/PyGeoModel/api/radar/coverage/task_a/outputs":
            return httpx.Response(200, json=[{
                "kind": "visible_geojson", "exists": True,
                "download_path": "/api/radar/coverage/task_a/outputs/visible_geojson"
            }])
        if path.endswith("/outputs/visible_geojson"):
            return httpx.Response(200, content=b"{}", headers={"Content-Type": "application/geo+json"})
        if path == "/PyGeoModel/api/map/tianditu/t0/wmts":
            return httpx.Response(200, content=b"tile", headers={"Content-Type": "image/png"})
        return httpx.Response(404)

    verify_deployment(
        frontend_url="http://example.test/PyGeoModel/",
        api_base_url="http://example.test/PyGeoModel",
        task_id="task_a",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    output = capsys.readouterr().out
    assert "health: ok" in output
    assert "artifact: ok" in output
    assert "tile: ok" in output
    assert "SERVICE=WMTS" not in output
    assert "TILECOL" not in output
