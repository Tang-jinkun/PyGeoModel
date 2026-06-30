# 观察哨侦测范围量化指标 API

本文档描述观察哨侦测范围模型的后端接口，重点说明如何获取侦测范围量化指标 JSON。

## 基础信息

- Base URL: `http://localhost:8000`
- API 前缀: `/api/watchpost`
- 计算方式: 异步任务
- 指标接口: 任务完成后通过 `/metrics` 获取 JSON

## 1. 创建观察哨侦测任务

`POST /api/watchpost/detection`

创建固定观察哨侦测范围任务。接口返回任务状态，计算在后台执行。

### 请求示例

```json
{
  "dem_id": "dem_20260629_041450_528ff0d2",
  "observer": {
    "lon": 79.80513693057287,
    "lat": 31.4827708959419,
    "height_m": 8
  },
  "target": {
    "height_m": 1.7
  },
  "coverage": {
    "max_range_m": 5000,
    "scan_mode": "sector",
    "azimuth_deg": 90,
    "view_angle_deg": 120
  },
  "analysis": {
    "use_curvature": true,
    "curvature_coeff": 0.75,
    "output_simplify_tolerance_m": 20
  }
}
```

### 主要输入字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `dem_id` | string | DEM 数据 ID |
| `observer.lon` | number | 观察哨经度 |
| `observer.lat` | number | 观察哨纬度 |
| `observer.height_m` | number | 观察点离地高度 |
| `target.height_m` | number | 目标离地高度 |
| `coverage.max_range_m` | number | 最大侦测距离，单位米 |
| `coverage.scan_mode` | string | `omni` 全向，`sector` 扇区 |
| `coverage.azimuth_deg` | number | 扇区中心方位角 |
| `coverage.view_angle_deg` | number | 观察扇区角度 |
| `analysis.use_curvature` | boolean | 是否考虑地球曲率修正 |
| `analysis.curvature_coeff` | number | 曲率系数 |
| `analysis.output_simplify_tolerance_m` | number/null | 输出 GeoJSON 简化容差 |

### 响应示例

```json
{
  "task_id": "watchpost_task_20260630_101500_ab12cd34",
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

## 2. 查询观察哨任务状态

`GET /api/watchpost/detection/{task_id}`

用于轮询任务状态。任务完成后，响应中会包含 `metrics`、`outputs` 和 `model`。

### 状态值

| 状态 | 说明 |
| --- | --- |
| `pending` | 已创建，等待执行 |
| `running` | 正在计算 |
| `finished` | 已完成，可读取 metrics |
| `failed` | 计算失败 |

## 3. 获取量化指标 JSON

`GET /api/watchpost/detection/{task_id}/metrics`

任务完成后调用。该接口只返回量化指标 JSON，适合其他系统集成。

### 成功响应

```json
{
  "theoretical_area_m2": 78500000.0,
  "visible_area_m2": 46200000.0,
  "blocked_area_m2": 32300000.0,
  "blocked_ratio": 0.411,
  "max_range_m": 5000.0,
  "effective_view_angle_deg": 120.0,
  "observer_ground_elevation_m": 3200.0,
  "observer_altitude_m": 3208.0
}
```

### 指标说明

| 字段 | 单位 | 说明 |
| --- | --- | --- |
| `theoretical_area_m2` | 平方米 | 理论侦测范围面积，不扣除地形遮挡 |
| `visible_area_m2` | 平方米 | 实际可侦测面积，已考虑地形遮挡 |
| `blocked_area_m2` | 平方米 | 理论范围内被地形遮挡的面积 |
| `blocked_ratio` | 0-1 | 遮挡面积占理论侦测范围面积比例 |
| `max_range_m` | 米 | 最大侦测距离 |
| `effective_view_angle_deg` | 度 | 实际观察角度。全向为 360，扇区为 `view_angle_deg` |
| `observer_ground_elevation_m` | 米 | 观察哨地面高程 |
| `observer_altitude_m` | 米 | 观察点海拔高度，等于地面高程加观察点离地高度 |

### 错误响应

任务未完成或指标尚不可用：

```json
{
  "detail": {
    "code": "TASK_METRICS_NOT_READY",
    "message": "Watchpost metrics are available only after the task is finished."
  }
}
```

HTTP 状态码: `409`

## 4. 查询输出文件

`GET /api/watchpost/detection/{task_id}/outputs`

返回观察哨任务产出的文件列表。

当前输出类型：

| kind | 文件 | 说明 |
| --- | --- | --- |
| `viewshed_tif` | `viewshed.tif` | GDAL viewshed 栅格 |
| `visible_geojson` | `visible.geojson` | 实际可侦测区域 |
| `blocked_geojson` | `blocked.geojson` | 地形遮挡区域 |
| `range_geojson` | `range.geojson` | 理论侦测范围 |
| `model_metadata_json` | `model_metadata.json` | 模型元数据 |
| `output_manifest_json` | `output_manifest.json` | 输出清单 |

## 5. 下载输出文件

`GET /api/watchpost/detection/{task_id}/outputs/{kind}`

示例：

```text
GET /api/watchpost/detection/watchpost_task_20260630_101500_ab12cd34/outputs/visible_geojson
```

## 6. 调用流程建议

1. 调用 `POST /api/watchpost/detection` 创建任务。
2. 保存返回的 `task_id`。
3. 轮询 `GET /api/watchpost/detection/{task_id}`，直到 `status` 为 `finished` 或 `failed`。
4. 如果 `finished`，调用 `GET /api/watchpost/detection/{task_id}/metrics` 获取量化指标 JSON。
5. 如需空间结果，再调用 `/outputs` 或 `/outputs/{kind}`。

## 7. 与其他模型指标接口的一致性

雷达模型：

```text
GET /api/radar/coverage/{task_id}/metrics
```

UAV 模型：

```text
GET /api/uav/recon/{task_id}/metrics
```

后续新增模型也应保持同样约定：

```text
POST /api/{model}/...
GET  /api/{model}/.../{task_id}
GET  /api/{model}/.../{task_id}/metrics
```
