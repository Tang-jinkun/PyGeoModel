# UAV 侦查覆盖量化指标 API

本文档描述 UAV 侦查模型的后端接口。当前版本只要求模型计算和 JSON 指标返回，不包含前端展示。

## 基础信息

- Base URL: `http://localhost:8000`
- API 前缀: `/api/uav`
- 计算方式: 异步任务
- 指标接口: 任务完成后通过 `/metrics` 获取 JSON

## 1. 创建 UAV 侦查任务

`POST /api/uav/recon`

创建单点或航线侦查覆盖任务。接口返回任务状态，计算在后台执行。

### 单点请求示例

```json
{
  "dem_id": "dem_20260629_041450_528ff0d2",
  "uav": {
    "lon": 79.80513693057287,
    "lat": 31.4827708959419,
    "altitude_m": 500,
    "altitude_mode": "agl",
    "heading_deg": 90,
    "pitch_deg": -45,
    "roll_deg": 0
  },
  "sensor": {
    "sensor_type": "camera",
    "h_fov_deg": 60,
    "v_fov_deg": 40,
    "max_range_m": 5000,
    "min_range_m": 0,
    "ground_resolution_m": null
  },
  "analysis": {
    "target_height_m": 0,
    "use_terrain_occlusion": true,
    "sample_resolution_m": null,
    "output_simplify_tolerance_m": 30
  }
}
```

### 航线请求示例

```json
{
  "dem_id": "dem_20260629_041450_528ff0d2",
  "uav": {
    "lon": 79.80513693057287,
    "lat": 31.4827708959419,
    "altitude_m": 500,
    "altitude_mode": "agl",
    "heading_deg": 90,
    "pitch_deg": -45,
    "roll_deg": 0
  },
  "route": {
    "sample_interval_m": 500,
    "waypoints": [
      {
        "lon": 79.80513693057287,
        "lat": 31.4827708959419,
        "altitude_m": 500,
        "altitude_mode": "agl",
        "heading_deg": 90,
        "pitch_deg": -45,
        "roll_deg": 0
      },
      {
        "lon": 79.85513693057287,
        "lat": 31.5027708959419,
        "altitude_m": 500,
        "altitude_mode": "agl",
        "heading_deg": 110,
        "pitch_deg": -45,
        "roll_deg": 0
      }
    ]
  },
  "sensor": {
    "sensor_type": "camera",
    "h_fov_deg": 60,
    "v_fov_deg": 40,
    "max_range_m": 5000,
    "min_range_m": 0
  },
  "analysis": {
    "target_height_m": 0,
    "use_terrain_occlusion": true,
    "output_simplify_tolerance_m": 30
  }
}
```

### 主要输入字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `dem_id` | string | DEM 数据 ID |
| `uav.lon` | number | 单点无人机经度 |
| `uav.lat` | number | 单点无人机纬度 |
| `uav.altitude_m` | number | 无人机高度 |
| `uav.altitude_mode` | string | `agl` 表示相对地面高度，`amsl` 表示海拔高度 |
| `uav.heading_deg` | number | 航向角，0-360 度 |
| `uav.pitch_deg` | number | 传感器俯仰角，向下为负 |
| `uav.roll_deg` | number | 横滚角，当前第一版保留字段 |
| `route.waypoints` | array | 航线航点。存在时按航线覆盖计算 |
| `route.sample_interval_m` | number | 航线插值采样间距 |
| `sensor.h_fov_deg` | number | 水平视场角 |
| `sensor.v_fov_deg` | number | 垂直视场角 |
| `sensor.max_range_m` | number | 最大侦查距离 |
| `sensor.min_range_m` | number | 最小侦查距离 |
| `analysis.target_height_m` | number | 目标高度 |
| `analysis.use_terrain_occlusion` | boolean | 是否考虑地形遮挡 |

### 响应示例

```json
{
  "task_id": "uav_task_20260630_101500_ab12cd34",
  "dem_id": "dem_20260629_041450_528ff0d2",
  "status": "pending",
  "progress": 0,
  "message": "queued",
  "metrics": null,
  "outputs": null,
  "output_files": [],
  "model": null,
  "warnings": [],
  "request": {
    "...": "same as request body"
  }
}
```

## 2. 查询 UAV 任务状态

`GET /api/uav/recon/{task_id}`

用于轮询任务状态。任务完成后，响应中会包含 `metrics`、`outputs` 和 `model`。

### 状态值

| 状态 | 说明 |
| --- | --- |
| `pending` | 已创建，等待执行 |
| `running` | 正在计算 |
| `finished` | 已完成，可读取 metrics |
| `failed` | 计算失败 |

## 3. 获取量化指标 JSON

`GET /api/uav/recon/{task_id}/metrics`

任务完成后调用。该接口只返回量化指标 JSON，适合其他系统集成。

### 成功响应

```json
{
  "theoretical_area_m2": 1250000.0,
  "visible_area_m2": 820000.0,
  "blocked_area_m2": 430000.0,
  "blocked_ratio": 0.344,
  "max_ground_distance_m": 5000.0,
  "coverage_point_count": 12,
  "route_length_m": 5600.0,
  "average_visible_area_m2": 210000.0,
  "overlap_area_m2": 1700000.0
}
```

### 指标说明

| 字段 | 单位 | 说明 |
| --- | --- | --- |
| `theoretical_area_m2` | 平方米 | 传感器理论视场投影面积，不扣除地形遮挡 |
| `visible_area_m2` | 平方米 | 实际可侦查面积，已考虑地形遮挡 |
| `blocked_area_m2` | 平方米 | 理论视场内被地形遮挡的面积 |
| `blocked_ratio` | 0-1 | 遮挡面积占理论面积比例 |
| `max_ground_distance_m` | 米 | 本次模型使用的最大侦查距离 |
| `coverage_point_count` | 个 | 参与覆盖计算的采样点数。单点为 1，航线为插值后的点数 |
| `route_length_m` | 米 | 航线长度。单点为 0 |
| `average_visible_area_m2` | 平方米 | 每个采样点平均可侦查面积 |
| `overlap_area_m2` | 平方米 | 航线多点覆盖重叠面积估计值 |

### 错误响应

任务未完成或指标尚不可用：

```json
{
  "detail": {
    "code": "TASK_METRICS_NOT_READY",
    "message": "UAV metrics are available only after the task is finished."
  }
}
```

HTTP 状态码: `409`

## 4. 查询输出文件

`GET /api/uav/recon/{task_id}/outputs`

返回 UAV 任务产出的文件列表。

当前输出类型：

| kind | 文件 | 说明 |
| --- | --- | --- |
| `footprint_geojson` | `footprint.geojson` | 理论侦查范围 |
| `visible_geojson` | `visible.geojson` | 实际可侦查区域 |
| `blocked_geojson` | `blocked.geojson` | 地形遮挡区域 |
| `model_metadata_json` | `model_metadata.json` | 模型元数据 |
| `output_manifest_json` | `output_manifest.json` | 输出清单 |

## 5. 下载输出文件

`GET /api/uav/recon/{task_id}/outputs/{kind}`

示例：

```text
GET /api/uav/recon/uav_task_20260630_101500_ab12cd34/outputs/visible_geojson
```

## 6. 调用流程建议

1. 调用 `POST /api/uav/recon` 创建任务。
2. 保存返回的 `task_id`。
3. 轮询 `GET /api/uav/recon/{task_id}`，直到 `status` 为 `finished` 或 `failed`。
4. 如果 `finished`，调用 `GET /api/uav/recon/{task_id}/metrics` 获取量化指标 JSON。
5. 如需空间结果，再调用 `/outputs` 或 `/outputs/{kind}`。

## 7. 与雷达指标接口的一致性

雷达模型也提供独立量化指标接口：

```text
GET /api/radar/coverage/{task_id}/metrics
```

后续新增模型也应保持同样约定：

```text
POST /api/{model}/...
GET  /api/{model}/.../{task_id}
GET  /api/{model}/.../{task_id}/metrics
```
