# 侦察车侦查范围量化指标接口

## 概览

- 模型: 侦察车侦查范围
- API 前缀: `/api/recon-vehicle`
- 任务接口: 异步任务
- 指标接口: 任务完成后通过 `/metrics` 获取 JSON
- 第一版能力: 单点车位、路线采样、传感器扇区、DEM 地形通视遮挡

## 创建任务

`POST /api/recon-vehicle/coverage`

```json
{
  "dem_id": "dem_xxx",
  "vehicle": {
    "lon": 79.80513693057287,
    "lat": 31.4827708959419,
    "heading_deg": 90,
    "mast_height_m": 3
  },
  "route": {
    "waypoints": [
      {
        "lon": 79.80513693057287,
        "lat": 31.4827708959419,
        "heading_deg": 90,
        "mast_height_m": 3
      },
      {
        "lon": 79.82,
        "lat": 31.49,
        "heading_deg": 110,
        "mast_height_m": 3
      }
    ],
    "sample_interval_m": 500
  },
  "sensor": {
    "sensor_type": "optical",
    "max_range_m": 5000,
    "min_range_m": 0,
    "scan_mode": "sector",
    "view_angle_deg": 120
  },
  "target": {
    "height_m": 1.7
  },
  "analysis": {
    "use_terrain_occlusion": true,
    "use_curvature": true,
    "curvature_coeff": 0.75,
    "output_simplify_tolerance_m": 30
  }
}
```

`route` 可省略。省略时只计算 `vehicle` 单点侦查范围。

## 查询任务

`GET /api/recon-vehicle/coverage/{task_id}`

任务完成后响应中包含 `metrics`、`outputs`、`output_files` 和 `model`。

## 获取量化指标 JSON

`GET /api/recon-vehicle/coverage/{task_id}/metrics`

任务未完成时返回 `409 TASK_METRICS_NOT_READY`。

```json
{
  "theoretical_area_m2": 12000000.0,
  "visible_area_m2": 7600000.0,
  "blocked_area_m2": 4400000.0,
  "blocked_ratio": 0.3667,
  "max_range_m": 5000.0,
  "effective_view_angle_deg": 120.0,
  "coverage_point_count": 8,
  "route_length_m": 3500.0,
  "average_visible_area_m2": 1800000.0,
  "overlap_area_m2": 6800000.0,
  "vehicle_ground_elevation_m": 3210.5,
  "sensor_altitude_m": 3213.5
}
```

| 字段 | 单位 | 含义 |
| --- | --- | --- |
| `theoretical_area_m2` | 平方米 | 仅由传感器距离、方位和视场形成的理论侦查面积 |
| `visible_area_m2` | 平方米 | DEM 通视后可侦查面积 |
| `blocked_area_m2` | 平方米 | 地形遮挡面积 |
| `blocked_ratio` | 0-1 | `blocked_area_m2 / theoretical_area_m2` |
| `max_range_m` | 米 | 传感器最大距离 |
| `effective_view_angle_deg` | 度 | 实际视场角，全向为 360 |
| `coverage_point_count` | 个 | 单点为 1，路线为采样车位数量 |
| `route_length_m` | 米 | 路线长度，单点为 0 |
| `average_visible_area_m2` | 平方米 | 单个采样车位平均可见面积 |
| `overlap_area_m2` | 平方米 | 路线多车位可见区重叠面积估计 |
| `vehicle_ground_elevation_m` | 米 | 第一个车位地面高程 |
| `sensor_altitude_m` | 米 | 第一个车位传感器海拔高度 |

## 输出文件

`GET /api/recon-vehicle/coverage/{task_id}/outputs`

| kind | 文件 | 说明 |
| --- | --- | --- |
| `footprint_geojson` | `footprint.geojson` | 理论侦查范围 |
| `visible_geojson` | `visible.geojson` | 地形通视后可侦查区 |
| `blocked_geojson` | `blocked.geojson` | 地形遮挡区 |
| `model_metadata_json` | `model_metadata.json` | 模型参数和 DEM 投影信息 |
| `output_manifest_json` | `output_manifest.json` | 输出清单 |

下载单个输出：

`GET /api/recon-vehicle/coverage/{task_id}/outputs/{kind}`

## 调用流程

1. 上传或选择 DEM。
2. 调用 `POST /api/recon-vehicle/coverage` 创建任务。
3. 轮询 `GET /api/recon-vehicle/coverage/{task_id}`。
4. 任务 `status` 为 `finished` 后调用 `/metrics` 获取量化指标 JSON。
