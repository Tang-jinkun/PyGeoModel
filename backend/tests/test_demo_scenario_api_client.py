import httpx

from app.demo_scenarios.api_client import DemoApiClient
from app.demo_scenarios.registry import MODEL_SPECS
from app.demo_scenarios.storage import canonical_request_hash


def test_client_finds_finished_task_by_detail_request_hash() -> None:
    request = {"dem_id": "dem_a", "observer": {"lon": 79.8, "lat": 31.4}}

    def handler(incoming: httpx.Request) -> httpx.Response:
        if incoming.url.path == "/api/watchpost/detection":
            return httpx.Response(
                200,
                json=[
                    {"task_id": "task_1", "dem_id": "dem_a", "status": "finished"}
                ],
            )
        if incoming.url.path == "/api/watchpost/detection/task_1":
            return httpx.Response(
                200,
                json={"task_id": "task_1", "status": "finished", "request": request},
            )
        raise AssertionError(incoming.url.path)

    http = httpx.Client(
        base_url="http://test",
        transport=httpx.MockTransport(handler),
    )
    client = DemoApiClient(
        "http://test",
        http=http,
        poll_seconds=0,
        task_timeout_seconds=1,
    )

    found = client.find_matching_task(
        MODEL_SPECS["watchpost"],
        canonical_request_hash(request),
    )

    assert found == "task_1"


def test_wait_for_task_returns_finished_detail() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        status = "running" if calls == 1 else "finished"
        return httpx.Response(200, json={"task_id": "task_1", "status": status})

    http = httpx.Client(
        base_url="http://test",
        transport=httpx.MockTransport(handler),
    )
    client = DemoApiClient(
        "http://test",
        http=http,
        poll_seconds=0,
        task_timeout_seconds=1,
    )

    detail = client.wait_for_task(MODEL_SPECS["uav"], "task_1")

    assert detail["status"] == "finished"
    assert calls == 2


def test_create_task_recovers_post_timeout_without_duplicate_submission() -> None:
    request = {"dem_id": "dem_a"}
    post_count = 0

    def handler(incoming: httpx.Request) -> httpx.Response:
        nonlocal post_count
        if incoming.method == "POST":
            post_count += 1
            raise httpx.ReadTimeout("response lost", request=incoming)
        if incoming.url.path == "/api/uav/recon":
            return httpx.Response(
                200,
                json=[{"task_id": "task_1", "status": "pending"}],
            )
        if incoming.url.path == "/api/uav/recon/task_1":
            return httpx.Response(
                200,
                json={"task_id": "task_1", "status": "pending", "request": request},
            )
        raise AssertionError(incoming.url.path)

    http = httpx.Client(
        base_url="http://test",
        transport=httpx.MockTransport(handler),
    )
    client = DemoApiClient(
        "http://test",
        http=http,
        poll_seconds=0,
        task_timeout_seconds=1,
    )

    task_id = client.create_task(MODEL_SPECS["uav"], request)

    assert task_id == "task_1"
    assert post_count == 1
