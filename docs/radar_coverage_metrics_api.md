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
  "requested_theoretical_area_m2": 7850000000.0,
  "theoretical_area_m2": 6280000000.0,
  "unknown_area_m2": 1570000000.0,
  "visible_area_m2": 3690000000.0,
  "blocked_area_m2": 2590000000.0,
  "blocked_ratio": 0.412,
  "terrain_visible_area_m2": 5100000000.0,
  "beam_eligible_area_m2": 6280000000.0,
  "radar_equation_limited_area_m2": 0.0
}
```

### 指标说明

| 字段 | 单位 | 说明 |
| --- | --- | --- |
| `requested_theoretical_area_m2` | 平方米 | DEM 裁剪前的理论波束面积，已考虑扇区、俯仰角和雷达方程有效距离 |
| `theoretical_area_m2` | 平方米 | DEM 有效分析域内的理论波束面积，即可分析理论面积 |
| `unknown_area_m2` | 平方米 | 理论波束中超出 DEM 连续有效域的面积，结果未知，不视为地形遮挡 |
| `visible_area_m2` | 平方米 | 可分析理论面积中的实际可探测面积 |
| `blocked_area_m2` | 平方米 | 可分析理论面积中被地形遮挡的面积，不包含 DEM 外未知区 |
| `blocked_ratio` | 0-1 | `blocked_area_m2 / theoretical_area_m2` |
| `terrain_visible_area_m2` | 平方米 | 仅按地形最低可见高度判断的可见面积参考值 |
| `beam_eligible_area_m2` | 平方米 | DEM 有效分析域内满足波束俯仰角约束的面积 |
| `radar_equation_limited_area_m2` | 平方米 | 因雷达方程有效距离小于请求距离而被排除的面积 |

面积关系如下。由于面积由栅格像元统计，外部系统校验时应允许浮点误差：

```text
requested_theoretical_area_m2 = theoretical_area_m2 + unknown_area_m2
theoretical_area_m2 = visible_area_m2 + blocked_area_m2
```

DEM 有效分析域按方位角从雷达位置向外连续采样；每条射线遇到 DEM 边界或首个 NoData 像元后，后续区域都归入 `unknown_area_m2`。负高程是有效地形数据，不会被当作 NoData。

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

## 5. DEM 裁剪轮廓

完整任务响应的 `model.beam_clip_profile` 描述前端绘制理论波束时使用的径向裁剪轮廓：

```json
{
  "model": {
    "dem_coverage_ratio": 0.8,
    "beam_clip_profile": {
      "azimuth_step_deg": 2.0,
      "radius_m": [50000.0, 49875.0, 49250.0]
    }
  }
}
```

| 字段 | 说明 |
| --- | --- |
| `azimuth_step_deg` | 相邻半径样本的方位角间隔；当前为 2 度，方位角 0 度指北并顺时针增加 |
| `radius_m` | 各方位角从雷达位置到 DEM 连续有效域边界的距离，已限制在任务有效探测距离内 |
| `dem_coverage_ratio` | `theoretical_area_m2 / requested_theoretical_area_m2`；请求理论面积为 0 时取 1 |

`radar_range.geojson`、可见区、遮挡区、高度层、体素和三维裁切体使用同一个 DEM 分析域。旧任务可能没有 `beam_clip_profile`；前端加载这类任务时会使用 DEM 的矩形 `bounds` 近似裁剪，不能还原内部 NoData 形成的精确边界。

## 6. 查询输出文件

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

## 7. 下载输出文件

`GET /api/radar/coverage/{task_id}/outputs/{kind}`

示例：

```text
GET /api/radar/coverage/task_20260630_101500_ab12cd34/outputs/visible_geojson
```

## 8. 剖面分析接口

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

## 9. 多任务融合分析

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

## 10. 调用流程建议

1. 调用 `POST /api/radar/coverage` 创建任务。
2. 保存返回的 `task_id`。
3. 轮询 `GET /api/radar/coverage/{task_id}`，直到 `status` 为 `finished` 或 `failed`。
4. 如果 `finished`，调用 `GET /api/radar/coverage/{task_id}/metrics` 获取量化指标 JSON。
5. 如需空间结果，再调用 `/outputs` 或 `/outputs/{kind}`。
6. 如需某个点的剖面遮挡，调用 `/profile`。
7. 如需多任务合并覆盖指标，调用 `/fusion`。

## 11. 与 UAV 指标接口的一致性

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
