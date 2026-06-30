# 空中安全走廊模型接口文档

## 1. 模型说明

空中安全走廊模型根据敌方防空火力部署、DEM、起点终点和飞行高度层，规划一条风险较低的空中走廊。

第一版能力：

- 支持分层 3D 空域规划。
- 高度层按 AGL 高度输入。
- 防空部署随任务 JSON 提交。
- 风险场由防空点的水平射程、高度范围和威胁等级构造。
- 支持高度层切换，用于模拟升高或降低规避威胁。
- 输出安全走廊路径、走廊缓冲区、威胁区、风险采样点。
- 任务完成后通过 `/metrics` 获取量化指标 JSON。

模型边界：

- 第一版只支持一个起点到一个终点。
- 不做多机协同、动态敌情或真实交战仿真。
- 威胁模型是工程近似风险场，不等同于真实防空系统交战模型。
- 当前规划高度层按 AGL 解释；`start.altitude_mode` 和 `end.altitude_mode` 字段保留，但第一版会按最接近的 AGL 高度层选起终点层。

## 2. 接口清单

API 前缀：

```http
/api/air-corridor
```

| 功能 | 方法 | 路径 |
| --- | --- | --- |
| 创建规划任务 | `POST` | `/api/air-corridor/planning` |
| 查询任务列表 | `GET` | `/api/air-corridor/planning` |
| 查询任务详情 | `GET` | `/api/air-corridor/planning/{task_id}` |
| 获取量化指标 JSON | `GET` | `/api/air-corridor/planning/{task_id}/metrics` |
| 查询输出文件 | `GET` | `/api/air-corridor/planning/{task_id}/outputs` |
| 下载输出文件 | `GET` | `/api/air-corridor/planning/{task_id}/outputs/{kind}` |
| 删除任务 | `DELETE` | `/api/air-corridor/planning/{task_id}` |

## 3. 调用流程

```text
上传 DEM -> 获取 dem_id -> 创建空中安全走廊任务 -> 获取 task_id -> 轮询任务详情 -> finished 后获取 /metrics
```

第三方系统只需要量化结果时，调用 `/metrics` 即可。需要地图展示时，再下载 GeoJSON 输出。

## 4. 创建任务

`POST /api/air-corridor/planning`

请求头：

```http
Content-Type: application/json
```

### 4.1 最小请求示例

```json
{
  "dem_id": "dem_xxx",
  "start": {
    "lon": 79.80513693057287,
    "lat": 31.4827708959419,
    "altitude_m": 1200,
    "altitude_mode": "agl"
  },
  "end": {
    "lon": 79.86,
    "lat": 31.52,
    "altitude_m": 1200,
    "altitude_mode": "agl"
  }
}
```

未传 `aircraft`、`altitude_layers_m`、`threats`、`planning` 时使用默认值。

### 4.2 完整请求示例

```json
{
  "dem_id": "dem_xxx",
  "start": {
    "lon": 79.80513693057287,
    "lat": 31.4827708959419,
    "altitude_m": 1200,
    "altitude_mode": "agl"
  },
  "end": {
    "lon": 79.86,
    "lat": 31.52,
    "altitude_m": 1200,
    "altitude_mode": "agl"
  },
  "aircraft": {
    "cruise_speed_kph": 180,
    "min_agl_m": 100,
    "max_agl_m": 3000,
    "max_climb_rate_mps": 8,
    "max_descent_rate_mps": 10
  },
  "altitude_layers_m": [300, 600, 900, 1200, 1800, 2400],
  "threats": [
    {
      "id": "sam_001",
      "name": "SAM Site 001",
      "lon": 79.83,
      "lat": 31.50,
      "min_range_m": 0,
      "max_range_m": 12000,
      "min_altitude_m": 100,
      "max_altitude_m": 3500,
      "threat_level": 1.0,
      "kill_zone_radius_m": 8000,
      "warning_zone_radius_m": 12000
    }
  ],
  "planning": {
    "corridor_width_m": 500,
    "horizontal_resolution_m": 250,
    "allow_altitude_change": true,
    "threat_weight": 1.0,
    "distance_weight": 0.25,
    "altitude_change_weight": 0.15,
    "terrain_clearance_weight": 0.4,
    "output_simplify_tolerance_m": 50
  }
}
```

## 5. 请求字段说明

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `dem_id` | string | 是 | 无 | 已上传 DEM 的 ID |
| `start.lon` | number | 是 | `79.80513693057287` | 起点经度，WGS84 |
| `start.lat` | number | 是 | `31.4827708959419` | 起点纬度，WGS84 |
| `start.altitude_m` | number | 否 | `1200` | 起点高度 |
| `start.altitude_mode` | string | 否 | `agl` | `agl` 或 `amsl` |
| `end.lon` | number | 是 | `79.80513693057287` | 终点经度，WGS84 |
| `end.lat` | number | 是 | `31.4827708959419` | 终点纬度，WGS84 |
| `end.altitude_m` | number | 否 | `1200` | 终点高度 |
| `end.altitude_mode` | string | 否 | `agl` | `agl` 或 `amsl` |
| `aircraft.cruise_speed_kph` | number | 否 | `180` | 巡航速度 |
| `aircraft.min_agl_m` | number | 否 | `100` | 最小离地高度 |
| `aircraft.max_agl_m` | number | 否 | `3000` | 最大离地高度 |
| `aircraft.max_climb_rate_mps` | number | 否 | `8` | 最大爬升率，第一版保留字段 |
| `aircraft.max_descent_rate_mps` | number | 否 | `10` | 最大下降率，第一版保留字段 |
| `altitude_layers_m` | array | 否 | `[300,600,900,1200,1800,2400]` | 可飞高度层，AGL，米 |
| `threats` | array | 否 | `[]` | 敌方防空部署列表 |
| `planning.corridor_width_m` | number | 否 | `500` | 输出走廊宽度 |
| `planning.horizontal_resolution_m` | number | 否 | `250` | 规划网格水平分辨率 |
| `planning.allow_altitude_change` | boolean | 否 | `true` | 是否允许高度层切换 |
| `planning.threat_weight` | number | 否 | `1.0` | 威胁风险权重 |
| `planning.distance_weight` | number | 否 | `0.25` | 距离代价权重 |
| `planning.altitude_change_weight` | number | 否 | `0.15` | 高度变化代价权重 |
| `planning.terrain_clearance_weight` | number | 否 | `0.4` | 地形净空代价权重，第一版保留字段 |
| `planning.output_simplify_tolerance_m` | number/null | 否 | `null` | 输出几何简化容差 |

## 6. 参数约束

| 字段 | 约束 |
| --- | --- |
| `lon` | `-180` 到 `180` |
| `lat` | `-90` 到 `90` |
| `altitude_m` | `0` 到 `20000` |
| `cruise_speed_kph` | 大于 `0`，小于等于 `1200` |
| `min_agl_m` | `0` 到 `20000` |
| `max_agl_m` | 大于 `0`，小于等于 `30000`，且必须大于 `min_agl_m` |
| `altitude_layers_m` | 1 到 30 个高度层 |
| `threats` | 最多 500 个威胁点 |
| `corridor_width_m` | 大于 `0`，小于等于 `10000` |
| `horizontal_resolution_m` | 大于 `0`，小于等于 `5000` |
| `threat_weight` | `0` 到 `100` |
| `distance_weight` | `0` 到 `100` |
| `altitude_change_weight` | `0` 到 `100` |
| `terrain_clearance_weight` | `0` 到 `100` |

`altitude_layers_m` 会自动去重并升序排列。

## 7. 防空威胁输入

每个威胁点结构：

```json
{
  "id": "sam_001",
  "name": "SAM Site 001",
  "lon": 79.83,
  "lat": 31.50,
  "min_range_m": 0,
  "max_range_m": 12000,
  "min_altitude_m": 100,
  "max_altitude_m": 3500,
  "threat_level": 1.0,
  "kill_zone_radius_m": 8000,
  "warning_zone_radius_m": 12000
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | string | 是 | 无 | 威胁唯一 ID |
| `name` | string/null | 否 | `null` | 威胁名称 |
| `lon` | number | 是 | 无 | 防空阵地经度 |
| `lat` | number | 是 | 无 | 防空阵地纬度 |
| `min_range_m` | number | 否 | `0` | 最小作用距离 |
| `max_range_m` | number | 是 | 无 | 最大作用距离 |
| `min_altitude_m` | number | 否 | `0` | 最小作用海拔高度 |
| `max_altitude_m` | number | 否 | `10000` | 最大作用海拔高度 |
| `threat_level` | number | 否 | `1` | 威胁等级，越大代价越高 |
| `kill_zone_radius_m` | number/null | 否 | `max_range_m * 0.7` | 高风险区半径 |
| `warning_zone_radius_m` | number/null | 否 | `max_range_m` | 告警区半径 |

约束：

- `min_range_m < max_range_m`
- `min_altitude_m < max_altitude_m`
- 如果同时传 `kill_zone_radius_m` 和 `warning_zone_radius_m`，则 `kill_zone_radius_m <= warning_zone_radius_m`
- `threat_level` 范围为 `0` 到 `10`

## 8. 创建任务响应

成功创建任务返回 `202 Accepted`。

```json
{
  "task_id": "air_corridor_task_20260630_084135_44ce9811",
  "dem_id": "dem_xxx",
  "status": "pending",
  "progress": 0,
  "message": "queued",
  "created_at": "2026-06-30T08:41:35.000000+00:00",
  "updated_at": "2026-06-30T08:41:35.000000+00:00",
  "metrics": null,
  "outputs": null,
  "output_files": [],
  "model": null,
  "warnings": [],
  "request": {
    "dem_id": "dem_xxx"
  }
}
```

调用方应保存 `task_id`。

## 9. 查询任务详情

`GET /api/air-corridor/planning/{task_id}`

任务状态：

| status | 说明 |
| --- | --- |
| `pending` | 已排队 |
| `running` | 正在计算 |
| `finished` | 已完成，可读取 `/metrics` |
| `failed` | 失败，查看 `message` |

完成后响应中包含 `metrics`、`outputs`、`output_files` 和 `model`。

## 10. 获取量化指标 JSON

`GET /api/air-corridor/planning/{task_id}/metrics`

该接口只返回指标 JSON，不返回任务外层信息。

```json
{
  "route_found": true,
  "failure_reason": null,
  "risk_score": 0.23,
  "max_segment_risk": 0.61,
  "mean_segment_risk": 0.18,
  "corridor_length_m": 18400.0,
  "estimated_time_seconds": 368.0,
  "min_terrain_clearance_m": 280.0,
  "mean_terrain_clearance_m": 920.0,
  "altitude_change_count": 3,
  "min_altitude_m": 600.0,
  "max_altitude_m": 1800.0,
  "threat_intersection_count": 1,
  "nearest_threat_distance_m": 2300.0
}
```

任务未完成时返回 `409 TASK_METRICS_NOT_READY`：

```json
{
  "detail": {
    "code": "TASK_METRICS_NOT_READY",
    "message": "Air corridor metrics are available only after the task is finished."
  }
}
```

### 10.1 指标字段说明

| 字段 | 类型 | 单位 | 说明 |
| --- | --- | --- | --- |
| `route_found` | boolean | - | 是否找到可飞走廊 |
| `failure_reason` | string/null | - | 未找到路线时的原因 |
| `risk_score` | number/null | - | 路径平均风险分值 |
| `max_segment_risk` | number/null | - | 路径采样点最大风险 |
| `mean_segment_risk` | number/null | - | 路径采样点平均风险 |
| `corridor_length_m` | number | 米 | 三维路径长度 |
| `estimated_time_seconds` | number/null | 秒 | 按巡航速度估计飞行时间 |
| `min_terrain_clearance_m` | number/null | 米 | 路径最小离地净空 |
| `mean_terrain_clearance_m` | number/null | 米 | 路径平均离地净空 |
| `altitude_change_count` | integer | 次 | 高度层切换次数 |
| `min_altitude_m` | number/null | 米 | 路径最低 AGL 高度层 |
| `max_altitude_m` | number/null | 米 | 路径最高 AGL 高度层 |
| `threat_intersection_count` | integer | 个 | 风险大于 0 的路径采样点数量 |
| `nearest_threat_distance_m` | number/null | 米 | 路径到最近威胁点的最近水平距离 |

## 11. 输出文件

### 11.1 查询输出文件

`GET /api/air-corridor/planning/{task_id}/outputs`

响应示例：

```json
[
  {
    "kind": "corridor_path_geojson",
    "label": "Air Corridor Path GeoJSON",
    "url": "/outputs/air_corridor_task_xxx/corridor_path.geojson",
    "download_url": "/api/air-corridor/planning/air_corridor_task_xxx/outputs/corridor_path_geojson",
    "filename": "corridor_path.geojson",
    "media_type": "application/geo+json",
    "size_bytes": 2048,
    "exists": true
  }
]
```

### 11.2 输出类型

| kind | 文件 | 说明 |
| --- | --- | --- |
| `corridor_path_geojson` | `corridor_path.geojson` | 安全走廊路线，LineString |
| `corridor_buffer_geojson` | `corridor_buffer.geojson` | 按 `corridor_width_m` 生成的走廊面 |
| `threat_zones_geojson` | `threat_zones.geojson` | 防空威胁区 |
| `risk_samples_geojson` | `risk_samples.geojson` | 路径采样点风险、高度、净空 |
| `cost_summary_json` | `cost_summary.json` | 各高度层风险摘要 |
| `model_metadata_json` | `model_metadata.json` | 模型参数和 DEM 投影信息 |
| `output_manifest_json` | `output_manifest.json` | 输出清单 |

### 11.3 下载单个输出

`GET /api/air-corridor/planning/{task_id}/outputs/{kind}`

示例：

```http
GET /api/air-corridor/planning/air_corridor_task_xxx/outputs/corridor_path_geojson
```

任务未完成时下载输出会返回 `409 TASK_NOT_FINISHED`。

## 12. curl 调用示例

### 12.1 创建任务

```bash
curl -X POST http://127.0.0.1:8000/api/air-corridor/planning \
  -H "Content-Type: application/json" \
  -d '{
    "dem_id": "dem_xxx",
    "start": {
      "lon": 79.80513693057287,
      "lat": 31.4827708959419,
      "altitude_m": 300,
      "altitude_mode": "agl"
    },
    "end": {
      "lon": 79.86,
      "lat": 31.52,
      "altitude_m": 300,
      "altitude_mode": "agl"
    },
    "altitude_layers_m": [300, 900, 1200],
    "threats": [
      {
        "id": "sam_001",
        "lon": 79.83,
        "lat": 31.50,
        "max_range_m": 12000,
        "min_altitude_m": 0,
        "max_altitude_m": 900,
        "threat_level": 5
      }
    ],
    "planning": {
      "horizontal_resolution_m": 500,
      "threat_weight": 10,
      "altitude_change_weight": 0.01
    }
  }'
```

### 12.2 查询任务

```bash
curl http://127.0.0.1:8000/api/air-corridor/planning/{task_id}
```

### 12.3 获取指标

```bash
curl http://127.0.0.1:8000/api/air-corridor/planning/{task_id}/metrics
```

### 12.4 查询输出文件

```bash
curl http://127.0.0.1:8000/api/air-corridor/planning/{task_id}/outputs
```

## 13. 常见错误

统一错误格式：

```json
{
  "detail": {
    "code": "ERROR_CODE",
    "message": "Human readable message."
  }
}
```

| code | HTTP | 说明 |
| --- | --- | --- |
| `DEM_NOT_FOUND` | 404 | DEM 不存在 |
| `DEM_WITHOUT_CRS` | 400/500 | DEM 缺少坐标系 |
| `AIR_CORRIDOR_START_OUTSIDE_DEM` | 400 | 起点超出 DEM |
| `AIR_CORRIDOR_END_OUTSIDE_DEM` | 400 | 终点超出 DEM |
| `AIR_CORRIDOR_NO_DATA` | 400 | 起点或终点落在 NoData |
| `RANGE_OUTSIDE_DEM` | 400 | 规划范围和 DEM 不相交 |
| `TASK_NOT_FOUND` | 404 | 任务不存在 |
| `TASK_METRICS_NOT_READY` | 409 | 任务未完成，不能读取指标 |
| `TASK_NOT_FINISHED` | 409 | 任务未完成，不能下载输出 |
| `OUTPUT_NOT_FOUND` | 404 | 指定输出文件不存在 |

## 14. 第三方系统集成建议

- 先上传 DEM 并保存 `dem_id`。
- 创建任务后保存 `task_id`。
- 每 1-3 秒轮询任务详情；大 DEM 或高分辨率规划可放宽到 3-5 秒。
- 任务 `status=finished` 后再读取 `/metrics`。
- 只需要量化结果时，不需要下载 GeoJSON 输出。
- 起点、终点和威胁区域应在 DEM 覆盖范围附近，否则风险场可能被裁剪。
- `horizontal_resolution_m` 越小，路径越精细，但计算量越大。
- `altitude_layers_m` 层数越多，越能体现高度规避，但计算量越大。
- `threat_weight` 越大，路线越倾向绕开威胁区；`distance_weight` 越大，路线越倾向短距离。
