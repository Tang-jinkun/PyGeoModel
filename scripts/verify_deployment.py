#!/usr/bin/env python3
import argparse
import json
from urllib.parse import urljoin

import httpx


def verify_deployment(
    *,
    frontend_url: str,
    api_base_url: str,
    task_id: str | None = None,
    client: httpx.Client | None = None,
) -> None:
    owned_client = client is None
    http = client or httpx.Client(timeout=httpx.Timeout(20.0, connect=5.0), follow_redirects=True)
    try:
        runtime = _request(http, urljoin(_with_slash(frontend_url), "runtime-config.js")).text
        assignment = runtime.partition("=")[2].strip().removesuffix(";")
        config = json.loads(assignment)
        if not isinstance(config.get("apiBaseUrl"), str):
            raise RuntimeError("runtime config does not contain apiBaseUrl")
        print("runtime-config: ok")

        health = _request(http, _api_url(api_base_url, "/api/health")).json()
        if health.get("status") != "ok":
            raise RuntimeError("backend health is not ok")
        print("health: ok")

        if task_id:
            task_path = f"/api/radar/coverage/{task_id}"
            task = _request(http, _api_url(api_base_url, task_path)).json()
            if task.get("result_state") != "ready":
                raise RuntimeError("selected task result is not ready")
            files = _request(http, _api_url(api_base_url, f"{task_path}/outputs")).json()
            descriptor = next(
                (item for item in files if item.get("exists") and item.get("download_path")),
                None,
            )
            if descriptor is None:
                raise RuntimeError("selected task has no downloadable descriptor")
            _request(http, _api_url(api_base_url, descriptor["download_path"]))
            print("artifact: ok")

        tile = _request(
            http,
            _api_url(api_base_url, "/api/map/tianditu/t0/wmts"),
            params={
                "SERVICE": "WMTS", "REQUEST": "GetTile", "VERSION": "1.0.0",
                "LAYER": "vec", "STYLE": "default", "TILEMATRIXSET": "w",
                "FORMAT": "tiles", "TILEMATRIX": "1", "TILEROW": "0", "TILECOL": "0",
            },
        )
        if not tile.headers.get("Content-Type", "").startswith("image/"):
            raise RuntimeError("tile response is not an image")
        print("tile: ok")
    finally:
        if owned_client:
            http.close()


def _request(client: httpx.Client, url: str, **kwargs) -> httpx.Response:
    response = client.get(url, **kwargs)
    response.raise_for_status()
    return response


def _api_url(api_base_url: str, path: str) -> str:
    return f"{api_base_url.rstrip('/')}{path}"


def _with_slash(value: str) -> str:
    return f"{value.rstrip('/')}/"


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a PyGeoModel frontend/API deployment.")
    parser.add_argument("--frontend-url", required=True)
    parser.add_argument("--api-base-url", required=True, help="Public backend base excluding /api")
    parser.add_argument("--task-id")
    args = parser.parse_args()
    verify_deployment(
        frontend_url=args.frontend_url,
        api_base_url=args.api_base_url,
        task_id=args.task_id,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
