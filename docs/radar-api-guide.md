# 雷达任务 API 调用手册

更新日期：2026-08-11
适用范围：PyGeoModel 的单雷达与多雷达统一任务接口。

本手册是雷达任务接口的人工可读说明。运行服务的 OpenAPI 是最终机器可读契约：`GET http://<host>:8000/openapi.json`；交互式页面为 `http://<host>:8000/docs`。

## 1. 基础约定

本地默认服务地址：

```text
API: http://127.0.0.1:8000
Web: http://127.0.0.1:5173
```

以下示例假定：

```bash
export API_BASE=http://127.0.0.1:8000
```

除产物下载外，请求和响应均使用 JSON。任务创建与重跑是异步操作：保存返回的 `task_id`，再轮询任务详情直到任务终态。不要以固定等待时间代替状态轮询。

所有雷达任务都需要已存在的 `dem_id`。单雷达任务使用 `task_type: "single"`，多雷达任务使用 `task_type: "multi"`；服务通过该字段选择计算模型。

> 已移除的路径：`/api/radar/coverage/*` 与 `/api/radar/multi-coverage/*`。客户端必须迁移到本文的 `/api/radar/tasks/*`，旧路径会返回 `404`。

## 2. 创建与管理任务

### 2.1 创建单雷达任务

`POST /api/radar/tasks`

```bash
curl -sS -X POST "$API_BASE/api/radar/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "single",
    "dem_id": "dem_example",
    "radar": {"lon": 102.1000, "lat": 29.6000, "height_m": 15},
    "target": {"height_m": 0},
    "coverage": {
      "max_range_m": 50000,
      "scan_mode": "omni",
      "azimuth_deg": 0,
      "beam_width_deg": 360
    }
  }'
```

### 2.2 创建多雷达任务

`POST /api/radar/tasks`

```bash
curl -sS -X POST "$API_BASE/api/radar/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "multi",
    "dem_id": "dem_example",
    "presentation_mode": "aggregate",
    "radars": [
      {
        "radar_id": "R1",
        "radar": {"lon": 102.1000, "lat": 29.6000, "height_m": 15},
        "target": {"height_m": 0},
        "coverage": {"max_range_m": 50000, "scan_mode": "omni"}
      },
      {
        "radar_id": "R2",
        "radar": {"lon": 102.2500, "lat": 29.6600, "height_m": 20},
        "target": {"height_m": 0},
        "coverage": {"max_range_m": 50000, "scan_mode": "omni"}
      }
    ]
  }'
```

`radars` 必须有 2 至 256 个站点，且 `radar_id` 唯一。`presentation_mode` 为 `aggregate` 时生成联合覆盖、重叠与盲区；`cooperative_3d` 还生成协同三维资产，且只允许 2 至 5 个站点。

创建成功返回 `202 Accepted`。响应中包含 `task_id`、`task_type`、状态和任务摘要。

### 2.3 统一生命周期端点

| 操作 | 方法与路径 | 说明 |
| --- | --- | --- |
| 列表 | `GET /api/radar/tasks?task_type=single|multi` | 不传筛选参数时返回两类任务的合并列表。 |
| 创建 | `POST /api/radar/tasks` | 使用 `task_type` 区分单/多雷达请求。 |
| 详情与轮询 | `GET /api/radar/tasks/{task_id}` | 返回任务状态、指标、产物和错误。 |
| 重跑 | `POST /api/radar/tasks/{task_id}/rerun` | 需要 `Idempotency-Key` 请求头。 |
| 删除 | `DELETE /api/radar/tasks/{task_id}` | 删除任务记录与可清理产物。 |
| 取消 | `POST /api/radar/tasks/{task_id}/cancel` | 仅排队或执行中的本服务任务可取消。 |
| 产物列表 | `GET /api/radar/tasks/{task_id}/outputs` | 发现可用产物及下载路径。 |
| 下载产物 | `GET /api/radar/tasks/{task_id}/outputs/{kind}` | 下载指定产物。 |

重跑请求示例：

```bash
curl -sS -X POST "$API_BASE/api/radar/tasks/task_example/rerun" \
  -H "Idempotency-Key: rerun-task-example-20260811-001"
```

同一用户动作的网络重试必须复用同一个幂等键；显式发起新的重跑则使用新键。键长度为 8 至 128 个字符。

任务状态为 `pending`、`running`、`finished` 或 `failed`；多雷达任务还可能是 `partial`。`partial` 不表示完全成功，客户端应读取站点结果和 `warnings` 后决定可展示的产物。

## 3. 单雷达与多雷达专属端点

| 任务类型 | 方法与路径 | 说明 |
| --- | --- | --- |
| 单雷达 | `GET /api/radar/tasks/{task_id}/metrics` | 读取覆盖统计指标。 |
| 单雷达 | `GET /api/radar/tasks/{task_id}/profile?lon=...&lat=...&samples=160` | 读取一条地形剖面。 |
| 单雷达 | `POST /api/radar/tasks/{task_id}/profiles` | 批量剖面。 |
| 多雷达 | `GET /api/radar/tasks/{task_id}/radars` | 读取各站点概览。 |
| 多雷达 | `GET /api/radar/tasks/{task_id}/radars/{radar_id}` | 读取指定站点。 |
| 多雷达 | `POST /api/radar/tasks/{task_id}/radars/{radar_id}/detail` | 创建指定站点的详细单雷达计算。 |
| 通用 | `POST /api/radar/fusion` | 对已有单雷达任务执行融合分析。 |

在不支持该任务类型的端点上，服务返回 `409` 和 `TASK_VARIANT_UNSUPPORTED`。不要根据任务 ID 前缀在客户端自行分派功能，应使用任务详情的 `task_type`。

## 4. 单目标评估

`POST /api/radar/tasks/{task_id}/evaluate-target`

```bash
curl -sS -X POST "$API_BASE/api/radar/tasks/task_example/evaluate-target" \
  -H "Content-Type: application/json" \
  -d '{
    "x": 102.1200,
    "y": 29.6200,
    "z": 3250,
    "target_type": "aircraft"
  }'
```

`x`、`y` 是 WGS84 经度、纬度，`z` 是米为单位的 AMSL 海拔高度。统一响应使用以下形式：

```json
{
  "task_id": "task_example",
  "task_type": "single",
  "detected": true,
  "detail": {
    "detectable": true,
    "reason": "detectable",
    "distance_m": 2100.4,
    "terrain_blocked": false
  },
  "contributors": []
}
```

单雷达响应中 `detail` 是详细三维评估，含距离、方位、地形、最小/最大可探测高度和不可探测原因。多雷达响应中 `detail` 为 `null`，`contributors` 给出各站点的判定：

```json
{
  "task_id": "multi_task_example",
  "task_type": "multi",
  "detected": true,
  "detail": null,
  "contributors": [
    {"radar_id": "R1", "detected": true},
    {"radar_id": "R2", "detected": false}
  ]
}
```

多雷达评估当前根据各站可见性栅格判定，目标高度不会影响其 `contributors` 结果；这与单雷达详细三维评估不同。

## 5. 批量目标评估

`POST /api/radar/tasks/{task_id}/evaluate-targets`

一次请求可提交 1 至 500 个目标，且 `target_id` 必须唯一。每个目标包括：

| 字段 | 说明 |
| --- | --- |
| `target_id` | 调用方提供的唯一标识，长度 1 至 128。 |
| `x` / `y` | WGS84 经度/纬度。 |
| `altitude_reference` | `amsl` 或 `agl`。 |
| `altitude_m` | `amsl` 时必填；`agl` 时可省略，默认 0。 |
| `target_type` | 可选的目标类型。 |

```bash
curl -sS -X POST "$API_BASE/api/radar/tasks/task_example/evaluate-targets" \
  -H "Content-Type: application/json" \
  -d '{
    "targets": [
      {
        "target_id": "aircraft-001",
        "x": 102.1200,
        "y": 29.6200,
        "altitude_reference": "amsl",
        "altitude_m": 3250,
        "target_type": "aircraft"
      },
      {
        "target_id": "ground-001",
        "x": 102.1300,
        "y": 29.6250,
        "altitude_reference": "agl",
        "altitude_m": 20
      }
    ]
  }'
```

单雷达任务会把 `agl` 高度加上该目标位置的 DEM 高程后再执行三维评估。多雷达任务保留其可见性栅格语义，不执行 DEM 高度换算。

请求整体参数无效时服务返回 `422`。单个目标在处理时失败不会中断其余目标；成功与失败行分别放在 `results` 和 `errors`：

```json
{
  "task_id": "task_example",
  "requested_count": 2,
  "succeeded_count": 1,
  "failed_count": 1,
  "detected_count": 1,
  "results": [
    {
      "target_id": "aircraft-001",
      "altitude_reference": "amsl",
      "source_altitude_m": 3250,
      "evaluation": {
        "task_id": "task_example",
        "task_type": "single",
        "detected": true,
        "detail": {"detectable": true, "reason": "detectable"},
        "contributors": []
      }
    }
  ],
  "errors": [
    {
      "target_id": "ground-001",
      "x": 102.1300,
      "y": 29.6250,
      "code": "TARGET_TERRAIN_UNAVAILABLE",
      "message": "Target terrain elevation is unavailable."
    }
  ]
}
```

`detected_count` 只统计成功行中 `evaluation.detected: true` 的数量。处理批量数据时请以 `target_id` 关联响应，而不是假定 `results` 与输入数组等长或顺序相同。

## 6. 产物与错误处理

使用任务详情或 outputs 列表返回的 `download_path` 下载产物；不要手工拼接文件名。例如：

```bash
curl -fL "$API_BASE/api/radar/tasks/task_example/outputs/visible_geojson" \
  -o visible.geojson
```

常见状态码：

| 状态码 | 调用方处理 |
| --- | --- |
| `200` | 查询、评估、下载前置检查或重跑成功。 |
| `202` | 任务已接受，开始轮询详情。 |
| `400` | 任务 ID 格式无效；修正路径。 |
| `404` | 任务、站点、DEM 或旧版路径不存在；不要重试同一请求。 |
| `409` | 任务状态未满足前置条件或端点不支持该任务类型。 |
| `422` | 请求字段校验失败；修正输入。 |
| `500` / `503` | 服务端或依赖异常；记录任务 ID 后有限次数退避重试。 |

业务错误通常为：

```json
{
  "detail": {
    "code": "SOME_ERROR_CODE",
    "message": "可读错误说明"
  }
}
```

源码入口：

- `backend/app/api/radar.py`
- `backend/app/schemas/radar.py`
- `backend/app/services/target_evaluation.py`
