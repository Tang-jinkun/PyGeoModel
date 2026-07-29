# 雷达覆盖与多雷达协同 API 对接手册

更新日期：2026-07-29  
适用范围：PyGeoModel FastAPI 服务中的雷达覆盖与多雷达协同接口。

本手册面向调用服务的前端、算法编排和第三方系统开发者。接口的最终机器可读契约以运行服务的 OpenAPI 为准：`GET http://<host>:8000/openapi.json`，交互式页面为 `http://<host>:8000/docs`。

## 1. 服务地址与调用约定

本地默认地址：

```text
API:  http://127.0.0.1:8000
Web:  http://127.0.0.1:5173
```

Docker Compose 默认将 API 的 `8000` 和 Web 的 `5173` 绑定到本机。前端通过 `/api` 代理访问后端；外部调用方应直接使用 API 基地址。

全部示例假定：

```bash
export API_BASE=http://127.0.0.1:8000
```

所有请求和响应均使用 JSON，下载端点除外。创建和重新运行均为异步操作：先取得任务记录，再轮询任务详情直到结束。不要通过固定等待时间判断计算已经完成。

调用雷达接口前需要一个可用 `dem_id`。DEM 的上传、管理与列表接口不在本文范围内；请从系统的数据接口或工作台中取得已存在 DEM 的 ID。

## 2. 任务状态与响应读取

单雷达任务的主要状态为：`pending`、`running`、`finished`、`failed`。多雷达任务还可能处于 `partial`，表示部分站点或部分结果可用但任务未完全成功。

推荐轮询间隔为 1 至 3 秒；运行时间较长时可逐步退避到 5 秒。只有 `finished` 表示成功完成；`failed` 和 `partial` 都必须读取 `error`、`warnings`、站点结果或日志后再决定是否继续处理。

产物描述通常包含：

```json
{
  "kind": "visible_geojson",
  "label": "可见区",
  "mime_type": "application/geo+json",
  "size_bytes": 12345,
  "download_path": "/api/radar/coverage/T-xxx/outputs/visible_geojson",
  "exists": true
}
```

请以 `exists` 和服务返回的 `download_path` 为准。不要根据文件名或类型手工猜测下载 URL。

## 3. 单雷达覆盖

### 3.1 创建任务

`POST /api/radar/coverage`

最小可用请求示例：

```bash
curl -sS -X POST "$API_BASE/api/radar/coverage" \
  -H "Content-Type: application/json" \
  -d '{
    "dem_id": "dem_example",
    "radar": {
      "lon": 102.1000,
      "lat": 29.6000,
      "height_m": 15
    },
    "target": { "height_m": 0 },
    "coverage": {
      "max_range_m": 50000,
      "scan_mode": "omni",
      "azimuth_deg": 0,
      "beam_width_deg": 360
    }
  }'
```

关键字段：

| 路径 | 类型与限制 | 说明 |
| --- | --- | --- |
| `dem_id` | string | 已存在的 DEM 标识。 |
| `radar.lon` / `radar.lat` | number，WGS84 | 雷达站坐标。 |
| `radar.height_m` | number，`>= 0` | 雷达天线离地高度。 |
| `target.height_m` | number，`>= 0` | 目标离地高度。 |
| `coverage.max_range_m` | number，`(0, 100000]` | 最大计算距离，单位米。 |
| `coverage.scan_mode` | `omni` / `sector` | 全向或扇区扫描。 |
| `coverage.azimuth_deg` | number，`[0, 360)` | 扇区中心方位角。 |
| `coverage.beam_width_deg` | number，`(0, 360]` | 水平波束宽度。 |

`advanced` 可选。常用字段为 `use_curvature`、`refraction_coeff`、`tolerance_m`、`voxel_grid_size`、`vertical_levels`、`voxel_max_cells`、`min_elevation_deg`、`max_elevation_deg`、`visual_dome` 与 `height_layers_m`。网格和体素上限越高，任务消耗越大；调用方应按产品场景限制这些值。

`radar_params` 可选，可提供频率、发射功率、天线增益、接收机灵敏度、RCS、损耗、脉冲参数、PRF、噪声系数、检测概率与虚警概率等雷达方程参数。仅当相关参数完整时，服务才会产生相应的雷达方程推导结果；不要把缺省参数解释为物理性能结论。

成功创建返回 `201 Created`，其中的 `task_id` 用于后续所有请求。

### 3.2 查询、重跑与删除

| 操作 | 方法与路径 | 说明 |
| --- | --- | --- |
| 列表 | `GET /api/radar/coverage` | 获取单雷达任务列表。 |
| 详情/轮询 | `GET /api/radar/coverage/{task_id}` | 读取状态、摘要、产物与错误。 |
| 重跑 | `POST /api/radar/coverage/{task_id}/rerun` | 使用任务输入重新创建计算。 |
| 删除 | `DELETE /api/radar/coverage/{task_id}` | 删除任务记录及其可清理资源。 |

重跑必须提供唯一的幂等键：

```bash
curl -sS -X POST "$API_BASE/api/radar/coverage/T-example/rerun" \
  -H "Idempotency-Key: rerun-T-example-20260729-001"
```

`Idempotency-Key` 长度必须为 8 至 128 个字符。对同一个用户动作重试时复用同一键；用户明确再次发起一次新重跑时使用新键。

### 3.3 指标、剖面和目标评估

| 功能 | 方法与路径 | 备注 |
| --- | --- | --- |
| 统计指标 | `GET /api/radar/coverage/{task_id}/metrics` | 仅在任务具备可读结果时调用。 |
| 单条剖面 | `GET /api/radar/coverage/{task_id}/profile?lon=...&lat=...&samples=160` | `samples` 为剖面采样数。 |
| 批量剖面 | `POST /api/radar/coverage/{task_id}/profiles` | 适合一次计算多个目标点。 |
| 目标评估 | `POST /api/radar/coverage/{task_id}/evaluate-target` | 返回指定目标的可见性评估。 |
| 覆盖融合 | `POST /api/radar/fusion` | 对已有单雷达结果执行融合分析。 |

目标评估请求示例：

```bash
curl -sS -X POST "$API_BASE/api/radar/coverage/T-example/evaluate-target" \
  -H "Content-Type: application/json" \
  -d '{
    "x": 102.1200,
    "y": 29.6200,
    "z": 3250,
    "target_type": "aircraft"
  }'
```

其中 `x` 和 `y` 是 WGS84 经度、纬度，`z` 是以米为单位的**平均海平面海拔高度（AMSL）**。不要把单雷达任务配置中的 `target.height_m` 直接填入 `z`，后者不是离地高度。

### 3.4 单雷达产物

使用下列端点发现并下载产物：

```text
GET /api/radar/coverage/{task_id}/outputs
GET /api/radar/coverage/{task_id}/outputs/{kind}
```

常见 `kind`：`viewshed_tif`、`visible_geojson`、`blocked_geojson`、`range_geojson`、`min_visible_height_tif`、`height_layers_manifest_json`、`scene_glb`、`radar_platform_glb`、`model_metadata_json` 与 `output_manifest_json`。体素和裁剪体还可能出现相应的 manifest JSON 与 BIN 数据。

下载时优先使用详情或 outputs 列表返回的 `download_path`。例如：

```bash
curl -fL "$API_BASE/api/radar/coverage/T-example/outputs/visible_geojson" \
  -o visible.geojson
```

## 4. 多雷达协同

### 4.1 创建任务

`POST /api/radar/multi-coverage`

聚合覆盖示例：

```bash
curl -sS -X POST "$API_BASE/api/radar/multi-coverage" \
  -H "Content-Type: application/json" \
  -d '{
    "dem_id": "dem_example",
    "presentation_mode": "aggregate",
    "radars": [
      {
        "radar_id": "R1",
        "lon": 102.1000,
        "lat": 29.6000,
        "height_m": 15,
        "target_height_m": 0,
        "max_range_m": 50000,
        "scan_mode": "omni"
      },
      {
        "radar_id": "R2",
        "lon": 102.2500,
        "lat": 29.6600,
        "height_m": 20,
        "target_height_m": 0,
        "max_range_m": 50000,
        "scan_mode": "omni"
      }
    ]
  }'
```

`radars` 数量为 2 至 256，且每项 `radar_id` 唯一。每个站点可独立设置范围、扫描参数、高级参数和可选的雷达方程参数。

`presentation_mode` 支持：

- `aggregate`：生成联合覆盖、重叠、盲区和覆盖次数等汇总结果。
- `cooperative_3d`：除聚合结果外，生成每站探测域与平台 GLB，以及协同交会 GLB；此模式只允许 2 至 5 个站点。

### 4.2 多雷达任务与站点详情

| 操作 | 方法与路径 | 说明 |
| --- | --- | --- |
| 列表 | `GET /api/radar/multi-coverage` | 获取协同任务列表。 |
| 详情/轮询 | `GET /api/radar/multi-coverage/{task_id}` | 读取聚合状态、各站结果、产物和 `scene_assets`。 |
| 重跑 | `POST /api/radar/multi-coverage/{task_id}/rerun` | 需 `Idempotency-Key` 请求头。 |
| 删除 | `DELETE /api/radar/multi-coverage/{task_id}` | 删除任务。 |
| 站点列表 | `GET /api/radar/multi-coverage/{task_id}/radars` | 读取每站概览。 |
| 站点详情 | `GET /api/radar/multi-coverage/{task_id}/radars/{radar_id}` | 读取指定雷达站的详细结果。 |
| 站点详细计算 | `POST /api/radar/multi-coverage/{task_id}/radars/{radar_id}/detail` | 请求生成或刷新指定站点详细结果。 |
| 目标评估 | `POST /api/radar/multi-coverage/{task_id}/evaluate-target` | 在协同任务上评估指定目标。 |

多雷达目标评估也使用 `x`、`y`、`z`；`z` 同样是 AMSL 海拔高度。

### 4.3 多雷达产物与场景资产

多雷达下载端点：

```text
GET /api/radar/multi-coverage/{task_id}/outputs
GET /api/radar/multi-coverage/{task_id}/outputs/{kind}
```

典型汇总产物：

| `kind` | 内容 |
| --- | --- |
| `visible_union_geojson` | 至少一个站点可见的联合区域。 |
| `overlap_geojson` | 多站同时覆盖的重叠区域。 |
| `blind_geojson` | 未被任何站点覆盖的区域。 |
| `coverage_count_geojson` | 每个位置的覆盖站点数。 |
| `stations_geojson` | 雷达站空间要素。 |
| `station_summaries_json` | 各站点摘要。 |
| `fusion_scene_glb` | 汇总三维场景。 |
| `cooperative_intersection_glb` | 协同三维的交会资产。 |

对于 `cooperative_3d` 任务，详情响应还会包含 `scene_assets`。它是前端或三维客户端应优先消费的规范化场景资产列表：

```json
{
  "asset_id": "T-multi-001:R1:scene_glb",
  "task_id": "T-multi-001",
  "radar_id": "R1",
  "kind": "scene_glb",
  "label": "雷达站 R1 探测域",
  "render_tier": "world",
  "file": {
    "download_path": "/api/radar/multi-coverage/T-multi-001/outputs/...",
    "exists": true
  }
}
```

`scene_assets` 的规则：

- `kind: scene_glb`：雷达探测域，通常以 `render_tier: world` 呈现。
- `kind: radar_platform_glb`：雷达设备模型，通常以 `render_tier: equipment` 呈现。
- 协同交会资产也使用 `kind: scene_glb`，但以 `render_tier: emphasis` 呈现，并带有不为空的协同标签。
- `radar_id` 为站点资产所属的站点 ID；任务级协同交会资产可以没有 `radar_id`。
- 必须使用嵌套 `file.download_path` 下载。不要把规范化的 `kind: scene_glb` 直接拼为 `/outputs/scene_glb`，因为它可能映射到底层不同的物理产物类型。

推荐客户端流程：先渲染 GeoJSON 聚合结果，再遍历 `scene_assets`，跳过 `file.exists: false` 的项，按 `render_tier` 进行三维层级或遮挡策略配置，并为每个资产提供独立的显隐与聚焦能力。

## 5. 错误处理与重试

| 状态码 | 含义与客户端处理 |
| --- | --- |
| `201` | 任务创建成功，保存 `task_id` 并开始轮询。 |
| `200` | 查询、评估、下载前置检查或重跑成功。 |
| `404` | 任务、站点或 DEM 不存在；不要重试相同参数。 |
| `409` | 并发状态或幂等请求冲突；读取任务详情后决定下一步。 |
| `410` | 任务记录存在，但请求的产物已不可用；从 outputs/详情重新发现可用文件。 |
| `422` | 参数校验失败；展示字段错误，不进行自动重试。 |
| `500` | 服务端计算或未处理错误；记录 request ID/任务 ID 并查看服务端日志。 |
| `503` | 服务暂不可用、依赖尚未就绪或上游不可用；指数退避重试，并为用户保留任务状态入口。 |

业务错误通常以以下形式返回：

```json
{
  "detail": {
    "code": "SOME_ERROR_CODE",
    "message": "可读错误说明"
  }
}
```

参数校验错误遵循 FastAPI 的 `422` 结构，`detail` 为错误项列表。客户端应保留原始响应用于诊断，同时向用户显示可理解的字段级提示。

重试原则：

1. 对网络错误和 `503` 使用有限次数的指数退避。
2. 创建任务的网络超时不应立刻盲目重复提交；先根据客户端保存的任务 ID、请求追踪信息或服务端幂等能力确认结果。
3. 仅重跑端点要求 `Idempotency-Key`；同一用户动作的重试复用相同键。
4. `422`、明确的 `404` 和业务校验错误需要修正输入，而不是自动重试。

## 6. 前端集成建议

1. 提交后立即把服务返回的任务对象写入任务列表，并启动轮询。
2. 仅在状态为 `finished` 时启用常规“查看图层”和“下载”操作；对 `partial` 单独展示可用站点和警告。
3. 渲染层以服务端产物列表为源，不在前端硬编码“某任务一定有某文件”。
4. 对多雷达协同，分别维护聚合 GeoJSON 图层和 `scene_assets` 三维资产的开关、加载状态与聚焦操作。
5. 使用 `download_path` 作为相对 API 路径，并与当前 API 基地址拼接；不要依赖服务器本地文件路径。
6. 对 GLB 加载失败记录 `task_id`、`asset_id`、`download_path`、HTTP 状态和解析错误，便于定位是文件不可用、网关问题还是客户端渲染问题。

## 7. 版本兼容

较早的多雷达历史任务可能没有 `scene_assets`，也可能没有雷达平台或协同交会 GLB。客户端应把字段缺失视为“该任务没有该类资产”，而不是解析失败；需要新资产时调用对应任务的重跑接口。雷达平台的显示倍率属于纯可视化元数据，不应参与任何距离、面积或覆盖概率计算。

接口实现与数据模型的源码入口：

- `backend/app/api/radar.py`
- `backend/app/schemas/radar.py`
- `backend/app/services/artifact_contracts.py`

