# 模型量化指标接口调用指南

第三方系统完整接入流程见 [third_party_model_service_integration_guide.md](third_party_model_service_integration_guide.md)。

## 是否支持“给参数后拿量化指标 JSON”

支持。

当前雷达、UAV、观察哨、火炮模型都采用同一套异步任务接口：

1. 调用模型 `POST` 接口，提交所需参数。
2. 接口立即返回 `task_id`，任务进入后台计算。
3. 轮询任务详情接口，直到 `status` 为 `finished`。
4. 调用 `/metrics` 接口，直接获取量化指标 JSON。

统一模式：

```http
POST /api/{model}/{task_type}
GET  /api/{model}/{task_type}/{task_id}
GET  /api/{model}/{task_type}/{task_id}/metrics
```

任务未完成时调用 `/metrics` 会返回 `409 TASK_METRICS_NOT_READY`。

## 当前可用模型接口

| 模型 | 创建任务 | 查询任务 | 获取量化指标 JSON |
| --- | --- | --- | --- |
| 雷达探测范围 | `POST /api/radar/coverage` | `GET /api/radar/coverage/{task_id}` | `GET /api/radar/coverage/{task_id}/metrics` |
| UAV 侦查范围 | `POST /api/uav/recon` | `GET /api/uav/recon/{task_id}` | `GET /api/uav/recon/{task_id}/metrics` |
| 观察哨侦测范围 | `POST /api/watchpost/detection` | `GET /api/watchpost/detection/{task_id}` | `GET /api/watchpost/detection/{task_id}/metrics` |
| 火炮火力覆盖/弹道遮山 | `POST /api/artillery/coverage` | `GET /api/artillery/coverage/{task_id}` | `GET /api/artillery/coverage/{task_id}/metrics` |
| 侦察车侦查范围 | `POST /api/recon-vehicle/coverage` | `GET /api/recon-vehicle/coverage/{task_id}` | `GET /api/recon-vehicle/coverage/{task_id}/metrics` |
| 车辆可达能力 | `POST /api/mobility/accessibility` | `GET /api/mobility/accessibility/{task_id}` | `GET /api/mobility/accessibility/{task_id}/metrics` |
| 空中安全走廊 | `POST /api/air-corridor/planning` | `GET /api/air-corridor/planning/{task_id}` | `GET /api/air-corridor/planning/{task_id}/metrics` |

## 通用响应流程

创建任务响应示例：

```json
{
  "task_id": "artillery_task_20260630_025030_03e6bde2",
  "dem_id": "dem_xxx",
  "status": "pending",
  "progress": 0,
  "message": "queued",
  "metrics": null,
  "outputs": null,
  "output_files": [],
  "model": null,
  "warnings": [],
  "request": {}
}
```

轮询任务响应中，重点看：

```json
{
  "task_id": "artillery_task_20260630_025030_03e6bde2",
  "status": "finished",
  "progress": 100,
  "message": "finished",
  "metrics": {
    "theoretical_area_m2": 12758553.91,
    "reachable_area_m2": 0.0,
    "terrain_masked_area_m2": 12758553.91,
    "terrain_masked_ratio": 1.0
  }
}
```

当 `status` 为 `finished` 后，可以调用：

```http
GET /api/artillery/coverage/artillery_task_20260630_025030_03e6bde2/metrics
```

返回值就是纯量化指标 JSON，不包含任务记录、输出文件清单等外围信息。

## 状态码

| 状态码 | 场景 | 说明 |
| --- | --- | --- |
| `202` | 创建任务成功 | 返回 `task_id`，后台开始计算 |
| `200` | 查询成功 | 任务详情或指标 JSON |
| `400` | 参数或空间位置错误 | 例如点位超出 DEM、参数范围不合法 |
| `404` | 资源不存在 | DEM 或任务不存在 |
| `409` | 任务状态不允许 | 任务未完成时读取 `/metrics` |
| `500` | 服务端计算失败 | DEM 处理、GDAL、输出文件等异常 |

错误响应格式：

```json
{
  "detail": {
    "code": "TASK_METRICS_NOT_READY",
    "message": "Artillery metrics are available only after the task is finished."
  }
}
```

## curl 调用示例：火炮弹道遮山

创建任务：

```bash
curl -X POST http://127.0.0.1:8000/api/artillery/coverage \
  -H 'Content-Type: application/json' \
  -d '{
    "dem_id": "dem_xxx",
    "battery": {
      "lon": 79.80513693057287,
      "lat": 31.4827708959419,
      "height_m": 0,
      "altitude_mode": "agl"
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
      "clearance_margin_m": 0
    }
  }'
```

查询任务：

```bash
curl http://127.0.0.1:8000/api/artillery/coverage/{task_id}
```

获取量化指标：

```bash
curl http://127.0.0.1:8000/api/artillery/coverage/{task_id}/metrics
```

火炮指标示例：

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
  "sample_point_count": 740,
  "reachable_sample_count": 548,
  "masked_sample_count": 192,
  "min_clearance_m": -38.4,
  "mean_clearance_m": 96.2
}
```

## curl 调用示例：UAV 航线侦查

创建任务：

```bash
curl -X POST http://127.0.0.1:8000/api/uav/recon \
  -H 'Content-Type: application/json' \
  -d '{
    "dem_id": "dem_xxx",
    "uav": {
      "lon": 79.80513693057287,
      "lat": 31.4827708959419,
      "altitude_m": 500,
      "altitude_mode": "agl",
      "heading_deg": 0,
      "pitch_deg": -45
    },
    "route": {
      "waypoints": [
        {
          "lon": 79.80513693057287,
          "lat": 31.4827708959419,
          "altitude_m": 500,
          "altitude_mode": "agl",
          "heading_deg": 0,
          "pitch_deg": -45
        },
        {
          "lon": 79.82,
          "lat": 31.49,
          "altitude_m": 500,
          "altitude_mode": "agl",
          "heading_deg": 45,
          "pitch_deg": -45
        }
      ],
      "sample_interval_m": 500
    },
    "sensor": {
      "sensor_type": "camera",
      "h_fov_deg": 60,
      "v_fov_deg": 40,
      "max_range_m": 5000,
      "min_range_m": 0
    },
    "analysis": {
      "use_terrain_occlusion": true
    }
  }'
```

获取量化指标：

```bash
curl http://127.0.0.1:8000/api/uav/recon/{task_id}/metrics
```

UAV 指标示例：

```json
{
  "theoretical_area_m2": 12000000.0,
  "visible_area_m2": 9000000.0,
  "blocked_area_m2": 3000000.0,
  "blocked_ratio": 0.25,
  "max_ground_distance_m": 5000.0,
  "coverage_point_count": 8,
  "route_length_m": 3500.0,
  "average_visible_area_m2": 2100000.0,
  "overlap_area_m2": 7800000.0
}
```

## curl 调用示例：雷达

创建任务：

```bash
curl -X POST http://127.0.0.1:8000/api/radar/coverage \
  -H 'Content-Type: application/json' \
  -d '{
    "dem_id": "dem_xxx",
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
      "azimuth_deg": 0,
      "beam_width_deg": 360
    },
    "advanced": {
      "use_curvature": true,
      "curvature_coeff": 0.75,
      "min_elevation_deg": 0,
      "max_elevation_deg": 32
    }
  }'
```

获取量化指标：

```bash
curl http://127.0.0.1:8000/api/radar/coverage/{task_id}/metrics
```

## curl 调用示例：观察哨

创建任务：

```bash
curl -X POST http://127.0.0.1:8000/api/watchpost/detection \
  -H 'Content-Type: application/json' \
  -d '{
    "dem_id": "dem_xxx",
    "observer": {
      "lon": 79.80513693057287,
      "lat": 31.4827708959419,
      "height_m": 2
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
      "curvature_coeff": 0.75
    }
  }'
```

获取量化指标：

```bash
curl http://127.0.0.1:8000/api/watchpost/detection/{task_id}/metrics
```

## 前端或第三方系统建议

前端/第三方系统不需要解析输出文件也能拿到核心指标。建议只依赖以下流程：

```text
POST 创建任务 -> 保存 task_id -> GET 查询任务直到 finished -> GET /metrics 读取指标 JSON
```

如果需要地图展示，再额外调用：

```http
GET /api/{model}/{task_type}/{task_id}/outputs
GET /api/{model}/{task_type}/{task_id}/outputs/{kind}
```
