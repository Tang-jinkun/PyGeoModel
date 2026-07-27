# Two-Station Cooperative Radar 3D Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow two through five radar stations in cooperative 3D mode while preserving the existing aggregate-mode range.

**Architecture:** Keep the current request and rendering flow unchanged. Align the backend schema guard and both frontend validation entry points around the same two-to-five boundary, with focused API and component regression tests.

**Tech Stack:** FastAPI, Pydantic, pytest, Vue 3, TypeScript, Vitest

## Global Constraints

- Cooperative 3D accepts exactly two through five stations.
- Aggregate mode continues to accept two through 256 stations.
- No worker, artifact, or rendering behavior changes.

---

### Task 1: Lock the new boundary with regression tests

**Files:**
- Modify: `backend/tests/test_multi_radar_api.py`
- Modify: `frontend/src/components/MultiRadarPanel.test.ts`
- Create: `frontend/src/components/workbench/MultiRadarStationEditor.test.ts`

**Interfaces:**
- Consumes: `POST /api/radar/multi-coverage` and the two existing multi-radar form components.
- Produces: regression coverage proving two stations are accepted and six remain rejected.

- [x] Change the backend accepted cooperative request fixture from three stations to two, and retain the six-station rejection assertion with the new message.
- [x] Change the legacy panel test to submit exactly two stations.
- [x] Add a workbench editor test asserting two cooperative stations produce no validation alert.
- [x] Run the focused backend and frontend tests and confirm they fail because the current production guards still require three stations.

### Task 2: Align production validation and documentation

**Files:**
- Modify: `backend/app/schemas/radar.py`
- Modify: `frontend/src/components/MultiRadarPanel.vue`
- Modify: `frontend/src/components/workbench/MultiRadarStationEditor.vue`
- Modify: `docs/superpowers/specs/2026-07-26-multi-radar-fusion-3d-design.md`

**Interfaces:**
- Consumes: `MultiRadarRequest.presentation_mode` and station-array lengths.
- Produces: consistent two-to-five validation and user-facing messages.

- [x] Replace each cooperative lower-bound check of three with two.
- [x] Update English and Chinese validation text to say two through five.
- [x] Update the design scope from three-to-five to two-to-five without changing the rendering design.
- [x] Run focused tests, the full backend suite, the full frontend suite, and the frontend production build.
