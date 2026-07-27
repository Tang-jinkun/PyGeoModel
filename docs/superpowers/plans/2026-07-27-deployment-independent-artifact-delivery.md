# Deployment-Independent Artifact Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every task artifact and TianDiTu tile load through a backend-owned, deployment-independent API contract in Nginx subpath, same-origin root, and direct cross-origin deployments.

**Architecture:** A shared backend `ArtifactStore` validates registered output contracts, writes a versioned checksum manifest, publishes sibling staging directories atomically, and derives live result availability for every task response. The frontend reads a container-generated runtime API base and resolves all API, GeoJSON, GLB, binary, and tile paths through one URL resolver; Nginx is an optional edge proxy and no longer owns artifact or TianDiTu semantics.

**Tech Stack:** Python 3.12, FastAPI 0.115.6, Pydantic 2.7, HTTPX 0.28, Pytest 8.3, Vue 3.5, TypeScript 5.7, Vite 6, Vitest 4, Docker Compose, Node 22, Nginx.

## Global Constraints

- Keep task computation state separate from `result_state`, whose exact values are `pending`, `ready`, and `unavailable`.
- Never trust persisted `exists` fields when serving list or detail responses.
- Never start computation while listing, reading, or downloading historical tasks.
- Explicit rerun requires an `Idempotency-Key`; the same historical task/key pair returns one new task ID and schedules computation once, while a new key creates a new rerun. The new task stores `rerun_of` and leaves the historical task unchanged.
- `artifact-manifest.json` schema version is `1`; every entry records kind, filename, media type, required/public flags, byte size, and SHA-256.
- Normal reads verify manifest shape, required file presence, and byte sizes; only reconciliation verifies SHA-256.
- A worker publishes only by renaming a complete sibling staging directory to its final task directory.
- Canonical client access uses `download_path`; new frontend code must ignore legacy `url` and `download_url`.
- `PYGEOMODEL_API_BASE_URL` excludes `/api`; valid examples are `/PyGeoModel`, the empty string, and `http://124.221.208.30:8000`.
- Runtime configuration takes precedence over the temporary `VITE_API_BASE` fallback.
- `PYGEOMODEL_TIANDITU_TOKEN` stays server-side and must not appear in frontend assets, runtime configuration, public URLs, response bodies, or logs.
- `VITE_MAP_ENGINE` remains build-time, defaults to `maplibre`, and supports explicit `mapbox` with `VITE_MAPBOX_ACCESS_TOKEN`.
- Raw `/outputs` is unmounted after API descriptors preserve compatibility by mirroring `download_path` into deprecated `download_url`; `url` remains null and the migrated frontend reads only `download_path`.
- Reconciliation defaults to dry-run; repair requires explicit model and task IDs.
- The seven missing production radar results are repaired only after dry-run review and are never recomputed from a read endpoint.
- Do not print, commit, or embed real TianDiTu or Mapbox tokens.

## File Structure

- Create `backend/app/schemas/artifacts.py`: shared manifest, descriptor, result-state, and reconciliation response models.
- Create `backend/app/services/artifact_contracts.py`: immutable output specifications and the complete model contract registry.
- Create `backend/app/services/artifact_store.py`: safe paths, staging, manifest validation, atomic publish, live listing/download, deletion, and reconciliation.
- Create `backend/app/services/task_results.py`: apply live artifact state to model-specific task schema instances.
- Create `backend/app/api/tianditu.py` and `backend/app/services/tianditu.py`: validated server-side TianDiTu proxy.
- Create `backend/app/services/reconciliation.py` and `scripts/reconcile_artifacts.py`: administrative scan, legacy upgrade, and selected repair orchestration.
- Create `frontend/src/config/runtime.ts`: validate and expose container runtime configuration.
- Create `frontend/docker/write-runtime-config.mjs` and `frontend/docker/server.mjs`: JSON-safe config generation and static serving with `no-store` runtime config.
- Modify all backend model schemas, task stores, workers, and APIs listed in Tasks 3-5 to use the shared artifact contract.
- Modify `frontend/src/api/http.ts`, all artifact consumers, and multi-radar adapters to use `download_path` through one resolver.
- Modify `frontend/src/map/tiandituStyle.ts` to use the backend tile endpoint through that resolver.
- Modify `frontend/Dockerfile`, `frontend/index.html`, `frontend/vite.config.ts`, `frontend/.env.example`, and `docker-compose.yml` for portable runtime deployment.
- Create `deploy/nginx/pygeomodel.conf.example` and `docs/deployment.md`: optional Nginx and direct-port deployment examples without credentials.

---

### Task 1: Shared Artifact Models And Store

**Files:**
- Create: `backend/app/schemas/artifacts.py`
- Create: `backend/app/services/artifact_contracts.py`
- Create: `backend/app/services/artifact_store.py`
- Create: `backend/tests/test_artifact_store.py`

**Interfaces:**
- Produces: `ArtifactSpec`, `OutputContract`, `ArtifactManifest`, `ArtifactDescriptor`, `ResultAvailability`, `ArtifactStore.create_staging_dir()`, `publish()`, `inspect()`, `list_descriptors()`, `resolve_download()`, `delete()`, and `reconcile()`.
- Produces: `artifact_store = ArtifactStore(settings.outputs_dir)` through a getter that reads the current mutable test setting rather than capturing the original path at import time.

- [ ] **Step 1: Write failing manifest, path-safety, atomic publication, optional-artifact, and stale-size tests**

Create `backend/tests/test_artifact_store.py` with focused tests using this contract fixture:

```python
from pathlib import Path

import pytest

from app.core.errors import AppError
from app.services.artifact_contracts import ArtifactSpec, OutputContract
from app.services.artifact_store import ArtifactStore


@pytest.fixture
def contract() -> OutputContract:
    return OutputContract(
        model_id="test_model",
        version=1,
        download_path_template="/api/test/tasks/{task_id}/outputs/{kind}",
        artifacts=(
            ArtifactSpec("required_json", "required.json", "application/json", "Required", required=True),
            ArtifactSpec("optional_bin", "optional.bin", "application/octet-stream", "Optional", required=False),
        ),
    )


def test_publish_renames_complete_sibling_and_writes_checksums(tmp_path: Path, contract: OutputContract) -> None:
    store = ArtifactStore(tmp_path / "outputs")
    staging = store.create_staging_dir("task_valid")
    (staging / "required.json").write_text('{"ok":true}', encoding="utf-8")

    manifest = store.publish("task_valid", contract, staging)

    final = tmp_path / "outputs" / "task_valid"
    assert not staging.exists()
    assert manifest.schema_version == 1
    assert manifest.artifacts[0].sha256 == "4062edaf750fb8074e7e83e0c9028c94e32468a8b6f1614774328ef045150f93"
    assert (final / "artifact-manifest.json").exists()
    assert store.inspect("task_valid", contract, computation_status="finished").state == "ready"


def test_publish_rejects_missing_required_artifact_without_visible_result(tmp_path: Path, contract: OutputContract) -> None:
    store = ArtifactStore(tmp_path / "outputs")
    staging = store.create_staging_dir("task_missing")

    with pytest.raises(AppError, match="required_json"):
        store.publish("task_missing", contract, staging)

    assert not (tmp_path / "outputs" / "task_missing").exists()


def test_inspect_marks_finished_result_unavailable_when_size_changes(tmp_path: Path, contract: OutputContract) -> None:
    store = ArtifactStore(tmp_path / "outputs")
    staging = store.create_staging_dir("task_stale")
    (staging / "required.json").write_text("{}", encoding="utf-8")
    store.publish("task_stale", contract, staging)
    (tmp_path / "outputs" / "task_stale" / "required.json").write_text("changed", encoding="utf-8")

    state = store.inspect("task_stale", contract, computation_status="finished")

    assert state.state == "unavailable"
    assert state.reason_code == "ARTIFACT_SIZE_MISMATCH"


def test_resolve_download_rejects_traversal_and_missing_result(tmp_path: Path, contract: OutputContract) -> None:
    store = ArtifactStore(tmp_path / "outputs")
    with pytest.raises(AppError) as invalid:
        store.resolve_download("../task", "required_json", contract, computation_status="finished")
    assert invalid.value.status_code == 400

    with pytest.raises(AppError) as missing:
        store.resolve_download("task_missing", "required_json", contract, computation_status="finished")
    assert missing.value.status_code == 410
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
cd /home/PyGeoModel
PYTHONPATH=backend pytest backend/tests/test_artifact_store.py -q
```

Expected: collection fails because `app.schemas.artifacts`, `artifact_contracts`, and `artifact_store` do not exist.

- [ ] **Step 3: Implement the shared types and complete store behavior**

Create `backend/app/schemas/artifacts.py` with these public models and exact field names:

```python
from typing import Literal

from pydantic import BaseModel, Field

ResultState = Literal["pending", "ready", "unavailable"]


class ArtifactManifestEntry(BaseModel):
    kind: str
    filename: str
    media_type: str
    required: bool = True
    public: bool = True
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ArtifactManifest(BaseModel):
    schema_version: Literal[1] = 1
    task_id: str
    model_id: str
    created_at: str
    contract_version: int = Field(ge=1)
    artifacts: list[ArtifactManifestEntry]


class ArtifactDescriptor(BaseModel):
    kind: str
    label: str
    filename: str
    media_type: str
    required: bool = True
    size_bytes: int | None = None
    exists: bool = False
    download_path: str | None = None
    url: str | None = None
    download_url: str | None = None


class ResultAvailability(BaseModel):
    state: ResultState
    reason_code: str | None = None


class ArtifactReconciliationResult(BaseModel):
    task_id: str
    model_id: str
    state: ResultState
    reason_code: str | None = None
    action: Literal["none", "manifest_upgraded", "repair_eligible", "repair_ineligible"] = "none"
```

Create `backend/app/services/artifact_contracts.py` with immutable dataclasses. `OutputContract.spec(kind)` must raise `AppError("OUTPUT_KIND_NOT_FOUND", ..., 404)`. In `__post_init__`, reject duplicate kinds/filenames, filenames that are not a single basename, kinds outside `^[A-Za-z0-9_]+$`, contract versions below 1, and download templates missing exactly one `{task_id}` and `{kind}`. Allow worker-supplied dynamic artifacts only when `dynamic_kind_pattern` fully matches:

```python
from dataclasses import dataclass
import re

from app.core.errors import AppError


@dataclass(frozen=True)
class ArtifactSpec:
    kind: str
    filename: str
    media_type: str
    label: str
    required: bool = True
    public: bool = True


@dataclass(frozen=True)
class OutputContract:
    model_id: str
    version: int
    download_path_template: str
    artifacts: tuple[ArtifactSpec, ...]
    dynamic_kind_pattern: str | None = None

    def spec(self, kind: str) -> ArtifactSpec:
        for item in self.artifacts:
            if item.kind == kind:
                return item
        raise AppError("OUTPUT_KIND_NOT_FOUND", f"Output kind '{kind}' is not supported.", status_code=404)

    def accepts_dynamic(self, spec: ArtifactSpec) -> bool:
        return bool(self.dynamic_kind_pattern and re.fullmatch(self.dynamic_kind_pattern, spec.kind))
```

Implement `ArtifactStore` in `backend/app/services/artifact_store.py`. Use `Path.resolve()` containment checks, `hashlib.sha256()` in 1 MiB chunks, atomic JSON writes with flush/fsync, and sibling staging names `.{task_id}.staging-{uuid}`. `publish()` accepts `dynamic_artifacts: tuple[ArtifactSpec, ...] = ()`, validates every declared required artifact and every supplied dynamic file, writes the manifest last, fsyncs the staging directory, rejects an existing final directory with `ARTIFACT_RESULT_EXISTS`, calls `staging.replace(final)`, and fsyncs the outputs root after the rename. `list_descriptors()` returns all public contract/manifest entries, sets `download_path` only for live files, mirrors that API path into deprecated `download_url`, and leaves `url` null; missing files have neither path. `resolve_download()` returns `(Path, ArtifactDescriptor)`, using `409` for pending/running computation, `410` plus the live reason code for unavailable finished/partial/failed results, and `404` for an unknown kind. `delete()` returns whether it removed the directory and propagates filesystem failures so the owning task store can report partial deletion. `reconcile()` verifies checksums when requested and can write a manifest for a complete legacy directory only when `upgrade_legacy=True`. Emit structured publish/unavailable/reconcile logs with task ID, model ID, manifest version, result state, reason code, and artifact kind; never log request payloads or URLs.

Expose a getter instead of an import-time singleton so tests that replace `settings.data_dir` use the correct root:

```python
def get_artifact_store() -> ArtifactStore:
    return ArtifactStore(settings.outputs_dir)
```

- [ ] **Step 4: Run store tests and verify GREEN**

Run:

```bash
cd /home/PyGeoModel
PYTHONPATH=backend pytest backend/tests/test_artifact_store.py -q
```

Expected: all artifact store tests pass, including atomic publication, missing optional output, traversal rejection, size mismatch, checksum reconciliation, and legacy manifest upgrade.

- [ ] **Step 5: Commit the shared artifact foundation**

Run:

```bash
cd /home/PyGeoModel
git add backend/app/schemas/artifacts.py backend/app/services/artifact_contracts.py \
  backend/app/services/artifact_store.py backend/tests/test_artifact_store.py
git diff --cached --check
git commit -m "feat(backend): add atomic artifact store"
```

Expected: one commit containing only the shared artifact foundation.

---

### Task 2: Complete Output Contract Registry And Live Task State

**Files:**
- Modify: `backend/app/services/artifact_contracts.py`
- Create: `backend/app/services/task_results.py`
- Create: `backend/tests/test_artifact_contracts.py`
- Create: `backend/tests/test_task_results.py`
- Modify: `backend/app/schemas/radar.py`
- Modify: `backend/app/schemas/uav.py`
- Modify: `backend/app/schemas/watchpost.py`
- Modify: `backend/app/schemas/artillery.py`
- Modify: `backend/app/schemas/recon_vehicle.py`
- Modify: `backend/app/schemas/mobility.py`
- Modify: `backend/app/schemas/air_corridor.py`

**Interfaces:**
- Consumes: Task 1 `OutputContract`, `ArtifactDescriptor`, and `ArtifactStore.inspect/list_descriptors`.
- Produces: `OUTPUT_CONTRACTS`, `get_output_contract(model_id)`, and `apply_live_result(task, contract, store)`.
- Produces schema fields `result_state`, `result_reason_code`, `rerun_of`, and descriptor `download_path` for every task family, including multi-radar.

- [ ] **Step 1: Write failing registry and stale-persisted-state tests**

Create `backend/tests/test_artifact_contracts.py` asserting the exact registered IDs:

```python
from app.services.artifact_contracts import OUTPUT_CONTRACTS


def test_all_task_models_register_output_contracts() -> None:
    assert set(OUTPUT_CONTRACTS) == {
        "radar", "uav", "watchpost", "artillery", "recon_vehicle",
        "mobility", "air_corridor", "multi_radar",
    }
    for contract in OUTPUT_CONTRACTS.values():
        assert contract.version == 1
        assert len({item.kind for item in contract.artifacts}) == len(contract.artifacts)
        assert len({item.filename for item in contract.artifacts}) == len(contract.artifacts)
```

Create `backend/tests/test_task_results.py` with a finished task whose persisted output descriptor says `exists=True` but whose directory is missing, then assert:

```python
live = apply_live_result(task, get_output_contract("radar"), ArtifactStore(tmp_path / "outputs"))
assert live.result_state == "unavailable"
assert live.result_reason_code == "ARTIFACT_MANIFEST_MISSING"
assert all(item.exists is False and item.download_path is None for item in live.output_files)
assert live.metrics == task.metrics
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
cd /home/PyGeoModel
PYTHONPATH=backend pytest backend/tests/test_artifact_contracts.py backend/tests/test_task_results.py -q
```

Expected: failures because the registry, live hydration helper, and shared schema fields are absent.

- [ ] **Step 3: Register every artifact contract and add shared live fields**

Add this registry shape to `backend/app/services/artifact_contracts.py`; enter every tuple from the table exactly and use existing labels from the corresponding `*_output_files.py` modules:

| Model ID | Download template | Public artifacts | Internal/conditional artifacts |
|---|---|---|---|
| `radar` | `/api/radar/coverage/{task_id}/outputs/{kind}` | `viewshed_tif=viewshed.tif`, `visible_geojson=visible.geojson`, `blocked_geojson=blocked.geojson`, `range_geojson=radar_range.geojson`, `model_metadata_json=model_metadata.json`, `output_manifest_json=output_manifest.json`, `min_visible_height_tif=min_visible_height.tif`, `voxel_manifest_json=voxel_manifest.json`, `voxel_points_bin=voxel_points.bin`, `clipped_volume_manifest_json=clipped_volume_manifest.json`, `clipped_volume_cells_bin=clipped_volume_cells.bin`, `height_layers_manifest_json=height_layers_manifest.json`, `scene_glb=radar_detection_domain.glb`, `radar_platform_glb=radar_platform.glb` | Dynamic public kinds match `height_(visible|blocked)_[0-9A-Za-z_]+` |
| `uav` | `/api/uav/recon/{task_id}/outputs/{kind}` | `footprint_geojson=footprint.geojson`, `visible_geojson=visible.geojson`, `blocked_geojson=blocked.geojson`, `model_metadata_json=model_metadata.json`, `output_manifest_json=output_manifest.json` | none |
| `watchpost` | `/api/watchpost/detection/{task_id}/outputs/{kind}` | `viewshed_tif=viewshed.tif`, `visible_geojson=visible.geojson`, `blocked_geojson=blocked.geojson`, `range_geojson=range.geojson`, `model_metadata_json=model_metadata.json`, `output_manifest_json=output_manifest.json` | none |
| `artillery` | `/api/artillery/coverage/{task_id}/outputs/{kind}` | `theoretical_geojson=theoretical.geojson`, `reachable_geojson=reachable.geojson`, `terrain_masked_geojson=terrain_masked.geojson`, `sample_points_geojson=sample_points.geojson`, `model_metadata_json=model_metadata.json`, `output_manifest_json=output_manifest.json` | none |
| `recon_vehicle` | `/api/recon-vehicle/coverage/{task_id}/outputs/{kind}` | `footprint_geojson=footprint.geojson`, `visible_geojson=visible.geojson`, `blocked_geojson=blocked.geojson`, `model_metadata_json=model_metadata.json`, `output_manifest_json=output_manifest.json` | none |
| `mobility` | `/api/mobility/accessibility/{task_id}/outputs/{kind}` | `wheeled_path_geojson=wheeled_path.geojson`, `tracked_path_geojson=tracked_path.geojson`, `road_mask_geojson=road_mask.geojson`, `cost_summary_json=cost_summary.json`, `model_metadata_json=model_metadata.json`, `output_manifest_json=output_manifest.json` | none |
| `air_corridor` | `/api/air-corridor/planning/{task_id}/outputs/{kind}` | `corridor_path_geojson=corridor_path.geojson`, `corridor_buffer_geojson=corridor_buffer.geojson`, `threat_zones_geojson=threat_zones.geojson`, `risk_samples_geojson=risk_samples.geojson`, `cost_summary_json=cost_summary.json`, `scene_glb=air_corridor_result.glb`, `model_metadata_json=model_metadata.json`, `output_manifest_json=output_manifest.json` | none |
| `multi_radar` | `/api/radar/multi-coverage/{task_id}/outputs/{kind}` | `visible_union_geojson=visible_union.geojson`, `overlap_geojson=overlap.geojson`, `blind_geojson=blind.geojson`, `coverage_count_geojson=coverage_count.geojson`, `stations_geojson=stations.geojson`, `station_summaries_json=station_summaries.json` | Required non-public `station_masks_npz=station_masks.npz`, `grid_json=grid.json`; optional public `fusion_scene_glb=fusion_scene.glb`, `cooperative_intersection_glb=cooperative_intersection.glb` |

Add a common field mixin in `backend/app/schemas/artifacts.py`:

```python
class TaskResultFields(BaseModel):
    result_state: ResultState = "pending"
    result_reason_code: str | None = None
    rerun_of: str | None = None
```

Make each task summary model inherit `TaskResultFields` and declare `output_files: list[ArtifactDescriptor]`. Keep the existing model-specific output-file class names as compatibility subclasses of `ArtifactDescriptor` with `kind: str`; do not narrow response descriptors to the static output-kind Literal because radar publishes dynamic height kinds. Add `output_files: list[ArtifactDescriptor]` to `MultiRadarTaskStatus`. Add `errors: list[str] = Field(default_factory=list)` to every task-delete response model so a retry-safe delete can report a task-record or artifact-directory failure after attempting both resources.

Create `backend/app/services/task_results.py`:

```python
from typing import TypeVar

from app.services.artifact_contracts import OutputContract
from app.services.artifact_store import ArtifactStore

TaskT = TypeVar("TaskT")


def apply_live_result(task: TaskT, contract: OutputContract, store: ArtifactStore) -> TaskT:
    availability = store.inspect(task.task_id, contract, computation_status=task.status)
    task.result_state = availability.state
    task.result_reason_code = availability.reason_code
    task.output_files = store.list_descriptors(task.task_id, contract)
    return task
```

- [ ] **Step 4: Run registry, schema, and live-state tests**

Run:

```bash
cd /home/PyGeoModel
PYTHONPATH=backend pytest backend/tests/test_artifact_contracts.py backend/tests/test_task_results.py \
  backend/tests/test_output_files.py -q
```

Expected: all tests pass and legacy descriptor fields still deserialize while new live descriptors expose `download_path`.

- [ ] **Step 5: Commit contracts and live state**

Run:

```bash
cd /home/PyGeoModel
git add backend/app/schemas/artifacts.py backend/app/schemas/{radar,uav,watchpost,artillery,recon_vehicle,mobility,air_corridor}.py \
  backend/app/services/artifact_contracts.py backend/app/services/task_results.py \
  backend/tests/test_artifact_contracts.py backend/tests/test_task_results.py
git diff --cached --check
git commit -m "feat(backend): define task output contracts"
```

Expected: one commit with all model contract declarations and no worker/API behavior change yet.

---

### Task 3: Radar Atomic Publication, Live API Semantics, And Explicit Rerun

**Files:**
- Modify: `backend/app/workers/coverage_task.py`
- Modify: `backend/app/services/task_store.py`
- Modify: `backend/app/services/output_files.py`
- Modify: `backend/app/api/radar.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_coverage_task_outputs.py`
- Modify: `backend/tests/test_task_store.py`
- Modify: `backend/tests/test_radar_outputs_api.py`

**Interfaces:**
- Consumes: `get_output_contract("radar")`, `ArtifactStore.publish`, `apply_live_result`.
- Produces: live list/detail/output responses, dynamic radar height artifact kinds, `410` unavailable downloads, and `POST /api/radar/coverage/{task_id}/rerun`.

- [ ] **Step 1: Add failing radar behavior tests**

Add tests that assert all of the following:

```python
def test_finished_task_with_deleted_directory_is_unavailable_and_download_is_gone(client, finished_radar_task):
    detail = client.get(f"/api/radar/coverage/{finished_radar_task.task_id}")
    assert detail.status_code == 200
    assert detail.json()["result_state"] == "unavailable"
    assert detail.json()["output_files"][0]["download_path"] is None
    download = client.get(f"/api/radar/coverage/{finished_radar_task.task_id}/outputs/visible_geojson")
    assert download.status_code == 410
    assert download.json()["detail"]["code"] == "ARTIFACT_MANIFEST_MISSING"


def test_rerun_creates_new_pending_task_without_mutating_history(client, finished_radar_task, monkeypatch):
    scheduled = monkeypatch_background_task(monkeypatch)
    headers = {"Idempotency-Key": "radar-rerun-test-key"}
    response = client.post(f"/api/radar/coverage/{finished_radar_task.task_id}/rerun", headers=headers)
    retried = client.post(f"/api/radar/coverage/{finished_radar_task.task_id}/rerun", headers=headers)
    assert response.status_code == 202
    assert response.json()["task_id"] != finished_radar_task.task_id
    assert response.json()["rerun_of"] == finished_radar_task.task_id
    assert retried.json()["task_id"] == response.json()["task_id"]
    assert scheduled.call_count == 1


def test_opening_missing_history_never_schedules_rerun(client, finished_radar_task, monkeypatch):
    scheduled = monkeypatch_background_task(monkeypatch)
    assert client.get(f"/api/radar/coverage/{finished_radar_task.task_id}").status_code == 200
    assert scheduled.call_count == 0
```

Extend the worker test so a forced exception before `publish()` leaves neither a final task directory nor a manifest. Add a height-layer assertion that the published manifest and output list include `height_visible_0` and `height_blocked_0` and that the height manifest references those kinds. Add deletion tests proving a second delete is a successful no-op and a forced directory deletion failure still attempts task-record deletion and returns an `errors` entry.

- [ ] **Step 2: Run radar tests and verify RED**

Run:

```bash
cd /home/PyGeoModel
PYTHONPATH=backend pytest backend/tests/test_coverage_task_outputs.py backend/tests/test_task_store.py \
  backend/tests/test_radar_outputs_api.py -q
```

Expected: failures show non-atomic per-file moves, missing live state, missing `410`, and missing rerun route.

- [ ] **Step 3: Migrate radar worker, store, and routes**

In `coverage_task.py`, extract the calculation body into `build_coverage_artifacts(task_id, payload, progress)`. It writes only to a store-created staging directory, calls the supplied progress callback at the current progress points, publishes once, and returns metrics/model/diagnostics/warnings/output descriptors. `run_coverage_task()` remains the task-state wrapper that supplies `mark_running`, then calls `mark_finished` or `mark_failed`. Replace final-directory creation and `_commit_staged_outputs()` with:

```python
store = get_artifact_store()
contract = get_output_contract("radar")
staging_dir = store.create_staging_dir(task_id)
dynamic_specs = tuple(
    ArtifactSpec(
        kind=f"height_{layer_kind}_{_height_filename_token(height)}",
        filename=f"{layer_kind}_h_{_height_filename_token(height)}.geojson",
        media_type="application/geo+json",
        label=f"Radar {layer_kind.title()} Height {height:g} m GeoJSON",
    )
    for height in height_layers
    for layer_kind in ("visible", "blocked")
)
manifest = store.publish(task_id, contract, staging_dir, dynamic_artifacts=dynamic_specs)
output_files = store.list_descriptors(task_id, contract)
```

Write height manifest entries with `visible_kind` and `blocked_kind`, not filenames. Remove all `/outputs/{task_id}` string construction and the radar `_ensure_*`/`_commit_staged_outputs` functions made redundant by `publish()`.

Remove `app.mount("/outputs", StaticFiles(...))` and its import from `backend/app/main.py`. Compatibility clients receive the API route through `download_url`, so staging and uncommitted artifacts are never statically addressable.

In `task_store.py`, add `create_rerun(original_task_id, payload, idempotency_key)` under the task lock. Persist the key in the task-record envelope (not the response schema), return the existing child for a repeated `rerun_of`/key pair, and return `(task, created: bool)` so the API schedules only new work. Continue to call `apply_live_result()` in `get_task()` and `list_tasks()`. Implement deletion so active records still return `409`, missing resources are a successful no-op, task-record and artifact-directory removal are both attempted, and individual filesystem failures are returned in `errors`. In `output_files.py`, keep compatibility function names but delegate to the shared store/contract.

In `radar.py`, use this download behavior and add rerun:

```python
from typing import Annotated

from fastapi import Header


@router.get("/coverage/{task_id}/outputs/{kind}")
def download_coverage_output(task_id: str, kind: str) -> FileResponse:
    task = get_task(task_id)
    path, info = get_artifact_store().resolve_download(
        task_id, kind, get_output_contract("radar"), computation_status=task.status
    )
    return FileResponse(path, media_type=info.media_type, filename=info.filename)


@router.post("/coverage/{task_id}/rerun", response_model=CoverageTaskStatus, status_code=202)
def rerun_coverage_task(
    task_id: str,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> CoverageTaskStatus:
    original = get_task(task_id)
    if original.request is None:
        raise AppError("TASK_REQUEST_UNAVAILABLE", "Saved request is unavailable.", status_code=409)
    read_dem_metadata(original.request.dem_id)
    task, created = create_rerun(original.task_id, original.request, idempotency_key)
    if created:
        background_tasks.add_task(run_coverage_task, task.task_id, original.request)
    return task
```

Wrap `AppError` into the existing FastAPI error response pattern and retain `409` for pending/running downloads.

- [ ] **Step 4: Run the complete radar backend suite**

Run:

```bash
cd /home/PyGeoModel
PYTHONPATH=backend pytest backend/tests/test_output_files.py backend/tests/test_task_store.py \
  backend/tests/test_coverage_task_outputs.py backend/tests/test_radar_outputs_api.py \
  backend/tests/test_coverage_model.py backend/tests/test_radar_volume.py -q
```

Expected: all selected tests pass; no radar worker test observes a partially published directory.

- [ ] **Step 5: Commit radar migration**

Run:

```bash
cd /home/PyGeoModel
git add backend/app/workers/coverage_task.py backend/app/services/task_store.py \
  backend/app/services/output_files.py backend/app/api/radar.py backend/app/main.py \
  backend/tests/test_coverage_task_outputs.py backend/tests/test_task_store.py backend/tests/test_radar_outputs_api.py
git diff --cached --check
git commit -m "feat(radar): publish outputs through artifact store"
```

Expected: radar is the first end-to-end model using the new contract.

---

### Task 4: Migrate UAV, Watchpost, Artillery, Recon Vehicle, Mobility, And Air Corridor

**Files:**
- Modify: `backend/app/workers/uav_recon_task.py`
- Modify: `backend/app/workers/watchpost_task.py`
- Modify: `backend/app/workers/artillery_task.py`
- Modify: `backend/app/workers/recon_vehicle_task.py`
- Modify: `backend/app/workers/mobility_task.py`
- Modify: `backend/app/workers/air_corridor_task.py`
- Modify: `backend/app/services/uav_task_store.py`
- Modify: `backend/app/services/watchpost_task_store.py`
- Modify: `backend/app/services/artillery_task_store.py`
- Modify: `backend/app/services/recon_vehicle_task_store.py`
- Modify: `backend/app/services/mobility_task_store.py`
- Modify: `backend/app/services/air_corridor_task_store.py`
- Modify: `backend/app/services/uav_output_files.py`
- Modify: `backend/app/services/watchpost_output_files.py`
- Modify: `backend/app/services/artillery_output_files.py`
- Modify: `backend/app/services/recon_vehicle_output_files.py`
- Modify: `backend/app/services/mobility_output_files.py`
- Modify: `backend/app/services/air_corridor_output_files.py`
- Modify: `backend/app/api/uav.py`
- Modify: `backend/app/api/watchpost.py`
- Modify: `backend/app/api/artillery.py`
- Modify: `backend/app/api/recon_vehicle.py`
- Modify: `backend/app/api/mobility.py`
- Modify: `backend/app/api/air_corridor.py`
- Modify: `backend/tests/test_uav_api.py`
- Modify: `backend/tests/test_watchpost_api.py`
- Modify: `backend/tests/test_artillery_api.py`
- Modify: `backend/tests/test_recon_vehicle_api.py`
- Modify: `backend/tests/test_mobility_api.py`
- Modify: `backend/tests/test_air_corridor_api.py`
- Modify: `backend/tests/test_air_corridor_task.py`

**Interfaces:**
- Consumes: the Task 3 radar migration pattern and Task 2 contracts.
- Produces: identical live-result, atomic-publish, `410`, retry-safe delete, and explicit rerun behavior for every remaining single-model task family.

- [ ] **Step 1: Add parameterized API contract tests before implementation**

In the six existing API test modules, add one test per model for unavailable output and rerun. Use each exact base route:

```python
MODEL_ROUTES = {
    "uav": "/api/uav/recon",
    "watchpost": "/api/watchpost/detection",
    "artillery": "/api/artillery/coverage",
    "recon_vehicle": "/api/recon-vehicle/coverage",
    "mobility": "/api/mobility/accessibility",
    "air_corridor": "/api/air-corridor/planning",
}
```

For each route, assert a finished record without a manifest returns `result_state=unavailable`, its known output returns `410`, `POST {base}/{task_id}/rerun` with an `Idempotency-Key` returns a different ID with `rerun_of`, retrying the key returns that ID without another background task, a missing key returns `422`, and `GET` never schedules work. Extend each worker test (or its API module when no separate worker test exists) to assert `artifact-manifest.json` exists only after successful completion.

- [ ] **Step 2: Run the six model suites and verify RED**

Run:

```bash
cd /home/PyGeoModel
PYTHONPATH=backend pytest backend/tests/test_uav_api.py backend/tests/test_watchpost_api.py \
  backend/tests/test_artillery_api.py backend/tests/test_recon_vehicle_api.py \
  backend/tests/test_mobility_api.py backend/tests/test_air_corridor_api.py \
  backend/tests/test_air_corridor_task.py -q
```

Expected: new cases fail for missing live state, atomic manifests, `410`, and rerun routes.

- [ ] **Step 3: Apply the same shared-store boundary to every listed model**

Extract these exact state-free builders: `build_uav_artifacts`, `build_watchpost_artifacts`, `build_artillery_artifacts`, `build_recon_vehicle_artifacts`, `build_mobility_artifacts`, and `build_air_corridor_artifacts`. Each has signature `(task_id, payload, progress)` and does not read or write the persisted task record. The existing `run_*_task()` supplies its mark-running callback and remains responsible for computation state. Inside each builder, use this publication sequence with its exact registered model ID (`uav`, `watchpost`, `artillery`, `recon_vehicle`, `mobility`, or `air_corridor`):

```python
store = get_artifact_store()
contract = get_output_contract(model_id)
staging_dir = store.create_staging_dir(task_id)
try:
    store.publish(task_id, contract, staging_dir)
    output_files = store.list_descriptors(task_id, contract)
finally:
    if staging_dir.exists():
        shutil.rmtree(staging_dir, ignore_errors=True)
```

Remove each worker's final-directory `mkdir`, per-file `.replace()`, `_commit_staged_outputs`, and redundant required-file checks. Remove path and URL logic from each `*_output_files.py`, retaining compatibility exports as thin calls into the registered contract/store.

For every task store, add the same locked `create_*_rerun(original_task_id, payload, idempotency_key) -> tuple[Task, bool]`, call `apply_live_result()` after parsing list/detail records, and delete via `ArtifactStore.delete()`. For every API, accept `kind: str`, use `ArtifactStore.resolve_download()`, and add `POST /{task_id}/rerun` that requires the header, validates the saved DEM/request, and schedules the worker only when the store returns `created=True`.

- [ ] **Step 4: Run all single-model backend tests**

Run:

```bash
cd /home/PyGeoModel
PYTHONPATH=backend pytest \
  backend/tests/test_uav_api.py backend/tests/test_watchpost_api.py \
  backend/tests/test_artillery_api.py backend/tests/test_artillery_task.py \
  backend/tests/test_recon_vehicle_api.py backend/tests/test_recon_vehicle_task.py \
  backend/tests/test_mobility_api.py backend/tests/test_mobility_task.py \
  backend/tests/test_air_corridor_api.py backend/tests/test_air_corridor_task.py \
  backend/tests/test_air_corridor_task_store.py -q
```

Expected: all selected tests pass with the shared manifest and state semantics.

- [ ] **Step 5: Commit remaining single-model migration**

Run:

```bash
cd /home/PyGeoModel
git add backend/app/workers/{uav_recon,watchpost,artillery,recon_vehicle,mobility,air_corridor}_task.py \
  backend/app/services/{uav,watchpost,artillery,recon_vehicle,mobility,air_corridor}_{task_store,output_files}.py \
  backend/app/api/{uav,watchpost,artillery,recon_vehicle,mobility,air_corridor}.py \
  backend/tests/test_{uav,watchpost,artillery,recon_vehicle,mobility,air_corridor}_api.py \
  backend/tests/test_{artillery,recon_vehicle,mobility,air_corridor}_task.py backend/tests/test_air_corridor_task_store.py
git diff --cached --check
git commit -m "feat(backend): migrate model outputs to artifact store"
```

Expected: all seven single-model task families now share the artifact contract.

---

### Task 5: Multi-Radar Artifact Contract And API

**Files:**
- Modify: `backend/app/workers/multi_radar_coverage_task.py`
- Modify: `backend/app/services/multi_radar_task_store.py`
- Modify: `backend/app/api/radar.py`
- Modify: `backend/tests/test_multi_radar_coverage_task.py`
- Modify: `backend/tests/test_multi_radar_task_store.py`
- Modify: `backend/tests/test_multi_radar_api.py`

**Interfaces:**
- Consumes: `get_output_contract("multi_radar")` and shared store/result helpers.
- Produces: multi-radar live `output_files`, canonical output list/download routes, optional scene artifacts, explicit rerun, and atomic aggregate publication.

- [ ] **Step 1: Write failing multi-radar artifact tests**

Add assertions that a successful aggregate has one final directory with a manifest; required non-public `station_masks.npz` and `grid.json` appear in the manifest but not `output_files`; the fusion and cooperative GLBs are optional and listed only when generated; a partial station result can still be `result_state=ready`; a missing completed result becomes unavailable; downloads return `410`; and rerun creates a linked task.

```python
assert stored.status in {"finished", "partial"}
assert stored.result_state == "ready"
assert {item.kind for item in stored.output_files} >= {
    "visible_union_geojson", "overlap_geojson", "blind_geojson",
    "coverage_count_geojson", "stations_geojson", "station_summaries_json",
}
assert all(item.download_path.startswith("/api/radar/multi-coverage/") for item in stored.output_files)
```

- [ ] **Step 2: Run multi-radar tests and verify RED**

Run:

```bash
cd /home/PyGeoModel
PYTHONPATH=backend pytest backend/tests/test_multi_radar_coverage_task.py \
  backend/tests/test_multi_radar_task_store.py backend/tests/test_multi_radar_api.py -q
```

Expected: failures expose current direct `/outputs` strings, per-file moves, and absent artifact routes.

- [ ] **Step 3: Publish multi-radar output as one directory and expose descriptors**

Extract `build_multi_radar_artifacts(task_id, payload, progress, evaluator=None)` so the computation does not update the persisted parent task. Have `_write_aggregate_outputs()` write every file under the store-created sibling staging directory and return model metadata only. `run_multi_radar_coverage_task()` remains the state wrapper. Call `publish()` once after all station aggregation and optional GLB generation. Build legacy `MultiRadarOutputs` values from descriptor `download_path` for compatibility, but make `output_files` canonical. Add:

```python
@router.get("/multi-coverage/{task_id}/outputs", response_model=list[ArtifactDescriptor])
def list_multi_outputs(task_id: str) -> list[ArtifactDescriptor]:
    return get_multi_task(task_id).output_files


@router.get("/multi-coverage/{task_id}/outputs/{kind}")
def download_multi_output(task_id: str, kind: str) -> FileResponse:
    task = get_multi_task(task_id)
    path, info = get_artifact_store().resolve_download(
        task_id, kind, get_output_contract("multi_radar"), computation_status=task.status
    )
    return FileResponse(path, media_type=info.media_type, filename=info.filename)
```

Treat both `finished` and `partial` as completed computation states in `ArtifactStore.inspect()`. Add `rerun_of`, atomic task-record writes, live hydration, retry-safe deletion, and an idempotent `POST /multi-coverage/{task_id}/rerun` with the same required header/store contract.

- [ ] **Step 4: Run multi-radar suites and verify GREEN**

Run:

```bash
cd /home/PyGeoModel
PYTHONPATH=backend pytest backend/tests/test_multi_radar_coverage_task.py \
  backend/tests/test_multi_radar_task_store.py backend/tests/test_multi_radar_api.py \
  backend/tests/test_multi_radar_coverage.py backend/tests/test_multi_radar_fusion_volume.py -q
```

Expected: all tests pass; both aggregate modes have valid manifests and API download paths.

- [ ] **Step 5: Commit multi-radar migration**

Run:

```bash
cd /home/PyGeoModel
git add backend/app/workers/multi_radar_coverage_task.py backend/app/services/multi_radar_task_store.py \
  backend/app/api/radar.py backend/tests/test_multi_radar_coverage_task.py \
  backend/tests/test_multi_radar_task_store.py backend/tests/test_multi_radar_api.py
git diff --cached --check
git commit -m "feat(radar): add multi-radar artifact contract"
```

Expected: multi-radar no longer bypasses shared artifact delivery.

---

### Task 6: Portable Frontend Runtime Configuration And URL Resolver

**Files:**
- Create: `frontend/src/config/runtime.ts`
- Create: `frontend/src/config/runtime.test.ts`
- Modify: `frontend/src/api/http.ts`
- Modify: `frontend/src/api/http.test.ts`
- Create: `frontend/docker/write-runtime-config.mjs`
- Create: `frontend/docker/server.mjs`
- Modify: `frontend/index.html`
- Modify: `frontend/vite.config.ts`
- Modify: `frontend/Dockerfile`

**Interfaces:**
- Produces: `window.__PYGEOMODEL_RUNTIME_CONFIG__`, `getRuntimeConfig()`, `resolveApiUrl(path)`, `requestJson()`, `requestResponse()`, and `requestGeoJson()`.
- Contract: runtime `apiBaseUrl` wins over `VITE_API_BASE`; the base never ends in `/`; path arguments must begin with `/api/`.

- [ ] **Step 1: Write failing root, subpath, absolute-origin, precedence, and escaping tests**

Create `frontend/src/config/runtime.test.ts` and extend `frontend/src/api/http.test.ts`:

```ts
it.each([
  ["", "/api/health", "/api/health"],
  ["/PyGeoModel/", "/api/health", "/PyGeoModel/api/health"],
  ["http://124.221.208.30:8000/", "/api/health", "http://124.221.208.30:8000/api/health"]
])("resolves API base %s", (base, path, expected) => {
  expect(resolveApiUrl(path, { apiBaseUrl: base })).toBe(expected);
});

it("prefers runtime config over the build fallback", () => {
  expect(resolveApiUrl("/api/health", { apiBaseUrl: "/runtime" }, "/build")).toBe("/runtime/api/health");
});

it("rejects a base containing query, fragment, credentials, or an /api suffix", () => {
  for (const base of [
    "/root?x=1", "/root#x", "https://u:p@example.com", "/PyGeoModel/api",
    "javascript:alert(1)", "//other.example/api-root", "api-root"
  ]) {
    expect(() => normalizeApiBase(base)).toThrow();
  }
});
```

Add a Node test invocation for `write-runtime-config.mjs` with a value containing quotes and `</script>`, then parse the generated assignment in a VM and assert the exact string round-trips without code execution.

- [ ] **Step 2: Run focused frontend tests and verify RED**

Run:

```bash
cd /home/PyGeoModel/frontend
npm test -- --run src/config/runtime.test.ts src/api/http.test.ts
```

Expected: failures because runtime configuration and `resolveApiUrl` do not exist.

- [ ] **Step 3: Implement runtime validation, unified requests, and portable static server**

Create `frontend/src/config/runtime.ts`:

```ts
export interface RuntimeConfig { apiBaseUrl: string }

declare global {
  interface Window { __PYGEOMODEL_RUNTIME_CONFIG__?: Partial<RuntimeConfig> }
}

export function normalizeApiBase(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  if (!trimmed.startsWith("/") && !/^https?:\/\//.test(trimmed)) throw new Error("Invalid API base URL");
  if (trimmed.startsWith("//")) throw new Error("Protocol-relative API bases are not supported");
  const parsed = new URL(trimmed, window.location.origin);
  if (parsed.username || parsed.password || parsed.search || parsed.hash) throw new Error("Invalid API base URL");
  const pathname = parsed.pathname.replace(/\/+$/, "");
  if (pathname.endsWith("/api")) throw new Error("PYGEOMODEL_API_BASE_URL must exclude /api");
  return /^https?:\/\//.test(trimmed) ? `${parsed.origin}${pathname}` : pathname;
}

export function getRuntimeConfig(): RuntimeConfig {
  return { apiBaseUrl: normalizeApiBase(
    window.__PYGEOMODEL_RUNTIME_CONFIG__?.apiBaseUrl ?? import.meta.env.VITE_API_BASE ?? ""
  ) };
}
```

Refactor `http.ts` so every request calls `resolveApiUrl(path)`. `resolveApiUrl` rejects non-API paths, preserves `{x}/{y}/{z}` in map templates, and uses `new URL()` only for absolute bases. `requestResponse` handles non-JSON payloads; `requestGeoJson<T>()` calls `requestResponse` then parses JSON. Retain `resolveAssetUrl` as a deprecated wrapper that delegates only for `/api/` paths and throws for `/outputs/`.

Add `<script src="./runtime-config.js"></script>` before the module in `index.html`, set Vite `base: "./"`, and create `write-runtime-config.mjs` using `JSON.stringify({ apiBaseUrl: process.env.PYGEOMODEL_API_BASE_URL ?? "" })`. Create `server.mjs` to serve `/app/dist`, return SPA `index.html` for navigation, and send `Cache-Control: no-store` specifically for `runtime-config.js`. Change the final Docker command to run the config writer then the server on port 5173.

- [ ] **Step 4: Run tests and production build**

Run:

```bash
cd /home/PyGeoModel/frontend
npm test -- --run src/config/runtime.test.ts src/api/http.test.ts
npm run build
PYGEOMODEL_API_BASE_URL='/PyGeoModel"</script><script>bad()</script>' node docker/write-runtime-config.mjs /tmp/pygeomodel-runtime-config.js
node --check /tmp/pygeomodel-runtime-config.js
```

Expected: tests and build pass; generated configuration is syntactically valid and contains only a JSON string value, not executable injected markup.

- [ ] **Step 5: Commit runtime configuration**

Run:

```bash
cd /home/PyGeoModel
git add frontend/src/config/runtime.ts frontend/src/config/runtime.test.ts frontend/src/api/http.ts \
  frontend/src/api/http.test.ts frontend/docker/write-runtime-config.mjs frontend/docker/server.mjs \
  frontend/index.html frontend/vite.config.ts frontend/Dockerfile
git diff --cached --check
git commit -m "feat(frontend): resolve API paths at container runtime"
```

Expected: one frontend image can select root, subpath, or absolute backend API base when the container starts.

---

### Task 7: Frontend Live Artifact Flow And Legacy Fallback Removal

**Files:**
- Modify: `frontend/src/models/shared.ts`
- Modify: `frontend/src/api/tasks.ts`
- Modify: `frontend/src/composables/useMapWorkspace.ts`
- Modify: `frontend/src/composables/useMapWorkspace.test.ts`
- Modify: `frontend/src/models/radar/layerAdapter.ts`
- Modify: `frontend/src/models/radar/layerAdapter.test.ts`
- Modify: `frontend/src/models/radar/heightLayerLoader.ts`
- Modify: `frontend/src/models/radar/heightLayerLoader.test.ts`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/api/multiRadar.ts`
- Modify: `frontend/src/models/multiRadar/types.ts`
- Modify: `frontend/src/models/multiRadar/fusionScene.ts`
- Modify: `frontend/src/models/multiRadar/fusionScene.test.ts`
- Modify: `frontend/src/models/multiRadar/cooperativeScene.ts`
- Modify: `frontend/src/models/multiRadar/cooperativeScene.test.ts`
- Modify: `frontend/src/components/tasks/TaskResultPanel.vue`
- Modify: `frontend/src/components/tasks/TaskResultPanel.test.ts`

**Interfaces:**
- Consumes: `TaskSummary.result_state`, live `OutputFile.download_path`, and Task 6 `resolveApiUrl/requestGeoJson`.
- Produces: no output request unless state is `ready`; no fallback to `task.outputs`, `url`, or `download_url`; explicit rerun UI action.

- [ ] **Step 1: Write failing data-flow tests**

Change test fixtures to the canonical shape:

```ts
const readyFile: OutputFile = {
  kind: "visible_geojson",
  label: "Visible coverage",
  filename: "visible.geojson",
  media_type: "application/geo+json",
  required: true,
  exists: true,
  size_bytes: 42,
  download_path: "/api/uav/recon/task-ready/outputs/visible_geojson"
};
```

Add cases proving: `pending` and `unavailable` tasks call neither metrics nor outputs; `ready` fetches only descriptors with `exists=true` and `download_path`; an output-list rejection creates an explicit loading error and never reads legacy `task.outputs`; GeoJSON and GLB URLs pass through `resolveApiUrl`; radar plan ignores legacy `url/download_url`; height manifests map `visible_kind/blocked_kind` through the live descriptor map; and multi-radar reads its live descriptor list instead of raw output strings.

Add `TaskResultPanel` tests for an unavailable reason and an emitted `rerun` command, with no automatic API call on mount.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
cd /home/PyGeoModel/frontend
npm test -- --run src/composables/useMapWorkspace.test.ts src/models/radar/layerAdapter.test.ts \
  src/models/radar/heightLayerLoader.test.ts src/models/multiRadar/fusionScene.test.ts \
  src/models/multiRadar/cooperativeScene.test.ts src/components/tasks/TaskResultPanel.test.ts
```

Expected: tests fail because current code gates on `status=finished`, accepts legacy URLs, and multi-radar uses `task.outputs`.

- [ ] **Step 3: Enforce the canonical descriptor flow**

Update shared types:

```ts
export type ResultState = "pending" | "ready" | "unavailable";
export interface OutputFile {
  kind: string; label: string; filename: string; media_type: string; required: boolean;
  size_bytes?: number | null; exists: boolean; download_path?: string | null;
  url?: string | null; download_url?: string | null;
}
export interface TaskSummary<Req extends BaseModelRequest = BaseModelRequest, Metrics = Record<string, unknown>, Model = Record<string, unknown>, Diagnostics = Record<string, unknown>> {
  task_id: string;
  dem_id?: string | null;
  status: TaskStatus;
  result_state: ResultState;
  result_reason_code?: string | null;
  rerun_of?: string | null;
  progress: number;
  message: string;
  created_at?: string | null;
  updated_at?: string | null;
  request?: Req | null;
  metrics?: Metrics | null;
  outputs?: Record<string, string | null> | null;
  model?: Model | null;
  diagnostics?: Diagnostics | null;
  output_files: OutputFile[];
  warnings: string[];
}
```

Add `rerun(taskId, idempotencyKey = crypto.randomUUID())` to `createTaskClient`, sending the value in the `Idempotency-Key` header. Keep one generated key for the duration of one user rerun action so a network retry reuses it; a later click generates a new key. In `useMapWorkspace.loadTaskOutputs`, return before API calls unless `result_state === "ready"`; when ready, require the output-list request to succeed, filter `exists && download_path`, and resolve each path through `resolveApiUrl`. Delete `resolveLayerUrl(..., task.outputs)`, `taskFiles()` legacy fallback, and every `file.download_url || file.url` branch.

In `layerAdapter`, require ready state and map only `download_path`. Change the height manifest type to `visible_kind`/`blocked_kind`, and look up both in `plan.outputUrls`. In `App.vue`, replace local `fetchJson` and `resolveRelativeUrl`, fetch multi-radar `output_files`, and use canonical descriptors for aggregate GeoJSON and optional GLBs. Remove synthetic fusion/cooperative output descriptors or change their helpers to consume an actual `OutputFile` without constructing URLs.

Wire the result panel rerun command to `taskClient.rerun`, insert the new pending task in history, and leave the selected historical record intact until the user selects the rerun.

- [ ] **Step 4: Run all artifact consumer tests and build**

Run:

```bash
cd /home/PyGeoModel/frontend
npm test -- --run src/api src/composables/useMapWorkspace.test.ts src/models/radar \
  src/models/multiRadar src/components/tasks/TaskResultPanel.test.ts
npm run build
if rg -n '(/outputs/|download_url\s*\|\||\.url\s*\|\||resolveRelativeUrl)' \
  dist/assets src/composables src/models src/App.vue \
  --glob '*.js' --glob '*.ts' --glob '*.vue' --glob '!*.test.ts'; then
  exit 1
fi
```

Expected: tests/build pass; the final `rg` has no artifact-loading fallback match in application source or built assets.

- [ ] **Step 5: Commit frontend artifact migration**

Run:

```bash
cd /home/PyGeoModel
git add frontend/src/models/shared.ts frontend/src/api/tasks.ts frontend/src/api/multiRadar.ts \
  frontend/src/composables/useMapWorkspace.ts frontend/src/composables/useMapWorkspace.test.ts \
  frontend/src/models/radar frontend/src/models/multiRadar frontend/src/App.vue \
  frontend/src/components/tasks/TaskResultPanel.vue frontend/src/components/tasks/TaskResultPanel.test.ts
git diff --cached --check
git commit -m "fix(frontend): load only live API artifacts"
```

Expected: task switching can no longer issue stale raw `/outputs` requests.

---

### Task 8: Backend-Owned TianDiTu Proxy

**Files:**
- Modify: `backend/app/core/config.py`
- Create: `backend/app/services/tianditu.py`
- Create: `backend/app/api/tianditu.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_tianditu_api.py`
- Modify: `frontend/src/map/tiandituStyle.ts`
- Modify: `frontend/src/map/tiandituStyle.test.ts`

**Interfaces:**
- Consumes: `PYGEOMODEL_TIANDITU_TOKEN` and frontend `resolveMapAssetUrl` backed by the runtime API base.
- Produces: `GET /api/map/tianditu/{node}/wmts` with strict WMTS allowlisting and bounded caching.

- [ ] **Step 1: Write failing proxy allowlist, secrecy, upstream error, and style tests**

Create backend tests with `httpx.MockTransport` asserting nodes are exactly `t0` through `t7`; operations are exactly `GetTile`; layers are `vec` or `cva`; matrix set is `w`; numeric matrix/row/column values are non-negative integers; client `tk` is ignored; the server token is sent upstream; `401/403` maps to `502 TIANDITU_UPSTREAM_AUTH_FAILED`; no response/log/detail contains the token; successful content type and bytes pass through; and cache control is `public, max-age=86400`. Assert `/api/health` remains `200` when TianDiTu is unavailable and reports the integration separately as `configured`, `available`, or `unavailable` without including credentials.

Update the style test expectation to:

```ts
window.__PYGEOMODEL_RUNTIME_CONFIG__ = { apiBaseUrl: "http://localhost:8000" };
const style = createTiandituStyle();
expect(style.sources.tianditu_vector.tiles[0]).toBe(
  "http://localhost:8000/api/map/tianditu/t0/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=vec&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}"
);
expect(JSON.stringify(style)).not.toContain("tk=");
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
cd /home/PyGeoModel
PYTHONPATH=backend pytest backend/tests/test_tianditu_api.py -q
cd frontend
npm test -- --run src/map/tiandituStyle.test.ts
```

Expected: backend route is missing and the frontend still emits `/PyGeoModel/tianditu`.

- [ ] **Step 3: Implement validated forwarding and switch the tile style**

Add `tianditu_token: SecretStr | None = None` and strict origin validation to `Settings`. The proxy service must build only this upstream URL shape:

```python
upstream = f"https://{node}.tianditu.gov.cn/{layer}_w/wmts"
params = {
    "SERVICE": "WMTS", "REQUEST": "GetTile", "VERSION": "1.0.0",
    "LAYER": layer, "STYLE": "default", "TILEMATRIXSET": "w", "FORMAT": "tiles",
    "TILEMATRIX": tile_matrix, "TILEROW": tile_row, "TILECOL": tile_col,
    "tk": settings.tianditu_token.get_secret_value(),
}
```

Reject absent server token with `503 TIANDITU_NOT_CONFIGURED`. Forward only controlled upstream headers (`User-Agent`, `Referer` when configured), use a finite connect/read timeout, and never log params. Include the router in `main.py` under `/api/map`. Keep process health independent from the optional upstream and return a separate `integrations.tianditu` status from `/api/health`.

In `tiandituStyle.ts`, create templates with `resolveMapAssetUrl("/api/map/tianditu/.../wmts?...{z}...")`; remove `tileProxyVersion`, hardcoded `/PyGeoModel`, and all Nginx-specific tile paths.

- [ ] **Step 4: Run proxy tests, frontend tests, and token scans**

Run:

```bash
cd /home/PyGeoModel
PYTHONPATH=backend pytest backend/tests/test_tianditu_api.py -q
cd frontend
npm test -- --run src/map/tiandituStyle.test.ts src/api/http.test.ts
npm run build
cd ..
if rg -n 'tianditu\.gov\.cn|[?&]tk=|PYGEOMODEL_TIANDITU_TOKEN' frontend/dist frontend/src; then
  exit 1
fi
```

Expected: tests/build pass; scan finds no upstream hostname, `tk=`, or server token variable in frontend source/bundle.

- [ ] **Step 5: Commit backend-owned TianDiTu proxy**

Run:

```bash
cd /home/PyGeoModel
git add backend/app/core/config.py backend/app/services/tianditu.py backend/app/api/tianditu.py \
  backend/app/main.py backend/tests/test_tianditu_api.py \
  frontend/src/map/tiandituStyle.ts frontend/src/map/tiandituStyle.test.ts
git diff --cached --check
git commit -m "feat(map): proxy TianDiTu through backend API"
```

Expected: TianDiTu works with or without host Nginx and the token stays server-side.

---

### Task 9: Reconciliation CLI And Explicit Selected Repair

**Files:**
- Create: `backend/app/services/reconciliation.py`
- Create: `scripts/reconcile_artifacts.py`
- Create: `backend/tests/test_artifact_reconciliation.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: all registered contracts/stores, saved task requests, DEM lookup, and model worker functions.
- Produces: default dry-run report, `--upgrade-legacy`, and explicit `--repair --model MODEL --task-id TASK_ID`.

- [ ] **Step 1: Write failing dry-run, legacy-upgrade, selection, and no-auto-repair tests**

Create fixtures for ready, missing, incomplete, checksum-corrupt, complete legacy, missing-request, and missing-DEM records. Assert default invocation changes no files; `--upgrade-legacy` only writes manifests for complete legacy directories; `--repair` without both model and task ID exits `2`; a selected eligible repair calls exactly one worker; an unselected task never runs; startup only removes sibling staging directories older than 24 hours and never repairs results.

```python
report = reconcile_all(dry_run=True, verify_checksums=True)
assert {item.reason_code for item in report} >= {
    "ARTIFACT_DIRECTORY_MISSING", "ARTIFACT_REQUIRED_FILE_MISSING", "ARTIFACT_CHECKSUM_MISMATCH",
}
assert worker.call_count == 0
```

- [ ] **Step 2: Run reconciliation tests and verify RED**

Run:

```bash
cd /home/PyGeoModel
PYTHONPATH=backend pytest backend/tests/test_artifact_reconciliation.py -q
```

Expected: reconciliation service and CLI do not exist.

- [ ] **Step 3: Implement a registry-driven administrative command**

Define a model adapter registry in `reconciliation.py` containing task glob, request parser, DEM ID accessor, and one exact builder from Tasks 3-5: `build_coverage_artifacts`, `build_uav_artifacts`, `build_watchpost_artifacts`, `build_artillery_artifacts`, `build_recon_vehicle_artifacts`, `build_mobility_artifacts`, `build_air_corridor_artifacts`, or `build_multi_radar_artifacts`. `reconcile_all()` calls `ArtifactStore.reconcile(..., verify_checksums=True)` and classifies repair eligibility without scheduling. `repair_selected(model_id, task_ids)` validates the saved request and DEM, requires the final artifact directory to be absent, then invokes the registered builder synchronously with a no-op progress callback so CLI exit status reflects success. It publishes artifacts under the selected historical task ID but does not rewrite that task's request, metrics, computation status, timestamps, or identity; normal live hydration makes the record ready immediately after publication.

Implement exact CLI arguments:

```python
parser.add_argument("--verify-checksums", action="store_true")
parser.add_argument("--upgrade-legacy", action="store_true")
parser.add_argument("--repair", action="store_true")
parser.add_argument("--model", choices=sorted(OUTPUT_CONTRACTS))
parser.add_argument("--task-id", action="append", default=[])
parser.add_argument("--json", action="store_true")
```

Default output is dry-run. Require `--model` and at least one `--task-id` with `--repair`. Print task IDs, states, reason codes, eligibility, and repaired task IDs only; never print request payloads, environment variables, tokens, or upstream URLs. Add startup cleanup for stale sibling staging directories without deleting final task directories.

- [ ] **Step 4: Run reconciliation and CLI tests**

Run:

```bash
cd /home/PyGeoModel
PYTHONPATH=backend pytest backend/tests/test_artifact_reconciliation.py -q
PYTHONPATH=backend python scripts/reconcile_artifacts.py --help
```

Expected: tests pass and help lists dry-run, checksum, legacy upgrade, and selected repair controls.

- [ ] **Step 5: Commit reconciliation tooling**

Run:

```bash
cd /home/PyGeoModel
git add backend/app/services/reconciliation.py scripts/reconcile_artifacts.py \
  backend/tests/test_artifact_reconciliation.py backend/app/main.py
git diff --cached --check
git commit -m "feat(ops): add artifact reconciliation command"
```

Expected: operators can inspect and explicitly repair selected results without read-path recomputation.

---

### Task 10: Direct-Port, Root, And Optional Nginx Deployment

**Files:**
- Modify: `docker-compose.yml`
- Modify: `frontend/.env.example`
- Create: `.env.example`
- Create: `deploy/nginx/pygeomodel.conf.example`
- Create: `docs/deployment.md`
- Create: `scripts/verify_deployment.py`
- Create: `backend/tests/test_deployment_config.py`

**Interfaces:**
- Consumes: `PYGEOMODEL_API_BASE_URL`, `PYGEOMODEL_CORS_ORIGINS`, and `PYGEOMODEL_TIANDITU_TOKEN`.
- Produces: one compose image set usable behind `/PyGeoModel` or directly on ports 5173/8000 without rebuild.

- [ ] **Step 1: Write failing configuration and smoke-verifier tests**

Add tests that parse compose YAML/text and assert frontend runtime env uses `PYGEOMODEL_API_BASE_URL`, backend exposes configurable CORS/token settings, frontend build args contain only map-engine selection, no `VITE_API_BASE` build arg exists, and the Nginx example has only generic frontend and `/api/` proxy locations with no `/outputs` or `/tianditu` business routes.

Test `scripts/verify_deployment.py` against a fake HTTP transport for root, subpath, and absolute API base. It must check health, runtime config, one task detail/output descriptor, descriptor download, and one TianDiTu tile while redacting query strings.

- [ ] **Step 2: Run deployment tests and verify RED**

Run:

```bash
cd /home/PyGeoModel
PYTHONPATH=backend pytest backend/tests/test_deployment_config.py -q
```

Expected: failure because compose still uses Vite-time API settings and deployment artifacts are absent.

- [ ] **Step 3: Add portable compose, optional Nginx, and operator documentation**

Change compose environment to:

```yaml
backend:
  environment:
    PYGEOMODEL_DATA_DIR: /workspace/data
    PYGEOMODEL_CORS_ORIGINS: ${PYGEOMODEL_CORS_ORIGINS:-["http://localhost:5173","http://127.0.0.1:5173"]}
    PYGEOMODEL_TIANDITU_TOKEN: ${PYGEOMODEL_TIANDITU_TOKEN:-}
  ports:
    - "${PYGEOMODEL_BACKEND_BIND:-127.0.0.1}:8000:8000"
frontend:
  build:
    args:
      VITE_MAP_ENGINE: ${VITE_MAP_ENGINE:-maplibre}
      VITE_MAPBOX_ACCESS_TOKEN: ${VITE_MAPBOX_ACCESS_TOKEN:-}
  environment:
    PYGEOMODEL_API_BASE_URL: ${PYGEOMODEL_API_BASE_URL:-/PyGeoModel}
  ports:
    - "${PYGEOMODEL_FRONTEND_BIND:-127.0.0.1}:5173:5173"
```

The Nginx example proxies `/PyGeoModel/api/` to backend `/api/` and all other `/PyGeoModel/` traffic to frontend, preserving WebSocket-compatible headers but defining no output/tile-specific location. Document three exact modes:

```bash
# Optional Nginx subpath
PYGEOMODEL_API_BASE_URL=/PyGeoModel docker compose up -d --build

# Direct frontend/backend ports
PYGEOMODEL_API_BASE_URL=http://124.221.208.30:8000 \
PYGEOMODEL_CORS_ORIGINS='["http://124.221.208.30:5173"]' \
PYGEOMODEL_BACKEND_BIND=0.0.0.0 PYGEOMODEL_FRONTEND_BIND=0.0.0.0 \
docker compose up -d --build

# Same-origin root edge proxy
PYGEOMODEL_API_BASE_URL= docker compose up -d --build
```

Explain that changing only `PYGEOMODEL_API_BASE_URL`, CORS origins, or TianDiTu token requires container recreation, not image rebuild; changing map renderer still requires frontend rebuild. The verifier accepts `--frontend-url`, `--api-base-url`, and optional `--task-id`, and never prints response query strings or secret values.

- [ ] **Step 4: Validate configuration without exposing secrets**

Run:

```bash
cd /home/PyGeoModel
PYTHONPATH=backend pytest backend/tests/test_deployment_config.py -q
docker compose config --quiet
PYTHONPATH=backend python scripts/verify_deployment.py --help
```

Expected: tests pass, compose resolves, and verifier help documents both Nginx and direct-port use.

- [ ] **Step 5: Commit portable deployment configuration**

Run:

```bash
cd /home/PyGeoModel
git add docker-compose.yml frontend/.env.example .env.example deploy/nginx/pygeomodel.conf.example \
  docs/deployment.md scripts/verify_deployment.py backend/tests/test_deployment_config.py
git diff --cached --check
git commit -m "build: support proxy-free runtime deployment"
```

Expected: deployment configuration contains no credential values and no artifact business routing in Nginx.

---

### Task 11: Full Regression And Two-Mode Integration Verification

**Files:**
- Modify only if a test exposes an in-scope regression: files already listed in Tasks 1-10.

**Interfaces:**
- Consumes: completed backend, frontend, and deployment changes.
- Produces: evidence that Nginx subpath and direct cross-origin modes use identical artifact and tile contracts.

- [ ] **Step 1: Run the complete backend suite**

Run:

```bash
cd /home/PyGeoModel
PYTHONPATH=backend pytest backend/tests -q
```

Expected: all backend tests pass.

- [ ] **Step 2: Run the complete frontend suite and build**

Run:

```bash
cd /home/PyGeoModel/frontend
npm test -- --run
npm run build
```

Expected: all frontend tests pass and Vite production build exits 0.

- [ ] **Step 3: Scan the built client for forbidden routing and credentials**

Run:

```bash
cd /home/PyGeoModel
if rg -n '(/outputs/|/PyGeoModel/tianditu|tianditu\.gov\.cn|[?&]tk=|PYGEOMODEL_TIANDITU_TOKEN)' frontend/dist; then
  exit 1
fi
```

Expected: no matches. Do not search for or print actual secret values.

- [ ] **Step 4: Build containers and verify both deployment modes**

Run the Nginx-subpath deployment first:

```bash
cd /home/PyGeoModel
docker compose build
docker compose up -d --force-recreate
PYTHONPATH=backend python scripts/verify_deployment.py \
  --frontend-url http://124.221.208.30/PyGeoModel/ \
  --api-base-url http://124.221.208.30/PyGeoModel
```

Then recreate the same images in direct mode without rebuilding:

```bash
cd /home/PyGeoModel
PYGEOMODEL_API_BASE_URL=http://124.221.208.30:8000 \
PYGEOMODEL_CORS_ORIGINS='["http://124.221.208.30:5173"]' \
PYGEOMODEL_BACKEND_BIND=0.0.0.0 PYGEOMODEL_FRONTEND_BIND=0.0.0.0 \
docker compose up -d --force-recreate
PYTHONPATH=backend python scripts/verify_deployment.py \
  --frontend-url http://124.221.208.30:5173/ \
  --api-base-url http://124.221.208.30:8000
```

Expected: health, runtime config, live descriptor download, and TianDiTu tile checks pass in both modes; switching between ready and unavailable history entries produces no raw `/outputs` requests. Restore the Nginx-subpath environment after this check so Task 12 deploys the intended public topology.

- [ ] **Step 5: Commit only test-driven corrections, if any**

Run:

```bash
cd /home/PyGeoModel
git status --short
git diff --check
```

Expected: clean worktree. If verification required an in-scope correction, stage only that correction and its regression test, rerun the failing command, and commit with `fix: close artifact delivery regression` before proceeding.

---

### Task 12: Production Dry-Run, Selected Historical Repair, And Rollout

**Files:**
- No repository file changes expected.
- Production data: Docker-mounted `/workspace/data/tasks` and `/workspace/data/outputs`, accessed through the backend container.

**Interfaces:**
- Consumes: reconciliation CLI, verified images, restored DEM records, and the seven explicitly selected historical radar task IDs.
- Produces: valid manifests and restored live artifacts for the seven selected historical task IDs without changing their task records.

- [x] **Step 1: Deploy the verified image on loopback and confirm the migration command is present**

Recreate the intended Nginx-subpath topology before touching data. The TianDiTu token is supplied through the existing protected environment and is not echoed:

```bash
cd /home/PyGeoModel
PYGEOMODEL_API_BASE_URL=/PyGeoModel \
PYGEOMODEL_BACKEND_BIND=127.0.0.1 PYGEOMODEL_FRONTEND_BIND=127.0.0.1 \
docker compose up -d --build --force-recreate
docker compose ps
curl -fsS http://127.0.0.1:8000/api/health
docker compose exec -T backend python /app/scripts/reconcile_artifacts.py --help >/dev/null
```

Expected: both containers are running on loopback, API process health is `ok`, and the new container contains the reconciliation command.

- [x] **Step 2: Capture dry-run state and upgrade only complete legacy directories**

Run commands through the backend container because the daemon-mounted data path may differ from the shell-visible host path:

```bash
cd /home/PyGeoModel
docker compose exec -T backend sh -lc 'df -h /workspace/data && du -sh /workspace/data/outputs'
docker compose exec -T backend python /app/scripts/reconcile_artifacts.py --verify-checksums --json \
  > /tmp/pygeomodel-artifact-dry-run.json
jq '{counts: (group_by(.state) | map({key: .[0].state, value: length}) | from_entries), unavailable: [.[] | select(.state == "unavailable") | {task_id, model_id, reason_code, action}]}' \
  /tmp/pygeomodel-artifact-dry-run.json
docker compose exec -T backend python /app/scripts/reconcile_artifacts.py \
  --verify-checksums --upgrade-legacy --json > /tmp/pygeomodel-artifact-upgrade.json
```

Expected: available capacity is reviewed before recomputation; `task_20260629_134237_25ff1d8b` is ready or upgraded; the seven missing radar tasks are unavailable/repair-eligible; complete legacy directories gain schema-v1 manifests; no missing task is recomputed and no task record timestamp changes.

- [x] **Step 3: Repair exactly the seven reviewed historical radar task IDs**

Pass the IDs confirmed by the container inventory and dry-run report explicitly; do not derive the selection from every unavailable task:

```bash
cd /home/PyGeoModel
docker compose exec -T backend python /app/scripts/reconcile_artifacts.py \
  --repair --model radar \
  --task-id task_20260629_114439_577ceaec \
  --task-id task_20260629_122700_df024c14 \
  --task-id task_20260629_134207_3e0b3b22 \
  --task-id task_20260630_012713_2080f5b5 \
  --task-id task_20260630_014542_87cae348 \
  --task-id task_20260630_020135_2aa88e64 \
  --task-id task_20260713_095035_4da417ae \
  --json > /tmp/pygeomodel-artifact-repair.json
```

Expected: each selected historical task directory is atomically restored with `artifact-manifest.json`; its existing task record, request, metrics, status, timestamps, and ID remain unchanged; live detail reports `result_state=ready`. Never use a wildcard or an automatically generated all-unavailable list.

- [x] **Step 4: Replace the host Nginx configuration and run public smoke checks**

Back up the active site, install the tested generic edge configuration, validate it before reload, and restore the backup if validation fails:

```bash
cd /home/PyGeoModel
sudo cp /etc/nginx/sites-available/gsms /tmp/pygeomodel-gsms.before-artifact-rollout.conf
sudo install -m 0644 deploy/nginx/pygeomodel.conf.example /etc/nginx/sites-available/gsms
if ! sudo nginx -t; then
  sudo install -m 0644 /tmp/pygeomodel-gsms.before-artifact-rollout.conf /etc/nginx/sites-available/gsms
  exit 1
fi
sudo systemctl reload nginx
PYTHONPATH=backend python scripts/verify_deployment.py \
  --frontend-url http://124.221.208.30/PyGeoModel/ \
  --api-base-url http://124.221.208.30/PyGeoModel
```

Expected: public artifact downloads return `200`, invalid/unknown kinds retain controlled `404`, and TianDiTu tiles return image content without browser-side credentials. The Nginx site has no `/outputs` or TianDiTu-specific location.

- [x] **Step 5: Confirm post-rollout invariants and retain a host-local audit**

Run:

```bash
cd /home/PyGeoModel
docker compose exec -T backend python /app/scripts/reconcile_artifacts.py --verify-checksums --json \
  > /tmp/pygeomodel-artifact-post-rollout.json
jq '[.[] | select(.model_id == "radar") | {task_id, state, reason_code}]' \
  /tmp/pygeomodel-artifact-post-rollout.json
git status --short
```

Expected: all eight historical radar tasks are ready, no sibling staging directory is left behind, and the Git worktree is clean. Keep the three `/tmp/pygeomodel-artifact-*.json` files and the Nginx backup as host-local rollout audit/recovery files; none contains a token.
