# Same-Origin API Proxy Design

## Problem

The Compose frontend publishes a runtime API URL of `http://127.0.0.1:8000`.
For a browser running outside the server's network namespace, that loopback
address points at the browser host, so every workspace request fails before it
reaches the backend.

## Design

The frontend runtime configuration defaults to an empty API base, causing all
browser requests to use their current origin. The existing Node static server
proxies only `/api` and `/api/*` to the internal `VITE_PROXY_TARGET`, which is
`http://backend:8000` in the image. Non-API paths retain the current static-file
and SPA fallback behavior. An explicit `PYGEOMODEL_API_BASE_URL` continues to
override same-origin operation for deployments with a separately exposed API.

Proxy connection failures return HTTP 502. They must never fall through to the
SPA document because an HTML response from an API route obscures deployment
failures.

## Verification

- A server test proves API path and query forwarding.
- Deployment configuration tests prove the Compose default is same-origin.
- Frontend tests and production build remain green.
- Runtime checks verify `/api/health` through port 5173 and workspace endpoints.
