# 火炮火力覆盖与弹道遮山指标接口

## 概览

- 模型: 火炮火力覆盖区
- API 前缀: `/api/artillery`
- 任务接口: 异步任务
- 指标接口: 任务完成后通过 `/metrics` 获取 JSON
- 第一版能力: 理论射界、简化抛物线弹道剖面、DEM 地形遮挡判定、覆盖量化指标

## 创建任务

`POST /api/artillery/coverage`

```json
{
  "dem_id": "dem_xxx",
  "battery": {
    "lon": 79.80513693057287,
    "lat": 31.4827708959419,
    "height_m": 0,
    "altitude_mode": "agl"
  },
  "target": {
    "target_height_m": 0
  },
  "weapon": {
    "min_range_m": 1000,
    "max_range_m": 15000,
    "azimuth_deg": 90,
    "traverse_deg": 120,
    "muzzle_velocity_mps": 500,
    "elevation_deg": 45
  },
  "munition": {
    "munition_type": "he",
    "lethal_radius_m": 50,
    "effective_radius_m": 120
  },
  "analysis": {
    "use_dem_elevation": true,
    "use_terrain_masking": true,
    "sample_resolution_m": 250,
    "trajectory_samples": 80,
    "clearance_margin_m": 0,
    "output_simplify_tolerance_m": 30
  }
}
```

## 任务状态

`GET /api/artillery/coverage/{task_id}`

任务完成后，响应中包含 `metrics`、`outputs`、`output_files` 和 `model`。

## 量化指标

`GET /api/artillery/coverage/{task_id}/metrics`

任务未完成时返回 `409 TASK_METRICS_NOT_READY`。

```json
{
  "theoretical_area_m2": 52300000.0,
  "reachable_area_m2": 38900000.0,
  "terrain_masked_area_m2": 13400000.0,
  "terrain_masked_ratio": 0.2562,
  "lethal_area_m2": 42000000.0,
  "effective_area_m2": 47100000.0,
  "min_range_m": 1000.0,
  "max_range_m": 15000.0,
  "effective_traverse_deg": 120.0,
  "lethal_radius_m": 50.0,
  "effective_radius_m": 120.0,
  "sample_point_count": 740,
  "reachable_sample_count": 548,
  "masked_sample_count": 192,
  "min_clearance_m": -38.4,
  "mean_clearance_m": 96.2,
  "battery_ground_elevation_m": 3210.5,
  "battery_altitude_m": 3210.5
}
```

| 字段 | 单位 | 含义 |
| --- | --- | --- |
| `theoretical_area_m2` | 平方米 | 仅由射程、最小射程和方向射界形成的理论覆盖面积 |
| `reachable_area_m2` | 平方米 | 简化弹道剖面未被 DEM 地形截断的覆盖面积 |
| `terrain_masked_area_m2` | 平方米 | 因山体/地形高程穿过弹道剖面而被排除的面积 |
| `terrain_masked_ratio` | 0-1 | `terrain_masked_area_m2 / theoretical_area_m2` |
| `lethal_area_m2` | 平方米 | 可达区按杀伤半径缓冲后的面积 |
| `effective_area_m2` | 平方米 | 可达区按有效半径缓冲后的面积 |
| `sample_point_count` | 个 | 射界内参与弹道遮山判定的采样目标点数量 |
| `reachable_sample_count` | 个 | 弹道净空满足要求的采样点数量 |
| `masked_sample_count` | 个 | 被地形截断的采样点数量 |
| `min_clearance_m` | 米 | 所有采样弹道的最小地形净空，负值表示遮山 |
| `mean_clearance_m` | 米 | 所有采样弹道的平均最小净空 |

## 输出文件

`GET /api/artillery/coverage/{task_id}/outputs`

| kind | 文件 | 说明 |
| --- | --- | --- |
| `theoretical_geojson` | `theoretical.geojson` | 理论射界 |
| `reachable_geojson` | `reachable.geojson` | 地形净空后可达区 |
| `terrain_masked_geojson` | `terrain_masked.geojson` | 弹道遮山区 |
| `sample_points_geojson` | `sample_points.geojson` | 每个采样目标点的遮山判定和净空属性 |
| `model_metadata_json` | `model_metadata.json` | 模型参数和 DEM 投影信息 |
| `output_manifest_json` | `output_manifest.json` | 输出清单 |

下载单个输出：

`GET /api/artillery/coverage/{task_id}/outputs/{kind}`

## 模型边界

第一版采用工程近似：

- 弹道为二维抛物线剖面。
- 不包含风、空气阻力、药温、装药号、真实火控表、地球自转等高精度外弹道因素。
- `muzzle_velocity_mps` 和 `elevation_deg` 用于形成弹道弧高；模型会将弹道末端校正到目标点高程，用于地形净空/遮山判定。
- 适合做地理覆盖分析和方案对比，不适合作为实弹射击诸元。

## 调用流程

1. 上传或选择 DEM。
2. 调用 `POST /api/artillery/coverage` 创建任务。
3. 轮询 `GET /api/artillery/coverage/{task_id}`。
4. 任务 `status` 为 `finished` 后调用 `/metrics` 获取量化指标 JSON。
