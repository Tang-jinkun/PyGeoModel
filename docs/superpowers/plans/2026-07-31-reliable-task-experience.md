# Reliable Task Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Execute each task with a failing test before production code.

**Goal:** Add bounded local scheduling, cancellation, recovery actions, resilient polling, adaptive GLB publication, and lazy result-layer loading.

**Architecture:** A process-local scheduler owns queue state and estimates; persisted task files remain authoritative for requests and outputs. On restart, interrupted work is recovered as a rerunnable failure. API routes enqueue named worker callables instead of attaching them directly to FastAPI background tasks. Frontend task state consumes the enriched detail response and defers result data fetches until a layer is requested.

**Tech Stack:** FastAPI, Pydantic, Python threading, Vue 3, Vitest, pytest, Rasterio, trimesh.

## Tasks

1. Add scheduler metadata, bounded execution, cancellation probes, queue estimates, and recovery tests.
2. Route radar and multi-radar creation/reruns through the scheduler; expose cancel and recovery actions.
3. Add task-center controls and unify multi-radar polling with retry/backoff behavior.
4. Defer GeoJSON fetches until result-layer visibility or focus requires them.
5. Change the GLB size limit into a non-blocking client-performance guideline and pin a compatible NumPy version.
6. Run focused tests, full test suites, production build, and Docker verification when available.
