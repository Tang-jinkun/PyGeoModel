# Offline Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a fully offline PyGeoModel delivery package with source code, frontend dependencies, Linux `amd64` and `arm64` Docker image archives, architecture-aware startup scripts, checksums, and one unified deployment guide.

**Architecture:** Build the existing backend and frontend images as Linux containers for `linux/amd64` (Windows x64 Docker Desktop Linux containers) and `linux/arm64` (ARM Linux Docker Engine). Save each architecture's backend/frontend images as separate Docker-loadable tar archives. The offline compose file selects the matching prebuilt image tag and mounts the bundled demo data. Offline frontend mode uses a local empty MapLibre style so startup never requests TianDiTu; DEM terrain geometry remains available through local Terrarium elevation tiles.

**Tech Stack:** Docker Buildx, Docker Compose v2, Python/FastAPI, Vue/Vite/MapLibre, PowerShell, POSIX shell, SHA-256.

## Global Constraints

- Do not start the backend or frontend application services while implementing or verifying this plan.
- Preserve the user's existing uncommitted feature changes; do not reset, checkout, clean, or delete them.
- Include the current radar red-line removal and artillery trajectory changes in the source delivery.
- Exclude `.tools/`, `PyGeoModel-前端重设计/`, logs, `.git/`, frontend build output, backend caches, old runtime task/output results, and other unrelated workspace artifacts.
- The Windows target is Docker Desktop Linux containers on x64 and therefore uses `linux/amd64`, not a Windows-native image.
- The ARM target is a Linux server using `linux/arm64`.
- Runtime startup must not pull images, install packages, or require Internet access.
- The prebuilt image archives are the authoritative runtime dependencies; the source bundle must additionally contain `frontend/node_modules` as requested.

---

## Task 1: Add and test an offline frontend runtime mode

**Files:** `frontend/src/config/runtime.ts`, `frontend/docker/write-runtime-config.mjs`, `frontend/src/map/tiandituStyle.ts`, `frontend/src/components/map/MapWorkspace.vue`, `frontend/src/config/runtime.test.ts`, `frontend/src/map/tiandituStyle.test.ts`, `frontend/src/components/map/MapWorkspace.test.ts`.

- [ ] Add an `offline` runtime flag and generate it from `PYGEOMODEL_OFFLINE`.
- [ ] Add a no-network MapLibre style for offline startup and make `MapWorkspace` select it only when the runtime flag is enabled; preserve caller-provided styles and the current online default.
- [ ] Add regression tests for runtime config serialization, offline style shape, and offline/default map style selection.
- [ ] Run the focused frontend tests and confirm they pass.

## Task 2: Add architecture-aware offline compose and startup/build tooling

**Files:** `deploy/offline/docker-compose.yml`, `deploy/offline/build-images.ps1`, `deploy/offline/start-offline.ps1`, `deploy/offline/start-offline.sh`, `.gitignore` if needed.

- [ ] Create an image-only compose file with no `build` directives, offline runtime environment, local data mount, health checks, and configurable host ports.
- [ ] Add a PowerShell build script that uses Buildx for `linux/amd64` and `linux/arm64`, tags images by architecture, and exports four Docker-loadable tar archives.
- [ ] Add Windows and Linux startup scripts that map host architecture to `amd64` or `arm64`, load only the matching archives, and run Compose with `--no-build`.
- [ ] Ensure scripts fail clearly when Docker is unavailable, Windows Docker Desktop is not using Linux containers, or a required archive is missing.
- [ ] Validate compose syntax and script help/dry-run paths without starting application services.

## Task 3: Add source delivery packager and unified deployment documentation

**Files:** `deploy/offline/package-source.ps1`, `docs/offline-deployment.md`, `deploy/offline/README.md` if useful.

- [ ] Add a packaging script that copies source files, `frontend/node_modules`, package locks, selected demo DEM/scenario data, deployment scripts, and image archives into a versioned delivery directory.
- [ ] Make the package filter explicit so excluded design files, tools, logs, `.git`, caches, build output, and historical task/output data cannot enter the delivery.
- [ ] Generate `SHA256SUMS` for every delivered image archive and source archive/file set.
- [ ] Write one unified Chinese deployment guide covering Windows x64 Docker Desktop, ARM Linux, offline startup, health checks, stop/restart, ports, data persistence, checksums, and the no-network basemap/DEM behavior.
- [ ] Run the packager in a temporary output location and inspect the resulting tree for forbidden files and required frontend dependencies.

## Task 4: Build both offline image variants and assemble the final artifact

**Files:** generated under `artifacts/pygeomodel-offline-*/` and excluded from source control unless the repository already tracks delivery artifacts.

- [ ] Confirm Docker Desktop/Buildx is available; start Docker Desktop only if needed for image construction, without starting the application compose stack.
- [ ] Build and export backend/frontend images for `linux/amd64` and `linux/arm64` using the repository's pinned dependency manifests.
- [ ] Verify each archive can be inspected and loaded by Docker, and verify image architecture metadata matches the requested target.
- [ ] Run the source packager to create the final delivery directory containing both architecture sets, source dependencies, scripts, docs, and checksums.
- [ ] Do not delete or modify unrelated user files in the workspace.

## Task 5: Final verification and handoff

- [ ] Run `py -3.13 -m pytest backend/tests -q`.
- [ ] Run `npm test` and `npm run build` from `frontend`.
- [ ] Run `git diff --check` and inspect the final source/package manifest.
- [ ] Verify no application service was started during the task and report the exact artifact path, image tags, target architectures, and verification results.
