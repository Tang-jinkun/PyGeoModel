# Independent Model Demo Scenarios Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在札达县 DEM 上为六个非雷达模型生成可复现的独立合成场景，通过现有 API 完成真实计算，并把可复用的成功任务写入场景索引。

**Architecture:** `backend/app/demo_scenarios` 提供确定性 DEM 采样、场景构建、请求校验、API 调用和索引存储；根目录下两个脚本仅负责 CLI。运行器只通过 HTTP API 创建任务，后端继续独占 `data/tasks` 和 `data/outputs`，场景文件与运行索引保存在被 Git 忽略的 `data/demo-scenarios`。

**Tech Stack:** Python 3.12、rasterio 1.4.3、NumPy、Shapely、PyProj、httpx 0.28.1、Pydantic 2、pytest 8.3.4、Docker Compose、FastAPI。

## Global Constraints

- 目标 DEM 固定为 `dem_20260713_080113_884937cf`，CRS 为 `EPSG:4326`，范围为 `[78.39572341, 30.449041933, 80.942515968, 32.70424882]`。
- 六个模型独立选址，不构成联合场景；雷达任务和输出不得修改或删除。
- 任务、指标和输出必须由现有 API 与后端 worker 真实生成，脚本不得直接写入 `data/tasks` 或 `data/outputs`。
- 场景生成必须使用固定种子和稳定排序；相同 DEM、场景版本与候选编号生成相同原生请求。
- 场景外层与辅助 GeoJSON 必须标记 `synthetic`，但提交给 API 的 `request` 对象不得添加契约外字段。
- 六个任务串行运行；单模型失败不得阻断后续模型；默认复用请求哈希匹配且验收成功的任务。
- 不新增第三方依赖；复用 `backend/requirements.txt` 已固定的包。
- 所有 Python 单元测试命令从 `backend` 目录运行：`.\.venv\Scripts\python.exe -m pytest ...`。

---

### Task 1: 场景领域对象与原子存储

**Files:**
- Create: `backend/app/demo_scenarios/__init__.py`
- Create: `backend/app/demo_scenarios/models.py`
- Create: `backend/app/demo_scenarios/storage.py`
- Create: `backend/tests/test_demo_scenario_storage.py`
- Modify: `.gitignore`
- Modify: `.dockerignore`

**Interfaces:**
- Produces: `ScenarioEnvelope`, `ScenarioIndexEntry`, `canonical_request_hash(request)`, `read_json(path)`, `write_json_atomic(path, payload)`。
- Consumes: Python 标准库；后续任务只能通过这些接口读写场景和索引。

- [ ] **Step 1: 写入失败的存储测试**

```python
# backend/tests/test_demo_scenario_storage.py
import json
from pathlib import Path

from app.demo_scenarios.models import ScenarioEnvelope
from app.demo_scenarios.storage import canonical_request_hash, read_json, write_json_atomic


def test_scenario_envelope_keeps_metadata_outside_request() -> None:
    envelope = ScenarioEnvelope(
        scenario_id="uav-recon",
        model_id="uav",
        version=1,
        dem_id="dem_a",
        candidate_index=0,
        request={"dem_id": "dem_a", "route": {"waypoints": []}},
    )
    payload = envelope.to_dict()
    assert payload["scenario"]["synthetic"] is True
    assert "synthetic" not in payload["request"]


def test_request_hash_is_stable_across_key_order() -> None:
    left = {"b": 2, "a": {"y": 1, "x": 0}}
    right = {"a": {"x": 0, "y": 1}, "b": 2}
    assert canonical_request_hash(left) == canonical_request_hash(right)


def test_atomic_json_write_leaves_no_partial_file(tmp_path: Path) -> None:
    target = tmp_path / "scenario-index.json"
    write_json_atomic(target, {"version": 1, "models": {}})
    assert read_json(target) == {"version": 1, "models": {}}
    assert list(tmp_path.glob("*.tmp")) == []
    assert json.loads(target.read_text(encoding="utf-8"))["version"] == 1
```

- [ ] **Step 2: 运行测试并确认按预期失败**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_demo_scenario_storage.py -v
```

Expected: collection fails with `ModuleNotFoundError: No module named 'app.demo_scenarios'`。

- [ ] **Step 3: 实现场景对象、规范化哈希和原子写入**

```python
# backend/app/demo_scenarios/models.py
from dataclasses import dataclass, field
from typing import Any


JsonObject = dict[str, Any]


@dataclass(frozen=True)
class ScenarioEnvelope:
    scenario_id: str
    model_id: str
    version: int
    dem_id: str
    candidate_index: int
    request: JsonObject
    artifacts: tuple[str, ...] = ()

    def to_dict(self) -> JsonObject:
        return {
            "scenario": {
                "id": self.scenario_id,
                "model_id": self.model_id,
                "version": self.version,
                "synthetic": True,
                "dem_id": self.dem_id,
                "candidate_index": self.candidate_index,
                "artifacts": list(self.artifacts),
            },
            "request": self.request,
        }


@dataclass(frozen=True)
class ScenarioIndexEntry:
    scenario_id: str
    model_id: str
    version: int
    dem_id: str
    request_file: str
    request_hash: str
    task_id: str
    status: str
    duration_seconds: float
    retries: int
    candidate_index: int
    candidate_attempts: int
    metrics: JsonObject = field(default_factory=dict)
    outputs: tuple[JsonObject, ...] = ()
    accepted: bool = False
    failure_reason: str | None = None

    def to_dict(self) -> JsonObject:
        return {
            **self.__dict__,
            "outputs": list(self.outputs),
            "synthetic": True,
        }
```

```python
# backend/app/demo_scenarios/storage.py
import hashlib
import json
import os
from pathlib import Path
from typing import Any


def canonical_request_hash(request: dict[str, Any]) -> str:
    encoded = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return payload


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
```

```python
# backend/app/demo_scenarios/__init__.py
from .models import ScenarioEnvelope, ScenarioIndexEntry

__all__ = ["ScenarioEnvelope", "ScenarioIndexEntry"]
```

Add to both `.gitignore` and `.dockerignore` under runtime data:

```gitignore
data/demo-scenarios/*
```

- [ ] **Step 4: 运行测试并确认通过**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_demo_scenario_storage.py -v`

Expected: `3 passed`。

- [ ] **Step 5: 提交领域与存储基础**

```powershell
git add .gitignore .dockerignore backend/app/demo_scenarios backend/tests/test_demo_scenario_storage.py
git commit -m "feat: add demo scenario storage primitives"
```

---

### Task 2: 确定性 DEM 地形采样

**Files:**
- Create: `backend/app/demo_scenarios/terrain.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/demo_scenario_helpers.py`
- Create: `backend/tests/test_demo_scenario_terrain.py`

**Interfaces:**
- Produces: `TerrainGrid.load(path, max_dimension=512)`, `TerrainGrid.select(profile, candidate_index)`, `TerrainGrid.lonlat(row, col)`, `TerrainGrid.route(anchor, offsets)`。
- Consumes: rasterio 栅格、NumPy；Task 3 和 Task 4 依赖稳定候选排序与路线坐标。

**Implementation correction from real DEM verification:** `TerrainGrid.select` also accepts `required_offsets`; candidate masks must prove every offset lands on a valid DEM cell. All route-based builders pass their complete offset set because the target DEM has an irregular NoData boundary.

- [ ] **Step 1: 写入失败的地形采样测试**

```python
# backend/tests/__init__.py
```

```python
# backend/tests/demo_scenario_helpers.py
from pathlib import Path

import numpy
import rasterio
from rasterio.transform import from_origin

def write_dem(path: Path) -> None:
    rows, cols = numpy.indices((80, 80))
    data = (rows * 40 + numpy.abs(cols - 40) * 15).astype("float32")
    with rasterio.open(
        path, "w", driver="GTiff", width=80, height=80, count=1,
        dtype="float32", crs="EPSG:4326", transform=from_origin(79.0, 32.0, 0.005, 0.005),
    ) as dataset:
        dataset.write(data, 1)
```

```python
# backend/tests/test_demo_scenario_terrain.py
from pathlib import Path

from app.demo_scenarios.terrain import TerrainGrid
from tests.demo_scenario_helpers import write_dem


def test_candidate_selection_is_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "dem.tif"
    write_dem(path)
    first = TerrainGrid.load(path, max_dimension=80)
    second = TerrainGrid.load(path, max_dimension=80)
    assert first.select("ridge", 0) == second.select("ridge", 0)
    assert first.select("valley", 1) == second.select("valley", 1)


def test_route_returns_valid_lon_lat_points(tmp_path: Path) -> None:
    path = tmp_path / "dem.tif"
    write_dem(path)
    terrain = TerrainGrid.load(path, max_dimension=80)
    anchor = terrain.select("valley", 0)
    route = terrain.route(anchor, [(-3, -4), (0, 0), (3, 4)])
    assert len(route) == 3
    assert all(79.0 <= lon <= 79.4 and 31.6 <= lat <= 32.0 for lon, lat in route)
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_demo_scenario_terrain.py -v`

Expected: `ModuleNotFoundError` for `app.demo_scenarios.terrain`。

- [ ] **Step 3: 实现降采样、坡度/起伏计算和稳定候选排序**

```python
# backend/app/demo_scenarios/terrain.py
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.warp import transform as transform_points


Profile = Literal["ridge", "rough", "valley", "flat"]
Cell = tuple[int, int]


@dataclass
class TerrainGrid:
    elevation: numpy.ndarray
    valid: numpy.ndarray
    slope_deg: numpy.ndarray
    relief_m: numpy.ndarray
    transform: Affine
    crs: object

    @classmethod
    def load(cls, path: Path, max_dimension: int = 512) -> "TerrainGrid":
        with rasterio.open(path) as source:
            scale = max(source.width / max_dimension, source.height / max_dimension, 1)
            width = max(1, round(source.width / scale))
            height = max(1, round(source.height / scale))
            band = source.read(1, out_shape=(height, width), masked=True, resampling=Resampling.bilinear)
            transform = source.transform * Affine.scale(source.width / width, source.height / height)
            elevation = band.filled(numpy.nan).astype("float64")
            valid = (~numpy.ma.getmaskarray(band)) & numpy.isfinite(elevation)
            center_lat = transform.f + transform.e * height / 2
            x_m = abs(transform.a) * 111_320 * numpy.cos(numpy.deg2rad(center_lat))
            y_m = abs(transform.e) * 110_540
            safe = numpy.where(valid, elevation, numpy.nanmedian(elevation[valid]))
            dy, dx = numpy.gradient(safe, y_m, x_m)
            slope = numpy.degrees(numpy.arctan(numpy.hypot(dx, dy)))
            relief = numpy.zeros_like(safe)
            for row_shift, col_shift in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1)):
                relief = numpy.maximum(relief, numpy.abs(safe - numpy.roll(safe, (row_shift, col_shift), (0, 1))))
            return cls(elevation, valid, slope, relief, transform, source.crs)

    def select(self, profile: Profile, candidate_index: int, margin: int = 6) -> Cell:
        rows, cols = numpy.indices(self.elevation.shape)
        interior = self.valid & (rows >= margin) & (cols >= margin)
        interior &= rows < self.elevation.shape[0] - margin
        interior &= cols < self.elevation.shape[1] - margin
        valid_elevation = self.elevation[self.valid]
        elevation_span = numpy.nanmax(valid_elevation) - numpy.nanmin(valid_elevation)
        elev = (self.elevation - numpy.nanmin(valid_elevation)) / max(elevation_span, 1)
        relief = self.relief_m / max(numpy.nanmax(self.relief_m[self.valid]), 1)
        rules = {
            "ridge": (interior & (self.slope_deg <= 25), elev + relief),
            "rough": (interior & (self.slope_deg >= 4) & (self.slope_deg <= 35), relief + self.slope_deg / 90),
            "valley": (interior & (self.slope_deg <= 15), -elev - self.slope_deg / 90),
            "flat": (interior & (self.slope_deg <= 10), -self.slope_deg / 90 + 0.25 * relief),
        }
        mask, score = rules[profile]
        cells = numpy.argwhere(mask)
        if len(cells) == 0:
            raise ValueError(f"No DEM candidates for profile '{profile}'")
        order = sorted(cells.tolist(), key=lambda rc: (-float(score[rc[0], rc[1]]), rc[0], rc[1]))
        position = candidate_index * 32
        if position >= len(order):
            raise IndexError(f"Candidate {candidate_index} is unavailable for profile '{profile}'")
        return tuple(order[position])

    def lonlat(self, row: int, col: int) -> tuple[float, float]:
        x, y = rasterio.transform.xy(self.transform, row, col, offset="center")
        if str(self.crs).upper() == "EPSG:4326":
            return float(x), float(y)
        lon, lat = transform_points(self.crs, "EPSG:4326", [x], [y])
        return float(lon[0]), float(lat[0])

    def route(self, anchor: Cell, offsets: list[Cell]) -> list[tuple[float, float]]:
        points: list[tuple[float, float]] = []
        for row_offset, col_offset in offsets:
            row, col = anchor[0] + row_offset, anchor[1] + col_offset
            if not (0 <= row < self.valid.shape[0] and 0 <= col < self.valid.shape[1] and self.valid[row, col]):
                raise ValueError("Route point falls outside valid DEM data")
            points.append(self.lonlat(row, col))
        return points
```

- [ ] **Step 4: 运行测试并确认通过**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_demo_scenario_terrain.py -v`

Expected: `2 passed`。

- [ ] **Step 5: 提交地形采样实现**

```powershell
git add backend/app/demo_scenarios/terrain.py backend/tests/__init__.py backend/tests/demo_scenario_helpers.py backend/tests/test_demo_scenario_terrain.py
git commit -m "feat: add deterministic demo terrain sampling"
```

---

### Task 3: 四个覆盖类模型场景构建器

**Files:**
- Create: `backend/app/demo_scenarios/coverage_builders.py`
- Create: `backend/tests/test_demo_coverage_builders.py`

**Interfaces:**
- Produces: `build_uav(terrain, dem_id, candidate_index)`, `build_watchpost(...)`, `build_artillery(...)`, `build_recon_vehicle(...)`，均返回 `ScenarioEnvelope`。
- Consumes: `TerrainGrid.select/route/lonlat`、现有四个 Pydantic 请求 schema。

- [ ] **Step 1: 写入四种场景契约测试**

```python
# backend/tests/test_demo_coverage_builders.py
import pytest

from app.demo_scenarios.coverage_builders import BUILDERS
from app.demo_scenarios.terrain import TerrainGrid
from app.schemas.artillery import ArtilleryCoverageRequest
from app.schemas.recon_vehicle import ReconVehicleCoverageRequest
from app.schemas.uav import UavReconRequest
from app.schemas.watchpost import WatchpostDetectionRequest
from tests.demo_scenario_helpers import write_dem


@pytest.mark.parametrize(
    ("model_id", "schema"),
    [("uav", UavReconRequest), ("watchpost", WatchpostDetectionRequest),
     ("artillery", ArtilleryCoverageRequest), ("recon_vehicle", ReconVehicleCoverageRequest)],
)
def test_coverage_builder_creates_valid_native_request(tmp_path, model_id, schema) -> None:
    dem_path = tmp_path / "dem.tif"
    write_dem(dem_path)
    terrain = TerrainGrid.load(dem_path, max_dimension=80)
    envelope = BUILDERS[model_id](terrain, "dem_a", 0)
    schema.model_validate(envelope.request)
    assert envelope.model_id == model_id
    assert envelope.to_dict()["scenario"]["synthetic"] is True
    assert "synthetic" not in envelope.request


def test_uav_and_recon_build_routes_with_multiple_waypoints(tmp_path) -> None:
    dem_path = tmp_path / "dem.tif"
    write_dem(dem_path)
    terrain = TerrainGrid.load(dem_path, max_dimension=80)
    assert len(BUILDERS["uav"](terrain, "dem_a", 0).request["route"]["waypoints"]) >= 6
    assert len(BUILDERS["recon_vehicle"](terrain, "dem_a", 0).request["route"]["waypoints"]) >= 5
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_demo_coverage_builders.py -v`

Expected: import failure for `coverage_builders`。

- [ ] **Step 3: 实现航向计算与四个原生请求构建器**

```python
# backend/app/demo_scenarios/coverage_builders.py
from math import atan2, cos, degrees, radians, sin
from typing import Callable

from app.demo_scenarios.models import ScenarioEnvelope
from app.demo_scenarios.terrain import TerrainGrid


def _heading(left: tuple[float, float], right: tuple[float, float]) -> float:
    lon1, lat1, lon2, lat2 = map(radians, (*left, *right))
    value = atan2(sin(lon2 - lon1) * cos(lat2), cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(lon2 - lon1))
    return (degrees(value) + 360) % 360


def build_uav(terrain: TerrainGrid, dem_id: str, candidate_index: int) -> ScenarioEnvelope:
    route = terrain.route(terrain.select("rough", candidate_index, margin=14), [(-8, -12), (-5, -7), (-2, -2), (2, 3), (5, 8), (8, 12)])
    waypoints = []
    for index, point in enumerate(route):
        heading = _heading(point, route[index + 1]) if index < len(route) - 1 else _heading(route[index - 1], point)
        waypoints.append({"lon": point[0], "lat": point[1], "altitude_m": 350 + index * 60,
                          "altitude_mode": "agl", "heading_deg": heading,
                          "pitch_deg": 2 if index % 2 else 0, "roll_deg": 0})
    request = {
        "dem_id": dem_id, "uav": waypoints[0], "route": {"waypoints": waypoints, "sample_interval_m": 1000},
        "sensor": {"sensor_type": "thermal", "h_fov_deg": 70, "v_fov_deg": 45,
                   "max_range_m": 6000, "min_range_m": 100, "ground_resolution_m": 5},
        "analysis": {"target_height_m": 1.7, "use_terrain_occlusion": True,
                     "sample_resolution_m": 120, "output_simplify_tolerance_m": 30},
    }
    return ScenarioEnvelope("uav-recon", "uav", 1, dem_id, candidate_index, request)


def build_watchpost(terrain: TerrainGrid, dem_id: str, candidate_index: int) -> ScenarioEnvelope:
    lon, lat = terrain.lonlat(*terrain.select("ridge", candidate_index))
    request = {
        "dem_id": dem_id, "observer": {"lon": lon, "lat": lat, "height_m": 8},
        "target": {"height_m": 1.7},
        "coverage": {"max_range_m": 12000, "scan_mode": "sector", "azimuth_deg": 135, "view_angle_deg": 120},
        "analysis": {"use_curvature": True, "curvature_coeff": 0.75, "output_simplify_tolerance_m": 30},
    }
    return ScenarioEnvelope("watchpost-detection", "watchpost", 1, dem_id, candidate_index, request)


def build_artillery(terrain: TerrainGrid, dem_id: str, candidate_index: int) -> ScenarioEnvelope:
    lon, lat = terrain.lonlat(*terrain.select("flat", candidate_index))
    request = {
        "dem_id": dem_id, "battery": {"lon": lon, "lat": lat, "height_m": 0, "altitude_mode": "agl"},
        "target": {"target_height_m": 0},
        "weapon": {"min_range_m": 2000, "max_range_m": 12000, "azimuth_deg": 90,
                   "traverse_deg": 120, "muzzle_velocity_mps": 420, "elevation_deg": 35},
        "munition": {"munition_type": "generic", "lethal_radius_m": 50, "effective_radius_m": 120},
        "analysis": {"use_dem_elevation": True, "use_terrain_masking": True, "sample_resolution_m": 250,
                     "trajectory_samples": 80, "clearance_margin_m": 0, "output_simplify_tolerance_m": 30},
    }
    return ScenarioEnvelope("artillery-coverage", "artillery", 1, dem_id, candidate_index, request)


def build_recon_vehicle(terrain: TerrainGrid, dem_id: str, candidate_index: int) -> ScenarioEnvelope:
    route = terrain.route(terrain.select("valley", candidate_index, margin=8), [(-4, -6), (-2, -3), (0, 0), (2, 3), (4, 6)])
    waypoints = []
    for index, point in enumerate(route):
        heading = _heading(point, route[index + 1]) if index < len(route) - 1 else _heading(route[index - 1], point)
        waypoints.append({"lon": point[0], "lat": point[1], "heading_deg": heading, "mast_height_m": 5})
    request = {
        "dem_id": dem_id, "vehicle": waypoints[0], "route": {"waypoints": waypoints, "sample_interval_m": 750},
        "sensor": {"sensor_type": "optical", "max_range_m": 5000, "min_range_m": 100,
                   "scan_mode": "sector", "view_angle_deg": 140},
        "target": {"height_m": 1.7},
        "analysis": {"use_terrain_occlusion": True, "use_curvature": True,
                     "curvature_coeff": 0.75, "output_simplify_tolerance_m": 30},
    }
    return ScenarioEnvelope("recon-vehicle", "recon_vehicle", 1, dem_id, candidate_index, request)


Builder = Callable[[TerrainGrid, str, int], ScenarioEnvelope]
BUILDERS: dict[str, Builder] = {
    "uav": build_uav, "watchpost": build_watchpost,
    "artillery": build_artillery, "recon_vehicle": build_recon_vehicle,
}
```

- [ ] **Step 4: 运行新测试和现有 schema/API 测试**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_demo_coverage_builders.py tests/test_uav_api.py tests/test_watchpost_api.py tests/test_artillery_api.py tests/test_recon_vehicle_api.py -v
```

Expected: all tests pass。

- [ ] **Step 5: 提交覆盖类场景构建器**

```powershell
git add backend/app/demo_scenarios/coverage_builders.py backend/tests/test_demo_coverage_builders.py
git commit -m "feat: build synthetic coverage model scenarios"
```

---

### Task 4: 机动通行与空中走廊场景构建器

**Files:**
- Create: `backend/app/demo_scenarios/route_builders.py`
- Create: `backend/tests/test_demo_route_builders.py`

**Interfaces:**
- Produces: `build_mobility(...) -> ScenarioEnvelope`、`build_air_corridor(...) -> ScenarioEnvelope`、`spatial_artifacts(envelope) -> dict[str, GeoJSON]`。
- Consumes: `TerrainGrid`；Task 5 将 GeoJSON 写为 `road-network.geojson` 和 `air-defense-threats.geojson`。

- [ ] **Step 1: 写入失败的路径模型测试**

```python
# backend/tests/test_demo_route_builders.py
from app.demo_scenarios.route_builders import build_air_corridor, build_mobility, spatial_artifacts
from app.demo_scenarios.terrain import TerrainGrid
from app.schemas.air_corridor import AirCorridorPlanningRequest
from app.schemas.mobility import MobilityAccessibilityRequest
from tests.demo_scenario_helpers import write_dem


def test_mobility_contains_three_synthetic_road_classes(tmp_path) -> None:
    path = tmp_path / "dem.tif"
    write_dem(path)
    scenario = build_mobility(TerrainGrid.load(path, 80), "dem_a", 0)
    MobilityAccessibilityRequest.model_validate(scenario.request)
    features = scenario.request["road_network"]["geojson"]["features"]
    assert {item["properties"]["road_class"] for item in features} == {"main", "branch", "trail"}
    assert all(item["properties"]["synthetic"] is True for item in features)


def test_air_corridor_contains_three_threats_and_altitude_layers(tmp_path) -> None:
    path = tmp_path / "dem.tif"
    write_dem(path)
    scenario = build_air_corridor(TerrainGrid.load(path, 80), "dem_a", 0)
    AirCorridorPlanningRequest.model_validate(scenario.request)
    assert len(scenario.request["threats"]) == 3
    assert scenario.request["altitude_layers_m"] == sorted(scenario.request["altitude_layers_m"])
    artifacts = spatial_artifacts(scenario)
    assert set(artifacts) == {"air-defense-threats.geojson"}
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_demo_route_builders.py -v`

Expected: import failure for `route_builders`。

- [ ] **Step 3: 实现道路网、威胁点和两个请求构建器**

```python
# backend/app/demo_scenarios/route_builders.py
from typing import Any

from app.demo_scenarios.models import ScenarioEnvelope
from app.demo_scenarios.terrain import TerrainGrid


def _line_feature(points: list[tuple[float, float]], road_class: str) -> dict[str, Any]:
    return {"type": "Feature", "properties": {"road_class": road_class, "synthetic": True},
            "geometry": {"type": "LineString", "coordinates": [list(point) for point in points]}}


def build_mobility(terrain: TerrainGrid, dem_id: str, candidate_index: int) -> ScenarioEnvelope:
    anchor = terrain.select("valley", candidate_index, margin=8)
    direct = terrain.route(anchor, [(-5, -7), (0, 0), (5, 7)])
    main = terrain.route(anchor, [(-5, -7), (-5, 0), (0, 7), (5, 7)])
    branch = terrain.route(anchor, [(-2, -5), (0, 0), (2, 5)])
    trail = terrain.route(anchor, [(-5, -7), (0, 0), (5, 7)])
    roads = {"type": "FeatureCollection", "synthetic": True,
             "features": [_line_feature(main, "main"), _line_feature(branch, "branch"), _line_feature(trail, "trail")]}
    request = {
        "dem_id": dem_id, "start": {"lon": direct[0][0], "lat": direct[0][1]},
        "end": {"lon": direct[-1][0], "lat": direct[-1][1]},
        "vehicles": {
            "wheeled": {"enabled": True, "base_speed_kph": 50, "max_slope_deg": 16, "slope_penalty": 2.4,
                        "road_speed_multiplier": 1.7, "offroad_speed_multiplier": 0.5},
            "tracked": {"enabled": True, "base_speed_kph": 32, "max_slope_deg": 32, "slope_penalty": 1.2,
                        "road_speed_multiplier": 1.2, "offroad_speed_multiplier": 0.9},
        },
        "road_network": {"geojson": roads, "road_buffer_m": 150,
                         "road_classes": {"main": 1.8, "branch": 1.35, "trail": 1.05}},
        "analysis": {"allow_diagonal": True, "max_search_radius_m": 50000, "output_simplify_tolerance_m": 30},
    }
    return ScenarioEnvelope("mobility-accessibility", "mobility", 1, dem_id, candidate_index, request,
                            ("road-network.geojson",))


def build_air_corridor(terrain: TerrainGrid, dem_id: str, candidate_index: int) -> ScenarioEnvelope:
    anchor = terrain.select("rough", candidate_index, margin=24)
    line = terrain.route(anchor, [(0, -22), (0, -7), (0, 0), (0, 7), (0, 22)])
    threats = []
    for index, point in enumerate(line[1:4], start=1):
        threats.append({"id": f"demo-threat-{index}", "name": f"Synthetic threat {index}",
                        "lon": point[0], "lat": point[1], "min_range_m": 1000,
                        "max_range_m": 5000 + index * 1000, "min_altitude_m": 0,
                        "max_altitude_m": 800 + index * 300, "threat_level": 4 + index * 2,
                        "kill_zone_radius_m": 2000 + index * 300, "warning_zone_radius_m": 3500 + index * 500})
    request = {
        "dem_id": dem_id,
        "start": {"lon": line[0][0], "lat": line[0][1], "altitude_m": 600, "altitude_mode": "agl"},
        "end": {"lon": line[-1][0], "lat": line[-1][1], "altitude_m": 600, "altitude_mode": "agl"},
        "aircraft": {"cruise_speed_kph": 180, "min_agl_m": 100, "max_agl_m": 3000,
                     "max_climb_rate_mps": 8, "max_descent_rate_mps": 10},
        "altitude_layers_m": [300, 600, 900, 1200, 1800, 2400], "threats": threats,
        "planning": {"corridor_width_m": 500, "horizontal_resolution_m": 250,
                     "allow_altitude_change": True, "threat_weight": 2.5, "distance_weight": 0.25,
                     "altitude_change_weight": 0.1, "terrain_clearance_weight": 0.4,
                     "output_simplify_tolerance_m": 30},
    }
    return ScenarioEnvelope("air-corridor", "air_corridor", 1, dem_id, candidate_index, request,
                            ("air-defense-threats.geojson",))


def spatial_artifacts(envelope: ScenarioEnvelope) -> dict[str, dict[str, Any]]:
    if envelope.model_id == "mobility":
        return {"road-network.geojson": envelope.request["road_network"]["geojson"]}
    if envelope.model_id == "air_corridor":
        features = [{"type": "Feature", "properties": {**item, "synthetic": True},
                     "geometry": {"type": "Point", "coordinates": [item["lon"], item["lat"]]}}
                    for item in envelope.request["threats"]]
        return {"air-defense-threats.geojson": {"type": "FeatureCollection", "synthetic": True, "features": features}}
    return {}
```

- [ ] **Step 4: 运行新测试和现有路径模型测试**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_demo_route_builders.py tests/test_mobility_api.py tests/test_mobility_task.py tests/test_air_corridor_api.py tests/test_air_corridor_task.py -v
```

Expected: all tests pass。

- [ ] **Step 5: 提交路径类场景构建器**

```powershell
git add backend/app/demo_scenarios/route_builders.py backend/tests/test_demo_route_builders.py
git commit -m "feat: build synthetic route model scenarios"
```

---

### Task 5: 场景生成编排与 CLI

**Files:**
- Create: `backend/app/demo_scenarios/generator.py`
- Create: `scripts/generate_demo_scenarios.py`
- Create: `backend/tests/test_demo_scenario_generator.py`

**Interfaces:**
- Produces: `generate_scenarios(data_dir, dem_id, candidate_indices=None) -> dict[str, ScenarioEnvelope]`、`generate_one(...)`。
- Consumes: Tasks 1-4 的 storage、terrain 和 builders；Task 8 使用 `generate_one` 执行候选回退。

- [ ] **Step 1: 写入失败的生成器测试**

```python
# backend/tests/test_demo_scenario_generator.py
import json

from app.demo_scenarios.generator import MODEL_ORDER, generate_scenarios
from tests.demo_scenario_helpers import write_dem


def test_generator_writes_six_scenarios_and_artifacts(tmp_path) -> None:
    dem_id = "dem_a"
    dem_dir = tmp_path / "dem" / dem_id
    dem_dir.mkdir(parents=True)
    write_dem(dem_dir / "dem.cog.tif")
    (dem_dir / "metadata.json").write_text(
        json.dumps({"dem_id": dem_id, "crs": "EPSG:4326", "bounds": [79.0, 31.6, 79.4, 32.0]}),
        encoding="utf-8",
    )
    scenarios = generate_scenarios(tmp_path, dem_id)
    output = tmp_path / "demo-scenarios" / dem_id
    assert list(scenarios) == MODEL_ORDER
    assert len(list(output.glob("*.json"))) == 6
    assert (output / "road-network.geojson").exists()
    assert (output / "air-defense-threats.geojson").exists()
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_demo_scenario_generator.py -v`

Expected: import failure for `generator`。

- [ ] **Step 3: 实现生成编排和 CLI 入口**

```python
# backend/app/demo_scenarios/generator.py
import argparse
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

from app.demo_scenarios.coverage_builders import BUILDERS as COVERAGE_BUILDERS
from app.demo_scenarios.models import ScenarioEnvelope
from app.demo_scenarios.route_builders import build_air_corridor, build_mobility, spatial_artifacts
from app.demo_scenarios.storage import read_json, write_json_atomic
from app.demo_scenarios.terrain import TerrainGrid
from app.schemas.air_corridor import AirCorridorPlanningRequest
from app.schemas.artillery import ArtilleryCoverageRequest
from app.schemas.mobility import MobilityAccessibilityRequest
from app.schemas.recon_vehicle import ReconVehicleCoverageRequest
from app.schemas.uav import UavReconRequest
from app.schemas.watchpost import WatchpostDetectionRequest


MODEL_ORDER = ["uav", "watchpost", "artillery", "recon_vehicle", "mobility", "air_corridor"]
BUILDERS = {**COVERAGE_BUILDERS, "mobility": build_mobility, "air_corridor": build_air_corridor}
TARGET_DEM_ID = "dem_20260713_080113_884937cf"
TARGET_BOUNDS = [78.39572341, 30.449041933, 80.942515968, 32.70424882]
REQUEST_SCHEMAS = {
    "uav": UavReconRequest, "watchpost": WatchpostDetectionRequest,
    "artillery": ArtilleryCoverageRequest, "recon_vehicle": ReconVehicleCoverageRequest,
    "mobility": MobilityAccessibilityRequest, "air_corridor": AirCorridorPlanningRequest,
}


@lru_cache(maxsize=2)
def _load_terrain(dem_path: Path) -> TerrainGrid:
    return TerrainGrid.load(dem_path)


def _validate_dem_metadata(data_dir: Path, dem_id: str) -> None:
    metadata_path = data_dir / "dem" / dem_id / "metadata.json"
    metadata = read_json(metadata_path)
    if metadata.get("dem_id") != dem_id:
        raise ValueError(f"DEM metadata id mismatch in {metadata_path}")
    bounds = metadata.get("bounds")
    if metadata.get("crs") != "EPSG:4326" or not isinstance(bounds, list) or len(bounds) != 4:
        raise ValueError(f"Unsupported DEM metadata in {metadata_path}")
    if dem_id == TARGET_DEM_ID and bounds != TARGET_BOUNDS:
        raise ValueError(f"Target DEM bounds mismatch in {metadata_path}")


def generate_one(data_dir: Path, dem_id: str, model_id: str, candidate_index: int) -> ScenarioEnvelope:
    _validate_dem_metadata(data_dir, dem_id)
    dem_path = data_dir / "dem" / dem_id / "dem.cog.tif"
    if not dem_path.exists():
        raise FileNotFoundError(f"DEM COG not found: {dem_path}")
    terrain = _load_terrain(dem_path)
    scenario = BUILDERS[model_id](terrain, dem_id, candidate_index)
    native_request = REQUEST_SCHEMAS[model_id].model_validate(scenario.request).model_dump(mode="json")
    scenario = replace(scenario, request=native_request)
    output_dir = data_dir / "demo-scenarios" / dem_id
    write_json_atomic(output_dir / f"{scenario.scenario_id}.json", scenario.to_dict())
    for filename, payload in spatial_artifacts(scenario).items():
        write_json_atomic(output_dir / filename, payload)
    return scenario


def generate_scenarios(data_dir: Path, dem_id: str, candidate_indices: dict[str, int] | None = None) -> dict[str, ScenarioEnvelope]:
    selected = candidate_indices or {}
    return {model_id: generate_one(data_dir, dem_id, model_id, selected.get(model_id, 0)) for model_id in MODEL_ORDER}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic synthetic PyGeoModel demo scenarios.")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--dem-id", required=True)
    args = parser.parse_args()
    scenarios = generate_scenarios(args.data_dir, args.dem_id)
    for model_id, scenario in scenarios.items():
        print(f"{model_id}: candidate={scenario.candidate_index} scenario={scenario.scenario_id}")
```

```python
# scripts/generate_demo_scenarios.py
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend" if (PROJECT_ROOT / "backend").exists() else PROJECT_ROOT
sys.path.insert(0, str(BACKEND_ROOT))

from app.demo_scenarios.generator import main


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行生成器测试和 CLI help**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_demo_scenario_generator.py -v
cd ..
$env:PYTHONPATH='backend'
backend\.venv\Scripts\python.exe scripts\generate_demo_scenarios.py --help
```

Expected: test passes；CLI 显示 `--data-dir` 与 `--dem-id`。

- [ ] **Step 5: 提交生成编排**

```powershell
git add backend/app/demo_scenarios/generator.py backend/tests/test_demo_scenario_generator.py scripts/generate_demo_scenarios.py
git commit -m "feat: add demo scenario generator cli"
```

---

### Task 6: 模型注册表与结果验收

**Files:**
- Create: `backend/app/demo_scenarios/registry.py`
- Create: `backend/tests/test_demo_scenario_registry.py`

**Interfaces:**
- Produces: `MODEL_SPECS: dict[str, ModelSpec]`、`ModelSpec.validate(metrics, output_kinds) -> list[str]`。
- Consumes: 六种模型的 metrics JSON 与 output kind；Task 7/8 用于复用和最终验收。

- [ ] **Step 1: 写入失败的注册表验收测试**

```python
# backend/tests/test_demo_scenario_registry.py
import pytest

from app.demo_scenarios.registry import MODEL_SPECS


@pytest.mark.parametrize("model_id", ["uav", "watchpost", "artillery", "recon_vehicle", "mobility", "air_corridor"])
def test_model_registry_has_endpoint_and_required_outputs(model_id: str) -> None:
    spec = MODEL_SPECS[model_id]
    assert spec.base_path.startswith("/api/")
    assert spec.required_outputs


def test_watchpost_rejects_extreme_blocked_ratio() -> None:
    spec = MODEL_SPECS["watchpost"]
    outputs = {"range_geojson", "visible_geojson", "blocked_geojson"}
    assert spec.validate({"blocked_ratio": 0}, outputs)
    assert spec.validate({"blocked_ratio": 0.4}, outputs) == []


def test_mobility_requires_two_reachable_distinct_results() -> None:
    spec = MODEL_SPECS["mobility"]
    outputs = {"road_mask_geojson", "wheeled_path_geojson", "tracked_path_geojson"}
    metrics = {"wheeled": {"reachable": True, "travel_time_seconds": 100},
               "tracked": {"reachable": True, "travel_time_seconds": 100}}
    assert spec.validate(metrics, outputs)
    metrics["tracked"]["travel_time_seconds"] = 140
    assert spec.validate(metrics, outputs) == []
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_demo_scenario_registry.py -v`

Expected: import failure for `registry`。

- [ ] **Step 3: 实现六种模型规格和明确验收函数**

```python
# backend/app/demo_scenarios/registry.py
from dataclasses import dataclass
from typing import Callable


Validator = Callable[[dict, set[str]], list[str]]


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    base_path: str
    required_outputs: frozenset[str]
    metric_validator: Validator

    def validate(self, metrics: dict, output_kinds: set[str]) -> list[str]:
        errors = [f"missing output: {kind}" for kind in sorted(self.required_outputs - output_kinds)]
        return errors + self.metric_validator(metrics, output_kinds)


def _positive(metrics: dict, *keys: str) -> list[str]:
    return [f"metric must be positive: {key}" for key in keys if float(metrics.get(key) or 0) <= 0]


def _uav(metrics: dict, _: set[str]) -> list[str]:
    return _positive(metrics, "route_length_m", "coverage_point_count", "visible_area_m2", "blocked_area_m2")


def _watchpost(metrics: dict, _: set[str]) -> list[str]:
    ratio = float(metrics.get("blocked_ratio") or 0)
    return [] if 0.01 < ratio < 0.99 else ["blocked_ratio must be between 0.01 and 0.99"]


def _artillery(metrics: dict, _: set[str]) -> list[str]:
    return _positive(metrics, "theoretical_area_m2", "reachable_area_m2", "terrain_masked_area_m2", "sample_point_count")


def _recon(metrics: dict, _: set[str]) -> list[str]:
    return _positive(metrics, "route_length_m", "coverage_point_count", "visible_area_m2", "blocked_area_m2")


def _mobility(metrics: dict, _: set[str]) -> list[str]:
    wheeled, tracked = metrics.get("wheeled", {}), metrics.get("tracked", {})
    errors = []
    if not wheeled.get("reachable") or not tracked.get("reachable"):
        errors.append("both vehicle types must be reachable")
    left, right = wheeled.get("travel_time_seconds"), tracked.get("travel_time_seconds")
    if left is None or right is None or abs(float(left) - float(right)) <= 1:
        errors.append("vehicle travel times must differ by more than one second")
    return errors


def _air(metrics: dict, _: set[str]) -> list[str]:
    errors = [] if metrics.get("route_found") is True else ["air corridor route was not found"]
    return errors + _positive(metrics, "corridor_length_m")


MODEL_SPECS = {
    "uav": ModelSpec("uav", "/api/uav/recon", frozenset({"footprint_geojson", "visible_geojson", "blocked_geojson"}), _uav),
    "watchpost": ModelSpec("watchpost", "/api/watchpost/detection", frozenset({"range_geojson", "visible_geojson", "blocked_geojson"}), _watchpost),
    "artillery": ModelSpec("artillery", "/api/artillery/coverage", frozenset({"theoretical_geojson", "reachable_geojson", "terrain_masked_geojson", "sample_points_geojson"}), _artillery),
    "recon_vehicle": ModelSpec("recon_vehicle", "/api/recon-vehicle/coverage", frozenset({"footprint_geojson", "visible_geojson", "blocked_geojson"}), _recon),
    "mobility": ModelSpec("mobility", "/api/mobility/accessibility", frozenset({"road_mask_geojson", "wheeled_path_geojson", "tracked_path_geojson"}), _mobility),
    "air_corridor": ModelSpec("air_corridor", "/api/air-corridor/planning", frozenset({"threat_zones_geojson", "corridor_buffer_geojson", "corridor_path_geojson", "risk_samples_geojson"}), _air),
}
```

- [ ] **Step 4: 运行注册表测试**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_demo_scenario_registry.py -v`

Expected: `8 passed`。

- [ ] **Step 5: 提交验收注册表**

```powershell
git add backend/app/demo_scenarios/registry.py backend/tests/test_demo_scenario_registry.py
git commit -m "feat: define demo model acceptance rules"
```

---

### Task 7: HTTP API 客户端、轮询与请求复用

**Files:**
- Create: `backend/app/demo_scenarios/api_client.py`
- Create: `backend/tests/test_demo_scenario_api_client.py`

**Interfaces:**
- Produces: `DemoApiClient.health()`, `find_matching_task(spec, request_hash)`, `create_task(spec, request)`, `wait_for_task(spec, task_id)`, `task_result(spec, task_id)`。
- Consumes: `httpx.Client`、`canonical_request_hash`、`ModelSpec`。

- [ ] **Step 1: 写入失败的 API 客户端测试**

```python
# backend/tests/test_demo_scenario_api_client.py
import httpx

from app.demo_scenarios.api_client import DemoApiClient
from app.demo_scenarios.registry import MODEL_SPECS
from app.demo_scenarios.storage import canonical_request_hash


def test_client_finds_finished_task_by_detail_request_hash() -> None:
    request = {"dem_id": "dem_a", "observer": {"lon": 79.8, "lat": 31.4}}

    def handler(incoming: httpx.Request) -> httpx.Response:
        if incoming.url.path == "/api/watchpost/detection":
            return httpx.Response(200, json=[{"task_id": "task_1", "dem_id": "dem_a", "status": "finished"}])
        if incoming.url.path == "/api/watchpost/detection/task_1":
            return httpx.Response(200, json={"task_id": "task_1", "status": "finished", "request": request})
        raise AssertionError(incoming.url.path)

    http = httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler))
    client = DemoApiClient("http://test", http=http, poll_seconds=0, task_timeout_seconds=1)
    found = client.find_matching_task(MODEL_SPECS["watchpost"], canonical_request_hash(request))
    assert found == "task_1"


def test_wait_for_task_returns_finished_detail() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        status = "running" if calls == 1 else "finished"
        return httpx.Response(200, json={"task_id": "task_1", "status": status})

    http = httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler))
    client = DemoApiClient("http://test", http=http, poll_seconds=0, task_timeout_seconds=1)
    assert client.wait_for_task(MODEL_SPECS["uav"], "task_1")["status"] == "finished"


def test_create_task_recovers_post_timeout_without_duplicate_submission() -> None:
    request = {"dem_id": "dem_a"}
    post_count = 0

    def handler(incoming: httpx.Request) -> httpx.Response:
        nonlocal post_count
        if incoming.method == "POST":
            post_count += 1
            raise httpx.ReadTimeout("response lost", request=incoming)
        if incoming.url.path == "/api/uav/recon":
            return httpx.Response(200, json=[{"task_id": "task_1", "status": "pending"}])
        if incoming.url.path == "/api/uav/recon/task_1":
            return httpx.Response(200, json={"task_id": "task_1", "status": "pending", "request": request})
        raise AssertionError(incoming.url.path)

    http = httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler))
    client = DemoApiClient("http://test", http=http, poll_seconds=0, task_timeout_seconds=1)
    assert client.create_task(MODEL_SPECS["uav"], request) == "task_1"
    assert post_count == 1
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_demo_scenario_api_client.py -v`

Expected: import failure for `api_client`。

- [ ] **Step 3: 实现有限重试、任务匹配、提交、轮询和结果读取**

```python
# backend/app/demo_scenarios/api_client.py
import time
from typing import Any

import httpx

from app.demo_scenarios.registry import ModelSpec
from app.demo_scenarios.storage import canonical_request_hash


class DemoApiClient:
    def __init__(self, base_url: str, *, http: httpx.Client | None = None, poll_seconds: float = 2,
                 task_timeout_seconds: float = 900, retries: int = 3) -> None:
        self.http = http or httpx.Client(base_url=base_url.rstrip("/"), timeout=30)
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
            except httpx.TransportError:
                if attempt == self.retries:
                    raise
            if attempt == self.retries:
                response.raise_for_status()
            self.retry_count += 1
            time.sleep(min(2 ** attempt, 5))
        raise RuntimeError("unreachable retry state")

    def health(self) -> None:
        payload = self._request("GET", "/api/health").json()
        if payload != {"status": "ok"}:
            raise RuntimeError(f"Unexpected health response: {payload}")

    def find_matching_task(self, spec: ModelSpec, request_hash: str,
                           statuses: frozenset[str] = frozenset({"finished"})) -> str | None:
        for summary in self._request("GET", spec.base_path).json():
            if summary.get("status") not in statuses:
                continue
            detail = self._request("GET", f"{spec.base_path}/{summary['task_id']}").json()
            request = detail.get("request")
            if isinstance(request, dict) and canonical_request_hash(request) == request_hash:
                return str(summary["task_id"])
        return None

    def create_task(self, spec: ModelSpec, request: dict[str, Any]) -> str:
        request_hash = canonical_request_hash(request)
        for attempt in range(self.retries + 1):
            try:
                response = self.http.post(spec.base_path, json=request)
                if response.status_code < 500:
                    response.raise_for_status()
                    return str(response.json()["task_id"])
                matching = self.find_matching_task(
                    spec, request_hash, frozenset({"pending", "running", "finished"})
                )
                if matching is not None:
                    return matching
                if attempt == self.retries:
                    response.raise_for_status()
            except httpx.TransportError:
                matching = self.find_matching_task(
                    spec, request_hash, frozenset({"pending", "running", "finished"})
                )
                if matching is not None:
                    return matching
                if attempt == self.retries:
                    raise
            self.retry_count += 1
            time.sleep(min(2 ** attempt, 5))
        raise RuntimeError("unreachable create retry state")

    def wait_for_task(self, spec: ModelSpec, task_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.task_timeout_seconds
        while time.monotonic() <= deadline:
            detail = self._request("GET", f"{spec.base_path}/{task_id}").json()
            if detail.get("status") == "finished":
                return detail
            if detail.get("status") == "failed":
                raise RuntimeError(detail.get("message") or f"Task failed: {task_id}")
            time.sleep(self.poll_seconds)
        raise TimeoutError(f"Task timed out: {task_id}")

    def task_result(self, spec: ModelSpec, task_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        metrics = self._request("GET", f"{spec.base_path}/{task_id}/metrics").json()
        outputs = self._request("GET", f"{spec.base_path}/{task_id}/outputs").json()
        return metrics, outputs
```

- [ ] **Step 4: 运行 API 客户端测试**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_demo_scenario_api_client.py -v`

Expected: `3 passed`。

- [ ] **Step 5: 提交 API 客户端**

```powershell
git add backend/app/demo_scenarios/api_client.py backend/tests/test_demo_scenario_api_client.py
git commit -m "feat: add demo task api client"
```

---

### Task 8: 任务运行编排、候选回退与场景索引

**Files:**
- Create: `backend/app/demo_scenarios/runner.py`
- Create: `backend/tests/test_demo_scenario_runner.py`

**Interfaces:**
- Produces: `run_scenarios(data_dir, dem_id, client, rebuild=False, max_candidates=4) -> dict`。
- Consumes: `generate_one`、`DemoApiClient`、`MODEL_SPECS`、`ScenarioIndexEntry`。

- [ ] **Step 1: 写入失败的串行运行与失败隔离测试**

```python
# backend/tests/test_demo_scenario_runner.py
from app.demo_scenarios.models import ScenarioEnvelope
from app.demo_scenarios.runner import run_scenarios


class FakeClient:
    def __init__(self) -> None:
        self.created: list[str] = []
        self.retry_count = 0

    def health(self) -> None: pass
    def find_matching_task(self, spec, request_hash): return None
    def create_task(self, spec, request):
        self.created.append(spec.model_id)
        return f"{spec.model_id}_task"
    def wait_for_task(self, spec, task_id): return {"status": "finished", "task_id": task_id}
    def task_result(self, spec, task_id):
        metrics = {
            "uav": {"route_length_m": 1, "coverage_point_count": 2, "visible_area_m2": 1, "blocked_area_m2": 1},
            "watchpost": {"blocked_ratio": 0.4},
            "artillery": {"theoretical_area_m2": 1, "reachable_area_m2": 1, "terrain_masked_area_m2": 1, "sample_point_count": 1},
            "recon_vehicle": {"route_length_m": 1, "coverage_point_count": 2, "visible_area_m2": 1, "blocked_area_m2": 1},
            "mobility": {"wheeled": {"reachable": True, "travel_time_seconds": 100}, "tracked": {"reachable": True, "travel_time_seconds": 140}},
            "air_corridor": {"route_found": True, "corridor_length_m": 1},
        }[spec.model_id]
        return metrics, [{"kind": kind, "filename": f"{kind}.geojson", "media_type": "application/geo+json"}
                         for kind in spec.required_outputs]


def test_runner_submits_models_in_fixed_order_and_writes_index(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.demo_scenarios.runner.generate_one",
        lambda _data_dir, dem_id, model_id, candidate_index: ScenarioEnvelope(
            model_id, model_id, 1, dem_id, candidate_index, {"dem_id": dem_id}
        ),
    )
    client = FakeClient()
    index = run_scenarios(tmp_path, "dem_a", client, max_candidates=1)
    assert client.created == ["uav", "watchpost", "artillery", "recon_vehicle", "mobility", "air_corridor"]
    assert all(item["accepted"] for item in index["models"].values())
    assert (tmp_path / "demo-scenarios" / "dem_a" / "scenario-index.json").exists()
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_demo_scenario_runner.py -v`

Expected: import failure for `runner`。

- [ ] **Step 3: 实现串行执行、复用、候选回退和索引写入**

```python
# backend/app/demo_scenarios/runner.py
import time
from pathlib import Path
from typing import Any

from app.demo_scenarios.api_client import DemoApiClient
from app.demo_scenarios.generator import MODEL_ORDER, generate_one
from app.demo_scenarios.models import ScenarioEnvelope, ScenarioIndexEntry
from app.demo_scenarios.registry import MODEL_SPECS
from app.demo_scenarios.storage import canonical_request_hash, write_json_atomic


def _run_one(client: DemoApiClient, scenario: ScenarioEnvelope, rebuild: bool) -> ScenarioIndexEntry:
    spec = MODEL_SPECS[scenario.model_id]
    request_hash = canonical_request_hash(scenario.request)
    started = time.monotonic()
    retries_before = client.retry_count
    task_id = None if rebuild else client.find_matching_task(spec, request_hash)
    if task_id is None:
        task_id = client.create_task(spec, scenario.request)
    client.wait_for_task(spec, task_id)
    metrics, outputs = client.task_result(spec, task_id)
    errors = spec.validate(metrics, {str(item["kind"]) for item in outputs})
    return ScenarioIndexEntry(
        scenario_id=scenario.scenario_id, model_id=scenario.model_id, version=scenario.version,
        dem_id=scenario.dem_id, request_file=f"{scenario.scenario_id}.json", request_hash=request_hash,
        task_id=task_id, status="finished", duration_seconds=round(time.monotonic() - started, 3),
        retries=client.retry_count - retries_before, candidate_index=scenario.candidate_index, metrics=metrics,
        candidate_attempts=scenario.candidate_index + 1,
        outputs=tuple(outputs), accepted=not errors, failure_reason="; ".join(errors) or None,
    )


def run_scenarios(data_dir: Path, dem_id: str, client: DemoApiClient, *, rebuild: bool = False,
                  max_candidates: int = 4) -> dict[str, Any]:
    client.health()
    results: dict[str, Any] = {}
    for model_id in MODEL_ORDER:
        last_error: str | None = None
        for candidate_index in range(max_candidates):
            try:
                scenario = generate_one(data_dir, dem_id, model_id, candidate_index)
                entry = _run_one(client, scenario, rebuild)
                results[model_id] = entry.to_dict()
                if entry.accepted:
                    break
                last_error = entry.failure_reason
            except Exception as exc:
                last_error = str(exc)
                results[model_id] = {"model_id": model_id, "status": "failed", "accepted": False,
                                     "candidate_index": candidate_index, "candidate_attempts": candidate_index + 1,
                                     "failure_reason": last_error,
                                     "synthetic": True}
        if not results[model_id].get("accepted"):
            results[model_id]["failure_reason"] = last_error
    index = {"version": 1, "synthetic": True, "dem_id": dem_id, "models": results}
    write_json_atomic(data_dir / "demo-scenarios" / dem_id / "scenario-index.json", index)
    return index
```

- [ ] **Step 4: 补充候选失败不阻断后续模型测试并运行**

Add this exact test to `test_demo_scenario_runner.py`:

```python
def test_failed_model_does_not_block_later_models(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.demo_scenarios.runner.generate_one",
        lambda _data_dir, dem_id, model_id, candidate_index: ScenarioEnvelope(
            model_id, model_id, 1, dem_id, candidate_index, {"dem_id": dem_id}
        ),
    )
    client = FakeClient()
    original_result = client.task_result

    def fail_watchpost(spec, task_id):
        if spec.model_id == "watchpost":
            raise RuntimeError("synthetic watchpost failure")
        return original_result(spec, task_id)

    client.task_result = fail_watchpost
    index = run_scenarios(tmp_path, "dem_a", client, max_candidates=1)
    assert index["models"]["watchpost"]["accepted"] is False
    assert "synthetic watchpost failure" in index["models"]["watchpost"]["failure_reason"]
    assert client.created[-4:] == ["artillery", "recon_vehicle", "mobility", "air_corridor"]
```

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_demo_scenario_runner.py -v`

Expected: both runner tests pass。

- [ ] **Step 5: 提交任务运行编排**

```powershell
git add backend/app/demo_scenarios/runner.py backend/tests/test_demo_scenario_runner.py
git commit -m "feat: orchestrate synthetic demo tasks"
```

---

### Task 9: 运行 CLI 与 Docker 容器接入

**Files:**
- Create: `scripts/run_demo_scenarios.py`
- Create: `backend/tests/test_demo_scenario_cli.py`
- Modify: `backend/Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `README.md`

**Interfaces:**
- Produces: `docker compose exec -T backend python /app/scripts/generate_demo_scenarios.py ...` 和 `run_demo_scenarios.py ...`。
- Consumes: Task 5/8 的 generator 和 runner；Docker 中 `/workspace/data` 已由 Compose 挂载。

- [ ] **Step 1: 写入失败的 CLI 参数测试**

```python
# backend/tests/test_demo_scenario_cli.py
import os
import subprocess
import sys
from pathlib import Path


def test_run_cli_exposes_required_options() -> None:
    project_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(project_root / "scripts" / "run_demo_scenarios.py"), "--help"],
        cwd=project_root, env={**os.environ, "PYTHONPATH": str(project_root / "backend")},
        check=True, capture_output=True, text=True,
    )
    assert "--api-base-url" in result.stdout
    assert "--max-candidates" in result.stdout
    assert "--rebuild" in result.stdout
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_demo_scenario_cli.py -v`

Expected: subprocess fails because `scripts/run_demo_scenarios.py` does not exist。

- [ ] **Step 3: 实现运行 CLI**

```python
# scripts/run_demo_scenarios.py
import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend" if (PROJECT_ROOT / "backend").exists() else PROJECT_ROOT
sys.path.insert(0, str(BACKEND_ROOT))

from app.demo_scenarios.api_client import DemoApiClient
from app.demo_scenarios.runner import run_scenarios


def main() -> None:
    parser = argparse.ArgumentParser(description="Run and validate synthetic PyGeoModel demo scenarios.")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--dem-id", required=True)
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--max-candidates", type=int, default=4)
    parser.add_argument("--poll-seconds", type=float, default=2)
    parser.add_argument("--task-timeout-seconds", type=float, default=900)
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    client = DemoApiClient(args.api_base_url, poll_seconds=args.poll_seconds,
                           task_timeout_seconds=args.task_timeout_seconds)
    index = run_scenarios(args.data_dir, args.dem_id, client,
                          rebuild=args.rebuild, max_candidates=args.max_candidates)
    print(json.dumps(index, ensure_ascii=False, indent=2))
    if not all(item.get("accepted") for item in index["models"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 复制脚本进后端镜像并记录命令**

Replace `backend/Dockerfile` with this complete content so the existing working mirrors, pip timeout, application code, and new scripts all enter the image:

```dockerfile
FROM python:3.12-slim

ARG DEBIAN_MIRROR=https://mirrors.cloud.tencent.com/debian
ARG DEBIAN_SECURITY_MIRROR=https://mirrors.cloud.tencent.com/debian-security
ARG PIP_INDEX_URL=https://pypi.org/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN sed -i \
        -e "s|http://deb.debian.org/debian-security|${DEBIAN_SECURITY_MIRROR}|g" \
        -e "s|http://deb.debian.org/debian|${DEBIAN_MIRROR}|g" \
        /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends gdal-bin \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --timeout 120 --retries 5 \
    --index-url "${PIP_INDEX_URL}" \
    -r /app/requirements.txt

COPY backend/app /app/app
COPY scripts /app/scripts

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Update the backend build args in `docker-compose.yml` so Compose does not override those defaults with the retired mirror:

```yaml
args:
  DEBIAN_MIRROR: https://mirrors.cloud.tencent.com/debian
  DEBIAN_SECURITY_MIRROR: https://mirrors.cloud.tencent.com/debian-security
  PIP_INDEX_URL: https://pypi.org/simple
```

Append this exact section to `README.md`:

````markdown
## Synthetic demo scenarios

With Docker services running, generate and execute the six non-radar demo scenarios against the local DEM:

```powershell
docker compose up -d --build
docker compose exec -T backend python /app/scripts/generate_demo_scenarios.py --data-dir /workspace/data --dem-id dem_20260713_080113_884937cf
docker compose exec -T backend python /app/scripts/run_demo_scenarios.py --data-dir /workspace/data --dem-id dem_20260713_080113_884937cf --api-base-url http://127.0.0.1:8000
```

Generated scenario files and `scenario-index.json` are stored under `data/demo-scenarios/<dem-id>/`. They are synthetic runtime data and are not committed to Git.
````

- [ ] **Step 5: 运行 CLI 测试并构建 Docker 镜像**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_demo_scenario_cli.py -v
cd ..
docker compose build backend
docker compose run --rm backend python /app/scripts/run_demo_scenarios.py --help
```

Expected: test passes；镜像构建成功；容器 CLI help 包含所有运行参数。

- [ ] **Step 6: 提交 Docker 与 CLI 接入**

```powershell
git add scripts/run_demo_scenarios.py backend/tests/test_demo_scenario_cli.py backend/Dockerfile docker-compose.yml README.md docs/superpowers/plans/2026-07-14-independent-model-demo-scenarios.md
git commit -m "feat: run demo scenarios from docker"
```

---

### Task 10: 全量测试、真实任务生成与前端验收

**Files:**
- Runtime create: `data/demo-scenarios/dem_20260713_080113_884937cf/*`（Git ignored）
- Runtime create: `data/tasks/*`、`data/outputs/*`（仅后端写入，Git ignored）
- Verify only: frontend and backend source files

**Interfaces:**
- Consumes: 所有前述任务。
- Produces: 六个真实 `finished` 任务、一份全部 `accepted=true` 的 `scenario-index.json`、前端可恢复的历史记录。

- [ ] **Step 1: 运行完整后端测试**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: exit code `0`，无失败测试。

- [ ] **Step 2: 运行前端类型、单元和生产构建检查**

Run:

```powershell
cd frontend
npm test
npm run build
```

Expected: Vitest 全部通过；`vue-tsc` 与 Vite build exit code `0`。

- [ ] **Step 3: 重建并确认 Docker 服务健康**

Run:

```powershell
docker compose up -d --build
docker compose ps
curl.exe --fail --silent http://127.0.0.1:8000/api/health
```

Expected: backend/frontend 均为 `Up`；health 返回 `{"status":"ok"}`。

- [ ] **Step 4: 生成六份场景并运行真实任务**

Run:

```powershell
docker compose exec -T backend python /app/scripts/generate_demo_scenarios.py --data-dir /workspace/data --dem-id dem_20260713_080113_884937cf
docker compose exec -T backend python /app/scripts/run_demo_scenarios.py --data-dir /workspace/data --dem-id dem_20260713_080113_884937cf --api-base-url http://127.0.0.1:8000 --max-candidates 4 --task-timeout-seconds 1800
```

Expected: exit code `0`；六个模型条目均为 `status=finished`、`accepted=true`。

- [ ] **Step 5: 验证索引、任务复用和输出文件**

Run:

```powershell
$index = Get-Content -Raw 'data\demo-scenarios\dem_20260713_080113_884937cf\scenario-index.json' | ConvertFrom-Json
$index.models.PSObject.Properties | ForEach-Object { [pscustomobject]@{ Model=$_.Name; TaskId=$_.Value.task_id; Status=$_.Value.status; Accepted=$_.Value.accepted; Outputs=$_.Value.outputs.Count } } | Format-Table
docker compose exec -T backend python /app/scripts/run_demo_scenarios.py --data-dir /workspace/data --dem-id dem_20260713_080113_884937cf --api-base-url http://127.0.0.1:8000
```

Expected: 表格有六行且全部 `Accepted=True`；第二次运行复用相同 task ID，不创建重复任务。

- [ ] **Step 6: 浏览器验收六个历史任务**

Open `http://127.0.0.1:5173/PyGeoModel/` and verify, model by model:

- UAV: footprint、visible、blocked 图层可加载，航迹请求含至少 6 个航点。
- Watchpost: range、visible、blocked 均非空，遮挡率不为 0/1。
- Artillery: theoretical、reachable、terrain masked、sample points 均可见。
- Recon vehicle: footprint、visible、blocked 均可见，路线请求含至少 5 个点。
- Mobility: road mask、wheeled path、tracked path 均可见，耗时不同。
- Air corridor: threat zones、corridor path、buffer、risk samples 均可见，`route_found=true`。

Expected: 所有模型都能从历史任务中恢复，图层显隐、定位和下载正常；雷达历史与录屏数据未受影响。

- [ ] **Step 7: 检查工作树只包含预期源码改动**

Run:

```powershell
git status --short
git diff --check
```

Expected: runtime data不出现；无空白错误；现有未跟踪日志仍保持原样。
