# 车辆可达能力模型接口文档

## 1. 模型说明

车辆可达能力模型用于评估轮式车辆和履式车辆从起点到终点的通行时间，并判断哪类车辆更优。

第一版能力：

- 输入 DEM，基于坡度计算通行代价。
- 输入起点、终点，计算最短通行时间路径。
- 同时评估轮式车辆和履式车辆。
- 可选输入路网 GeoJSON，路网区域会提升通行速度。
- 返回量化指标 JSON。
- 输出轮式/履式路径 GeoJSON、路网影响区 GeoJSON、模型元数据和输出清单。

模型边界：

- 第一版只支持一个起点到一个终点。
- 路网随任务请求提交，不单独上传为路网库。
- 通行时间是 DEM 坡度和道路加权的工程近似，不是车辆动力学仿真。
- 坡度超过车辆 `max_slope_deg` 的栅格视为不可通行。

## 2. 接口清单

API 前缀：

```http
/api/mobility
```

| 功能 | 方法 | 路径 |
| --- | --- | --- |
| 创建可达能力任务 | `POST` | `/api/mobility/accessibility` |
| 查询任务列表 | `GET` | `/api/mobility/accessibility` |
| 查询任务详情 | `GET` | `/api/mobility/accessibility/{task_id}` |
| 获取量化指标 JSON | `GET` | `/api/mobility/accessibility/{task_id}/metrics` |
| 查询输出文件 | `GET` | `/api/mobility/accessibility/{task_id}/outputs` |
| 下载输出文件 | `GET` | `/api/mobility/accessibility/{task_id}/outputs/{kind}` |
| 删除任务 | `DELETE` | `/api/mobility/accessibility/{task_id}` |

## 3. 调用流程

```text
上传 DEM -> 获取 dem_id -> 创建可达能力任务 -> 获取 task_id -> 轮询任务详情 -> finished 后获取 /metrics
```

第三方系统只需要量化指标时，调用到 `/metrics` 即可，不需要下载输出文件。

## 4. 创建任务

`POST /api/mobility/accessibility`

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
    "lat": 31.4827708959419
  },
  "end": {
    "lon": 79.82,
    "lat": 31.49
  }
}
```

未传 `vehicles` 时使用默认轮式/履式参数。未传 `road_network` 时只按 DEM 越野通行计算。

### 4.2 完整请求示例

```json
{
  "dem_id": "dem_xxx",
  "start": {
    "lon": 79.80513693057287,
    "lat": 31.4827708959419
  },
  "end": {
    "lon": 79.82,
    "lat": 31.49
  },
  "vehicles": {
    "wheeled": {
      "enabled": true,
      "base_speed_kph": 45,
      "max_slope_deg": 18,
      "slope_penalty": 2.2,
      "road_speed_multiplier": 1.5,
      "offroad_speed_multiplier": 0.65
    },
    "tracked": {
      "enabled": true,
      "base_speed_kph": 35,
      "max_slope_deg": 30,
      "slope_penalty": 1.4,
      "road_speed_multiplier": 1.25,
      "offroad_speed_multiplier": 0.85
    }
  },
  "road_network": {
    "geojson": {
      "type": "FeatureCollection",
      "features": [
        {
          "type": "Feature",
          "properties": {
            "class": "primary"
          },
          "geometry": {
            "type": "LineString",
            "coordinates": [
              [79.806, 31.483],
              [79.812, 31.486],
              [79.82, 31.49]
            ]
          }
        }
      ]
    },
    "road_buffer_m": 20,
    "road_classes": {
      "primary": 1.4,
      "secondary": 1.25,
      "track": 1.1
    }
  },
  "analysis": {
    "allow_diagonal": true,
    "max_search_radius_m": null,
    "output_simplify_tolerance_m": 30
  }
}
```

### 4.3 请求字段说明

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `dem_id` | string | 是 | 无 | 已上传 DEM 的 ID |
| `start.lon` | number | 是 | 无 | 起点经度，WGS84 |
| `start.lat` | number | 是 | 无 | 起点纬度，WGS84 |
| `end.lon` | number | 是 | 无 | 终点经度，WGS84 |
| `end.lat` | number | 是 | 无 | 终点纬度，WGS84 |
| `vehicles.wheeled.enabled` | boolean | 否 | `true` | 是否计算轮式车辆 |
| `vehicles.wheeled.base_speed_kph` | number | 否 | `45` | 轮式基础速度，公里/小时 |
| `vehicles.wheeled.max_slope_deg` | number | 否 | `18` | 轮式最大可通行坡度，度 |
| `vehicles.wheeled.slope_penalty` | number | 否 | `2.2` | 坡度速度惩罚系数 |
| `vehicles.wheeled.road_speed_multiplier` | number | 否 | `1.5` | 道路区域速度倍率 |
| `vehicles.wheeled.offroad_speed_multiplier` | number | 否 | `0.65` | 越野区域速度倍率 |
| `vehicles.tracked.enabled` | boolean | 否 | `true` | 是否计算履式车辆 |
| `vehicles.tracked.base_speed_kph` | number | 否 | `35` | 履式基础速度，公里/小时 |
| `vehicles.tracked.max_slope_deg` | number | 否 | `30` | 履式最大可通行坡度，度 |
| `vehicles.tracked.slope_penalty` | number | 否 | `1.4` | 坡度速度惩罚系数 |
| `vehicles.tracked.road_speed_multiplier` | number | 否 | `1.25` | 道路区域速度倍率 |
| `vehicles.tracked.offroad_speed_multiplier` | number | 否 | `0.85` | 越野区域速度倍率 |
| `road_network.geojson` | object/null | 否 | `null` | 路网 GeoJSON |
| `road_network.road_buffer_m` | number | 否 | `20` | 道路影响缓冲距离，米 |
| `road_network.road_classes` | object | 否 | 见默认值 | 不同道路等级的额外速度倍率 |
| `analysis.allow_diagonal` | boolean | 否 | `true` | 是否允许 8 邻域斜向移动 |
| `analysis.max_search_radius_m` | number/null | 否 | `null` | 起终点外扩搜索半径，空值时自动估算 |
| `analysis.output_simplify_tolerance_m` | number/null | 否 | `null` | 输出路径简化容差，米 |

### 4.4 参数约束

| 字段 | 约束 |
| --- | --- |
| `lon` | `-180` 到 `180` |
| `lat` | `-90` 到 `90` |
| `base_speed_kph` | 大于 `0`，小于等于 `150` |
| `max_slope_deg` | `0` 到 `60` |
| `slope_penalty` | `0` 到 `10` |
| `road_speed_multiplier` | 大于 `0`，小于等于 `5` |
| `offroad_speed_multiplier` | 大于 `0`，小于等于 `5` |
| `road_buffer_m` | `0` 到 `500` |
| `max_search_radius_m` | 大于 `0`，小于等于 `500000` |
| `output_simplify_tolerance_m` | 大于等于 `0` |

`vehicles.wheeled.enabled` 和 `vehicles.tracked.enabled` 不能同时为 `false`。

## 5. 路网 GeoJSON 说明

第一版支持：

- `FeatureCollection`
- `LineString`
- `MultiLineString`

每个道路 Feature 可在 `properties` 中使用以下任一字段表示道路等级：

- `class`
- `road_class`
- `highway`

示例：

```json
{
  "type": "Feature",
  "properties": {
    "class": "primary"
  },
  "geometry": {
    "type": "LineString",
    "coordinates": [
      [79.806, 31.483],
      [79.812, 31.486],
      [79.82, 31.49]
    ]
  }
}
```

道路等级倍率来自 `road_network.road_classes`。如果道路等级未命中，默认使用 `1.2`。

模型会将道路按 `road_buffer_m` 缓冲后栅格化，道路影响区内车辆速度会乘以车辆自身的 `road_speed_multiplier` 和道路等级倍率。

## 6. 创建任务响应

成功创建任务返回 `202 Accepted`。

```json
{
  "task_id": "mobility_task_20260630_082357_dbd4736f",
  "dem_id": "dem_xxx",
  "status": "pending",
  "progress": 0,
  "message": "queued",
  "created_at": "2026-06-30T08:23:57.000000+00:00",
  "updated_at": "2026-06-30T08:23:57.000000+00:00",
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

## 7. 查询任务详情

`GET /api/mobility/accessibility/{task_id}`

任务状态：

| status | 说明 |
| --- | --- |
| `pending` | 已排队 |
| `running` | 正在计算 |
| `finished` | 已完成，可读取 `/metrics` |
| `failed` | 失败，查看 `message` |

完成后响应示例：

```json
{
  "task_id": "mobility_task_20260630_082357_dbd4736f",
  "dem_id": "dem_xxx",
  "status": "finished",
  "progress": 100,
  "message": "finished",
  "metrics": {
    "winner": "tracked",
    "time_saving_seconds": 620.0,
    "time_saving_ratio": 0.18,
    "wheeled": {
      "reachable": true,
      "travel_time_seconds": 3420.0,
      "travel_distance_m": 18500.0,
      "average_speed_kph": 19.5,
      "road_distance_m": 6200.0,
      "offroad_distance_m": 12300.0,
      "max_slope_deg": 17.2,
      "mean_slope_deg": 6.8,
      "failure_reason": null
    },
    "tracked": {
      "reachable": true,
      "travel_time_seconds": 2800.0,
      "travel_distance_m": 17800.0,
      "average_speed_kph": 22.9,
      "road_distance_m": 4800.0,
      "offroad_distance_m": 13000.0,
      "max_slope_deg": 24.5,
      "mean_slope_deg": 8.1,
      "failure_reason": null
    }
  }
}
```

## 8. 获取量化指标 JSON

`GET /api/mobility/accessibility/{task_id}/metrics`

该接口只返回指标 JSON，不返回任务外层信息。

```json
{
  "winner": "tracked",
  "time_saving_seconds": 620.0,
  "time_saving_ratio": 0.18,
  "wheeled": {
    "reachable": true,
    "travel_time_seconds": 3420.0,
    "travel_distance_m": 18500.0,
    "average_speed_kph": 19.5,
    "road_distance_m": 6200.0,
    "offroad_distance_m": 12300.0,
    "max_slope_deg": 17.2,
    "mean_slope_deg": 6.8,
    "failure_reason": null
  },
  "tracked": {
    "reachable": true,
    "travel_time_seconds": 2800.0,
    "travel_distance_m": 17800.0,
    "average_speed_kph": 22.9,
    "road_distance_m": 4800.0,
    "offroad_distance_m": 13000.0,
    "max_slope_deg": 24.5,
    "mean_slope_deg": 8.1,
    "failure_reason": null
  }
}
```

任务未完成时返回 `409 TASK_METRICS_NOT_READY`：

```json
{
  "detail": {
    "code": "TASK_METRICS_NOT_READY",
    "message": "Mobility metrics are available only after the task is finished."
  }
}
```

### 8.1 指标字段说明

| 字段 | 类型 | 单位 | 说明 |
| --- | --- | --- | --- |
| `winner` | string | - | 优胜车辆：`wheeled`、`tracked`、`tie`、`none` |
| `time_saving_seconds` | number/null | 秒 | 优胜车辆相对较慢车辆节省时间 |
| `time_saving_ratio` | number/null | 0-1 | 节省时间占较慢车辆时间比例 |
| `wheeled.reachable` | boolean | - | 轮式车辆是否可达 |
| `wheeled.travel_time_seconds` | number/null | 秒 | 轮式车辆最短通行时间 |
| `wheeled.travel_distance_m` | number | 米 | 轮式车辆路径长度 |
| `wheeled.average_speed_kph` | number | 公里/小时 | 轮式车辆路径平均速度 |
| `wheeled.road_distance_m` | number | 米 | 轮式车辆路径道路段长度估计 |
| `wheeled.offroad_distance_m` | number | 米 | 轮式车辆路径越野段长度估计 |
| `wheeled.max_slope_deg` | number/null | 度 | 轮式车辆路径最大坡度 |
| `wheeled.mean_slope_deg` | number/null | 度 | 轮式车辆路径平均坡度 |
| `wheeled.failure_reason` | string/null | - | 轮式车辆不可达原因 |
| `tracked.reachable` | boolean | - | 履式车辆是否可达 |
| `tracked.travel_time_seconds` | number/null | 秒 | 履式车辆最短通行时间 |
| `tracked.travel_distance_m` | number | 米 | 履式车辆路径长度 |
| `tracked.average_speed_kph` | number | 公里/小时 | 履式车辆路径平均速度 |
| `tracked.road_distance_m` | number | 米 | 履式车辆路径道路段长度估计 |
| `tracked.offroad_distance_m` | number | 米 | 履式车辆路径越野段长度估计 |
| `tracked.max_slope_deg` | number/null | 度 | 履式车辆路径最大坡度 |
| `tracked.mean_slope_deg` | number/null | 度 | 履式车辆路径平均坡度 |
| `tracked.failure_reason` | string/null | - | 履式车辆不可达原因 |

### 8.2 winner 判定规则

| 情况 | winner |
| --- | --- |
| 轮式可达，履式不可达 | `wheeled` |
| 履式可达，轮式不可达 | `tracked` |
| 两者都不可达 | `none` |
| 两者都可达，时间接近 | `tie` |
| 两者都可达，轮式更快 | `wheeled` |
| 两者都可达，履式更快 | `tracked` |

时间接近的判定为相对差异约 1% 或绝对差异 5 秒以内。

## 9. 输出文件

### 9.1 查询输出文件

`GET /api/mobility/accessibility/{task_id}/outputs`

响应示例：

```json
[
  {
    "kind": "wheeled_path_geojson",
    "label": "Wheeled Vehicle Path GeoJSON",
    "url": "/outputs/mobility_task_xxx/wheeled_path.geojson",
    "download_url": "/api/mobility/accessibility/mobility_task_xxx/outputs/wheeled_path_geojson",
    "filename": "wheeled_path.geojson",
    "media_type": "application/geo+json",
    "size_bytes": 1024,
    "exists": true
  }
]
```

### 9.2 输出类型

| kind | 文件 | 说明 |
| --- | --- | --- |
| `wheeled_path_geojson` | `wheeled_path.geojson` | 轮式车辆最短时间路径 |
| `tracked_path_geojson` | `tracked_path.geojson` | 履式车辆最短时间路径 |
| `road_mask_geojson` | `road_mask.geojson` | 路网栅格化影响区 |
| `cost_summary_json` | `cost_summary.json` | 代价栅格摘要 |
| `model_metadata_json` | `model_metadata.json` | 模型参数和 DEM 投影信息 |
| `output_manifest_json` | `output_manifest.json` | 输出清单 |

### 9.3 下载单个输出

`GET /api/mobility/accessibility/{task_id}/outputs/{kind}`

示例：

```http
GET /api/mobility/accessibility/mobility_task_xxx/outputs/wheeled_path_geojson
```

任务未完成时下载输出会返回 `409 TASK_NOT_FINISHED`。

## 10. curl 调用示例

### 10.1 创建任务

```bash
curl -X POST http://127.0.0.1:8000/api/mobility/accessibility \
  -H "Content-Type: application/json" \
  -d '{
    "dem_id": "dem_xxx",
    "start": {
      "lon": 79.80513693057287,
      "lat": 31.4827708959419
    },
    "end": {
      "lon": 79.82,
      "lat": 31.49
    }
  }'
```

### 10.2 查询任务

```bash
curl http://127.0.0.1:8000/api/mobility/accessibility/{task_id}
```

### 10.3 获取指标

```bash
curl http://127.0.0.1:8000/api/mobility/accessibility/{task_id}/metrics
```

### 10.4 查询输出文件

```bash
curl http://127.0.0.1:8000/api/mobility/accessibility/{task_id}/outputs
```

## 11. 常见错误

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
| `DEM_NOT_FOUND` | 404 | `dem_id` 不存在 |
| `DEM_WITHOUT_CRS` | 400/500 | DEM 缺少坐标系 |
| `MOBILITY_START_OUTSIDE_DEM` | 400 | 起点超出 DEM 覆盖范围 |
| `MOBILITY_END_OUTSIDE_DEM` | 400 | 终点超出 DEM 覆盖范围 |
| `MOBILITY_NO_DATA` | 400 | 起点或终点落在 DEM NoData |
| `RANGE_OUTSIDE_DEM` | 400 | 搜索范围和 DEM 不相交 |
| `INVALID_ROAD_NETWORK` | 400 | 路网 GeoJSON 结构不合法 |
| `TASK_NOT_FOUND` | 404 | 任务不存在 |
| `TASK_METRICS_NOT_READY` | 409 | 任务未完成，不能读取指标 |
| `TASK_NOT_FINISHED` | 409 | 任务未完成，不能下载输出 |
| `OUTPUT_NOT_FOUND` | 404 | 指定输出文件不存在 |

## 12. 第三方系统集成建议

- 先上传 DEM 并保存 `dem_id`。
- 创建任务后保存 `task_id`。
- 每 1-3 秒轮询任务详情；大 DEM 可放宽到 3-5 秒。
- 任务 `status=finished` 后再读取 `/metrics`。
- 只需要量化指标时，不要下载 GeoJSON 输出。
- 起点、终点必须在 DEM 范围内，且 DEM 应覆盖合理搜索范围。
- 如果路网较复杂，建议先简化道路几何再提交，减少栅格化成本。
- `max_search_radius_m` 为空时系统自动估算；如果起终点之间存在明显绕行，可显式给更大的搜索半径。
