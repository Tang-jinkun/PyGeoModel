# 第三方系统模型服务调用指南

## 1. 服务地址

默认本地服务地址：

```text
http://127.0.0.1:8000
```

健康检查：

```http
GET /api/health
```

正常响应：

```json
{
  "status": "ok"
}
```

## 2. 总体调用流程

第三方系统调用模型服务时，统一使用异步任务流程：

```text
上传 DEM -> 获取 dem_id -> POST 创建模型任务 -> 获取 task_id -> 轮询任务状态 -> GET /metrics 获取量化指标 JSON
```

模型接口不会直接接收 DEM 文件路径。模型请求中只传 `dem_id`。

## 3. DEM 数据准备

### 3.1 DEM 文件要求

- 格式：GeoTIFF，建议 `.tif` 或 `.tiff`
- 必须包含 CRS 坐标系
- 高程单位应为米
- DEM 范围必须覆盖模型输入点位和分析半径
- 默认上传限制：500 MB

### 3.2 小文件上传

`POST /api/dem/upload`

请求类型：`multipart/form-data`

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `file` | file | DEM GeoTIFF 文件 |

curl 示例：

```bash
curl -X POST http://127.0.0.1:8000/api/dem/upload \
  -F "file=@/path/to/dem.tif"
```

响应示例：

```json
{
  "dem_id": "dem_20260630_103000_ab12cd34",
  "filename": "dem.tif",
  "crs": "EPSG:4326",
  "bounds": [79.7, 31.4, 79.9, 31.6],
  "resolution": [0.0002777778, 0.0002777778],
  "width": 720,
  "height": 720,
  "nodata": -9999.0,
  "file_size_bytes": 12345678,
  "cog_path": "/data/dem/dem_20260630_103000_ab12cd34/dem.cog.tif",
  "cog_file_size_bytes": 12000000,
  "uploaded_at": "2026-06-30T10:30:00+00:00",
  "task_count": 0,
  "active_task_count": 0
}
```

第三方系统保存 `dem_id`，后续模型任务都使用这个值。

### 3.3 分片上传

适合大文件或网络不稳定场景。

第一步：创建上传会话

`POST /api/dem/uploads`

```json
{
  "filename": "large_dem.tif",
  "file_size_bytes": 734003200,
  "chunk_size_bytes": 10485760,
  "total_chunks": 70
}
```

响应：

```json
{
  "upload_id": "upload_xxx",
  "filename": "large_dem.tif",
  "file_size_bytes": 734003200,
  "chunk_size_bytes": 10485760,
  "total_chunks": 70,
  "uploaded_chunks": []
}
```

第二步：上传每个分片

`PUT /api/dem/uploads/{upload_id}/chunks/{chunk_index}`

请求类型：`multipart/form-data`

```bash
curl -X PUT http://127.0.0.1:8000/api/dem/uploads/upload_xxx/chunks/0 \
  -F "file=@chunk_0.part"
```

第三步：合并完成

`POST /api/dem/uploads/{upload_id}/complete`

响应为 `DemMetadata`，同样保存其中的 `dem_id`。

### 3.4 DEM 查询

列出 DEM：

```http
GET /api/dem
```

查询单个 DEM：

```http
GET /api/dem/{dem_id}
```

删除 DEM：

```http
DELETE /api/dem/{dem_id}
```

如果 DEM 已被任务引用，删除可能返回冲突错误。

## 4. 模型任务统一规范

### 4.1 创建任务

```http
POST /api/{model}/{task_type}
```

响应状态码：`202 Accepted`

通用响应字段：

```json
{
  "task_id": "xxx_task_20260630_103000_ab12cd34",
  "dem_id": "dem_20260630_103000_ab12cd34",
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

第三方系统保存 `task_id`。

### 4.2 查询任务

```http
GET /api/{model}/{task_type}/{task_id}
```

任务状态：

| status | 含义 |
| --- | --- |
| `pending` | 已排队 |
| `running` | 计算中 |
| `finished` | 已完成，可读取 `/metrics` |
| `failed` | 失败，查看 `message` |

建议轮询间隔：1-3 秒。大 DEM 或路线模型可以适当放大到 3-5 秒。

### 4.3 获取量化指标 JSON

```http
GET /api/{model}/{task_type}/{task_id}/metrics
```

只有任务 `status=finished` 后可用。

未完成时响应：

```json
{
  "detail": {
    "code": "TASK_METRICS_NOT_READY",
    "message": "Metrics are available only after the task is finished."
  }
}
```

### 4.4 获取输出文件

列出输出文件：

```http
GET /api/{model}/{task_type}/{task_id}/outputs
```

下载某个输出：

```http
GET /api/{model}/{task_type}/{task_id}/outputs/{kind}
```

第三方系统如果只需要量化指标，可以不调用输出文件接口。

## 5. 当前模型接口清单

| 模型 | 创建任务 | 查询任务 | 获取量化指标 |
| --- | --- | --- | --- |
| 雷达探测范围 | `POST /api/radar/coverage` | `GET /api/radar/coverage/{task_id}` | `GET /api/radar/coverage/{task_id}/metrics` |
| UAV 侦查范围 | `POST /api/uav/recon` | `GET /api/uav/recon/{task_id}` | `GET /api/uav/recon/{task_id}/metrics` |
| 观察哨侦测范围 | `POST /api/watchpost/detection` | `GET /api/watchpost/detection/{task_id}` | `GET /api/watchpost/detection/{task_id}/metrics` |
| 火炮火力覆盖/弹道遮山 | `POST /api/artillery/coverage` | `GET /api/artillery/coverage/{task_id}` | `GET /api/artillery/coverage/{task_id}/metrics` |
| 侦察车侦查范围 | `POST /api/recon-vehicle/coverage` | `GET /api/recon-vehicle/coverage/{task_id}` | `GET /api/recon-vehicle/coverage/{task_id}/metrics` |
| 车辆可达能力 | `POST /api/mobility/accessibility` | `GET /api/mobility/accessibility/{task_id}` | `GET /api/mobility/accessibility/{task_id}/metrics` |
| 空中安全走廊 | `POST /api/air-corridor/planning` | `GET /api/air-corridor/planning/{task_id}` | `GET /api/air-corridor/planning/{task_id}/metrics` |

## 6. 调用示例：侦察车侦查范围

创建任务：

```bash
curl -X POST http://127.0.0.1:8000/api/recon-vehicle/coverage \
  -H "Content-Type: application/json" \
  -d '{
    "dem_id": "dem_20260630_103000_ab12cd34",
    "vehicle": {
      "lon": 79.80513693057287,
      "lat": 31.4827708959419,
      "heading_deg": 90,
      "mast_height_m": 3
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
      "curvature_coeff": 0.75
    }
  }'
```

查询任务：

```bash
curl http://127.0.0.1:8000/api/recon-vehicle/coverage/{task_id}
```

获取指标：

```bash
curl http://127.0.0.1:8000/api/recon-vehicle/coverage/{task_id}/metrics
```

指标响应示例：

```json
{
  "theoretical_area_m2": 12000000.0,
  "visible_area_m2": 7600000.0,
  "blocked_area_m2": 4400000.0,
  "blocked_ratio": 0.3667,
  "max_range_m": 5000.0,
  "effective_view_angle_deg": 120.0,
  "coverage_point_count": 1,
  "route_length_m": 0.0,
  "average_visible_area_m2": 7600000.0,
  "overlap_area_m2": 0.0,
  "vehicle_ground_elevation_m": 3210.5,
  "sensor_altitude_m": 3213.5
}
```

## 7. 调用示例：UAV 航线侦查

```bash
curl -X POST http://127.0.0.1:8000/api/uav/recon \
  -H "Content-Type: application/json" \
  -d '{
    "dem_id": "dem_20260630_103000_ab12cd34",
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

指标接口：

```http
GET /api/uav/recon/{task_id}/metrics
```

## 8. 调用示例：雷达探测范围

```bash
curl -X POST http://127.0.0.1:8000/api/radar/coverage \
  -H "Content-Type: application/json" \
  -d '{
    "dem_id": "dem_20260630_103000_ab12cd34",
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

指标接口：

```http
GET /api/radar/coverage/{task_id}/metrics
```

## 9. 调用示例：观察哨侦测范围

```bash
curl -X POST http://127.0.0.1:8000/api/watchpost/detection \
  -H "Content-Type: application/json" \
  -d '{
    "dem_id": "dem_20260630_103000_ab12cd34",
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

指标接口：

```http
GET /api/watchpost/detection/{task_id}/metrics
```

## 10. 调用示例：火炮火力覆盖/弹道遮山

```bash
curl -X POST http://127.0.0.1:8000/api/artillery/coverage \
  -H "Content-Type: application/json" \
  -d '{
    "dem_id": "dem_20260630_103000_ab12cd34",
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

指标接口：

```http
GET /api/artillery/coverage/{task_id}/metrics
```

## 11. 错误响应

统一错误格式：

```json
{
  "detail": {
    "code": "ERROR_CODE",
    "message": "Human readable message."
  }
}
```

常见错误：

| code | HTTP | 说明 |
| --- | --- | --- |
| `DEM_NOT_FOUND` | 404 | `dem_id` 不存在 |
| `DEM_WITHOUT_CRS` | 400/500 | DEM 缺少坐标系 |
| `INVALID_DEM` | 400 | DEM 格式不支持或无法读取 |
| `RADAR_OUTSIDE_DEM` | 400 | 雷达点超出 DEM |
| `UAV_OUTSIDE_DEM` | 400 | UAV 点超出 DEM |
| `WATCHPOST_OUTSIDE_DEM` | 400 | 观察哨点超出 DEM |
| `ARTILLERY_OUTSIDE_DEM` | 400 | 火炮阵地点超出 DEM |
| `RECON_VEHICLE_OUTSIDE_DEM` | 400 | 侦察车点超出 DEM |
| `RANGE_OUTSIDE_DEM` | 400 | 分析范围和 DEM 覆盖范围不相交 |
| `TASK_NOT_FOUND` | 404 | `task_id` 不存在 |
| `TASK_METRICS_NOT_READY` | 409 | 任务未完成，暂不能读取指标 |
| `TASK_NOT_FINISHED` | 409 | 任务未完成，暂不能下载输出 |
| `GDAL_VIEWSHED_FAILED` | 500 | 地形通视计算失败 |

## 12. 第三方系统集成建议

- 保存 `dem_id` 和 `task_id`，不要依赖输出文件路径作为任务主键。
- 创建任务后不要立即请求 `/metrics`，先轮询任务状态。
- 只需要量化结果时，调用 `/metrics` 即可。
- 需要地图展示时，再调用 `/outputs` 和 `/outputs/{kind}`。
- 请求参数中的经纬度使用 WGS84，经度 `lon`、纬度 `lat`。
- DEM 必须覆盖输入点和最大分析范围，否则任务会失败或范围被裁剪。
- 大 DEM 建议走分片上传。
- 对路线类模型，`sample_interval_m` 越小结果越细，但计算时间越长。
