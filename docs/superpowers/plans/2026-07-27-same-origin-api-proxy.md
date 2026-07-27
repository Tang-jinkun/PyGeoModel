# Same-Origin API Proxy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Compose frontend reach the backend without exposing a browser-local loopback API URL.

**Architecture:** Route browser API traffic through the frontend origin and proxy `/api/*` from the Node static server to the internal backend service. Preserve explicit external API configuration as an override.

**Tech Stack:** Node.js HTTP server, Docker Compose, Vitest, pytest

## Global Constraints

- Proxy only `/api` and `/api/*`.
- Preserve paths, query strings, methods, headers, bodies, status codes, and response headers.
- Return 502 for backend connection failures.
- Preserve static-file and SPA fallback behavior outside `/api`.

---

### Task 1: Specify proxy and deployment behavior

**Files:**
- Modify: `frontend/docker/server.test.ts`
- Modify: `backend/tests/test_deployment_config.py`

- [x] Add a real HTTP integration test for API path and query forwarding.
- [x] Change the Compose assertion to require an empty default API base.
- [x] Run focused tests and confirm both fail against the current implementation.

### Task 2: Implement and deploy the same-origin path

**Files:**
- Modify: `frontend/docker/server.mjs`
- Modify: `docker-compose.yml`

- [x] Add bounded `/api` proxying with a 502 failure response.
- [x] Change the Compose runtime API base default to empty.
- [x] Run focused and full tests plus the production build.
- [x] Rebuild the frontend container and verify workspace APIs through port 5173.
