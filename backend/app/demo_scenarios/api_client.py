import time
from typing import Any

import httpx

from app.demo_scenarios.registry import ModelSpec
from app.demo_scenarios.storage import canonical_request_hash


class DemoApiClient:
    def __init__(
        self,
        base_url: str,
        *,
        http: httpx.Client | None = None,
        poll_seconds: float = 2,
        task_timeout_seconds: float = 900,
        retries: int = 3,
    ) -> None:
        self.http = http or httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=30,
        )
        self.poll_seconds = poll_seconds
        self.task_timeout_seconds = task_timeout_seconds
        self.retries = retries
        self.retry_count = 0

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        for attempt in range(self.retries + 1):
            try:
                response = self.http.request(method, path, **kwargs)
                if response.status_code < 500:
                    response.raise_for_status()
                    return response
                if attempt == self.retries:
                    response.raise_for_status()
            except httpx.TransportError:
                if attempt == self.retries:
                    raise
            self.retry_count += 1
            time.sleep(min(2**attempt, 5))
        raise RuntimeError("unreachable retry state")

    def health(self) -> None:
        payload = self._request("GET", "/api/health").json()
        if payload != {"status": "ok"}:
            raise RuntimeError(f"Unexpected health response: {payload}")

    def find_matching_task(
        self,
        spec: ModelSpec,
        request_hash: str,
        statuses: frozenset[str] = frozenset({"finished"}),
    ) -> str | None:
        summaries = self._request("GET", spec.base_path).json()
        for summary in summaries:
            if summary.get("status") not in statuses:
                continue
            task_id = str(summary["task_id"])
            detail = self._request("GET", f"{spec.base_path}/{task_id}").json()
            request = detail.get("request")
            if (
                isinstance(request, dict)
                and canonical_request_hash(request) == request_hash
            ):
                return task_id
        return None

    def create_task(self, spec: ModelSpec, request: dict[str, Any]) -> str:
        request_hash = canonical_request_hash(request)
        active_statuses = frozenset({"pending", "running", "finished"})
        for attempt in range(self.retries + 1):
            try:
                response = self.http.post(spec.base_path, json=request)
                if response.status_code < 500:
                    response.raise_for_status()
                    return str(response.json()["task_id"])
                matching = self.find_matching_task(
                    spec,
                    request_hash,
                    active_statuses,
                )
                if matching is not None:
                    return matching
                if attempt == self.retries:
                    response.raise_for_status()
            except httpx.TransportError:
                matching = self.find_matching_task(
                    spec,
                    request_hash,
                    active_statuses,
                )
                if matching is not None:
                    return matching
                if attempt == self.retries:
                    raise
            self.retry_count += 1
            time.sleep(min(2**attempt, 5))
        raise RuntimeError("unreachable create retry state")

    def wait_for_task(self, spec: ModelSpec, task_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.task_timeout_seconds
        while time.monotonic() <= deadline:
            detail = self._request(
                "GET",
                f"{spec.base_path}/{task_id}",
            ).json()
            if detail.get("status") == "finished":
                return detail
            if detail.get("status") == "failed":
                raise RuntimeError(
                    detail.get("message") or f"Task failed: {task_id}"
                )
            time.sleep(self.poll_seconds)
        raise TimeoutError(f"Task timed out: {task_id}")

    def task_result(
        self,
        spec: ModelSpec,
        task_id: str,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        metrics = self._request(
            "GET",
            f"{spec.base_path}/{task_id}/metrics",
        ).json()
        outputs = self._request(
            "GET",
            f"{spec.base_path}/{task_id}/outputs",
        ).json()
        return metrics, outputs
