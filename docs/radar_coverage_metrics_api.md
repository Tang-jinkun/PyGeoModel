# 雷达覆盖量化指标 API

本文档描述雷达地形覆盖模型的后端接口，重点说明如何获取覆盖结果的量化指标 JSON。

## 基础信息

- Base URL: `http://localhost:8000`
- API 前缀: `/api/radar`
- 计算方式: 异步任务
- 指标接口: 任务完成后通过 `/metrics` 获取 JSON

## 1. 创建雷达覆盖任务

`POST /api/radar/coverage`

创建雷达覆盖计算任务。接口返回任务状态，计算在后台执行。

### 请求示例

```json
{
  "dem_id": "dem_20260629_041450_528ff0d2",
  "radar": {
    "lon": 79.80513693057287,
    "lat": 31.4827708959419,
    "height_m": 10
  },
  "target": {
    "height_m": 0
  },
  "coverage": {
    "max_range_m": 50000,
    "scan_mode": "omni",
    "azimuth_deg": 90,
    "beam_width_deg": 120
  },
  "advanced": {
    "use_curvature": true,
    "curvature_coeff": 0.75,
    "output_simplify_tolerance_m": 30,
    "voxel_grid_size": 128,
    "voxel_vertical_levels": 16,
    "voxel_max_height_m": 3000,
    "min_elevation_deg": 0,
    "max_elevation_deg": 32,
    "visual_dome_mode": true,
    "height_layers_m": [0, 100, 300, 500, 1000]
  },
  "reserved_radar_params": {
    "frequency_hz": null,
    "transmit_power_w": null,
    "antenna_gain_db": null,
    "receiver_sensitivity_dbm": null,
    "target_rcs_m2": null,
    "system_loss_db": null
  }
}
```

### 主要输入字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `dem_id` | string | DEM 数据 ID |
| `radar.lon` | number | 雷达经度 |
| `radar.lat` | number | 雷达纬度 |
| `radar.height_m` | number | 雷达离地高度 |
| `target.height_m` | number | 目标离地高度 |
| `coverage.max_range_m` | number | 最大覆盖距离，单位米 |
| `coverage.scan_mode` | string | `omni` 全向，`sector` 扇区 |
| `coverage.azimuth_deg` | number | 扇区中心方位角 |
| `coverage.beam_width_deg` | number | 水平波束宽度 |
| `advanced.use_curvature` | boolean | 是否考虑地球曲率修正 |
| `advanced.curvature_coeff` | number | 曲率系数 |
| `advanced.min_elevation_deg` | number | 最小俯仰角 |
| `advanced.max_elevation_deg` | number | 最大俯仰角 |
| `advanced.height_layers_m` | array | 高度层结果输出 |
| `reserved_radar_params` | object | 预留雷达方程参数。参数完整时可限制有效距离 |

### 响应示例

```json
{
  "task_id": "task_20260630_101500_ab12cd34",
  "dem_id": "dem_20260629_041450_528ff0d2",
  "status": "pending",
  "progress": 0,
  "message": "queued",
  "metrics": null,
  "outputs": null,
  "output_files": [],
  "model": null,
  "diagnostics": null,
  "warnings": [],
  "request": {
    "...": "same as request body"
  }
}
```

## 2. 查询雷达任务状态

`GET /api/radar/coverage/{task_id}`

用于轮询任务状态。任务完成后，响应中会包含 `metrics`、`outputs`、`model` 和 `diagnostics`。

### 状态值

| 状态 | 说明 |
| --- | --- |
| `pending` | 已创建，等待执行 |
| `running` | 正在计算 |
| `finished` | 已完成，可读取 metrics |
| `failed` | 计算失败 |

## 3. 获取量化指标 JSON

`GET /api/radar/coverage/{task_id}/metrics`

任务完成后调用。该接口只返回量化指标 JSON，适合其他系统集成。

### 成功响应

```json
{
  "theoretical_area_m2": 7850000000.0,
  "visible_area_m2": 4620000000.0,
  "blocked_area_m2": 3230000000.0,
  "blocked_ratio": 0.411,
  "terrain_visible_area_m2": 5100000000.0,
  "beam_eligible_area_m2": 7850000000.0,
  "radar_equation_limited_area_m2": 0.0
}
```

### 指标说明

| 字段 | 单位 | 说明 |
| --- | --- | --- |
| `theoretical_area_m2` | 平方米 | 理论覆盖面积，已考虑最大距离、扇区、俯仰角和雷达方程有效距离，但不扣除地形遮挡 |
| `visible_area_m2` | 平方米 | 实际可探测面积，已考虑地形遮挡 |
| `blocked_area_m2` | 平方米 | 理论覆盖内被地形遮挡的面积 |
| `blocked_ratio` | 0-1 | 遮挡面积占理论覆盖面积比例 |
| `terrain_visible_area_m2` | 平方米 | 仅按地形最低可见高度判断的可见面积参考值 |
| `beam_eligible_area_m2` | 平方米 | 满足波束俯仰角约束的面积 |
| `radar_equation_limited_area_m2` | 平方米 | 因雷达方程有效距离小于请求距离而被排除的面积 |

### 错误响应

任务未完成或指标尚不可用：

```json
{
  "detail": {
    "code": "TASK_METRICS_NOT_READY",
    "message": "Coverage metrics are available only after the task is finished."
  }
}
```

HTTP 状态码: `409`

## 4. 诊断信息

完整任务查询接口 `GET /api/radar/coverage/{task_id}` 中包含 `diagnostics` 字段。

示例：

```json
{
  "diagnostics": {
    "radar_equation_active": false,
    "radar_equation_max_range_m": null,
    "effective_max_range_m": 50000,
    "terrain_blocked_area_m2": 3230000000.0,
    "elevation_limited_area_m2": 0.0,
    "radar_equation_limited_area_m2": 0.0,
    "notes": [
      "Radar equation is inactive because one or more RF parameters are missing."
    ]
  }
}
```

### 诊断字段说明

| 字段 | 单位 | 说明 |
| --- | --- | --- |
| `radar_equation_active` | boolean | 雷达方程是否启用 |
| `radar_equation_max_range_m` | 米 | 雷达方程计算出的最大有效距离 |
| `effective_max_range_m` | 米 | 模型实际使用的最大距离 |
| `terrain_blocked_area_m2` | 平方米 | 地形遮挡面积 |
| `elevation_limited_area_m2` | 平方米 | 因俯仰角限制排除的面积 |
| `radar_equation_limited_area_m2` | 平方米 | 因雷达方程距离限制排除的面积 |
| `notes` | array | 模型诊断说明 |

## 5. 查询输出文件

`GET /api/radar/coverage/{task_id}/outputs`

返回雷达任务产出的文件列表。

当前输出类型：

| kind | 文件 | 说明 |
| --- | --- | --- |
| `viewshed_tif` | `viewshed.tif` | GDAL viewshed 栅格 |
| `visible_geojson` | `visible.geojson` | 实际可探测区 |
| `blocked_geojson` | `blocked.geojson` | 地形遮挡区 |
| `range_geojson` | `radar_range.geojson` | 理论覆盖范围 |
| `model_metadata_json` | `model_metadata.json` | 模型元数据 |
| `output_manifest_json` | `output_manifest.json` | 输出清单 |
| `min_visible_height_tif` | `min_visible_height.tif` | 最低可见高度栅格 |
| `voxel_manifest_json` | `voxel_manifest.json` | 体素点云清单 |
| `voxel_points_bin` | `voxel_points.bin` | 体素点云二进制 |
| `clipped_volume_manifest_json` | `clipped_volume_manifest.json` | 地形裁切波束体清单 |
| `clipped_volume_cells_bin` | `clipped_volume_cells.bin` | 地形裁切波束体二进制 |
| `height_layers_manifest_json` | `height_layers_manifest.json` | 高度层输出清单 |

## 6. 下载输出文件

`GET /api/radar/coverage/{task_id}/outputs/{kind}`

示例：

```text
GET /api/radar/coverage/task_20260630_101500_ab12cd34/outputs/visible_geojson
```

## 7. 剖面分析接口

`GET /api/radar/coverage/{task_id}/profile?lon={lon}&lat={lat}&samples=180`

用于查询雷达到指定目标点之间的地形剖面和遮挡信息。

返回字段包括：

| 字段 | 说明 |
| --- | --- |
| `blocked` | 是否存在地形遮挡 |
| `distance_m` | 目标距离 |
| `azimuth_deg` | 目标方位角 |
| `elevation_deg` | 目标俯仰角 |
| `obstruction_distance_m` | 最严重遮挡点距离 |
| `obstruction_lon` / `obstruction_lat` | 遮挡点经纬度 |
| `obstruction_clearance_m` | 遮挡点净空，负值表示遮挡 |
| `min_required_target_height_m` | 要达到可见所需的目标最低高度 |
| `samples` | 地形剖面采样列表 |

## 8. 多任务融合分析

`POST /api/radar/fusion`

对多个已完成雷达任务做覆盖融合分析。

请求：

```json
{
  "task_ids": [
    "task_20260630_101500_ab12cd34",
    "task_20260630_102000_cd34ef56"
  ]
}
```

返回的 `metrics` 字段：

| 字段 | 单位 | 说明 |
| --- | --- | --- |
| `task_count` | 个 | 参与融合的任务数量 |
| `union_visible_area_m2` | 平方米 | 多任务可探测区并集面积 |
| `overlap_visible_area_m2` | 平方米 | 多任务重叠覆盖面积 |
| `union_theoretical_area_m2` | 平方米 | 多任务理论范围并集面积 |
| `blind_area_m2` | 平方米 | 理论范围内未被实际覆盖的盲区面积 |
| `overlap_ratio` | 0-1 | 重叠覆盖比例 |
| `blind_ratio` | 0-1 | 盲区比例 |

## 9. 调用流程建议

1. 调用 `POST /api/radar/coverage` 创建任务。
2. 保存返回的 `task_id`。
3. 轮询 `GET /api/radar/coverage/{task_id}`，直到 `status` 为 `finished` 或 `failed`。
4. 如果 `finished`，调用 `GET /api/radar/coverage/{task_id}/metrics` 获取量化指标 JSON。
5. 如需空间结果，再调用 `/outputs` 或 `/outputs/{kind}`。
6. 如需某个点的剖面遮挡，调用 `/profile`。
7. 如需多任务合并覆盖指标，调用 `/fusion`。

## 10. 与 UAV 指标接口的一致性

UAV 模型也提供独立量化指标接口：

```text
GET /api/uav/recon/{task_id}/metrics
```

后续新增模型也应保持同样约定：

```text
POST /api/{model}/...
GET  /api/{model}/.../{task_id}
GET  /api/{model}/.../{task_id}/metrics
```
