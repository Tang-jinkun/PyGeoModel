# 雷达探测模型前端接入指南

本文面向调用 PyGeoModel 后端服务的第三方前端开发者，说明如何提交雷达探测任务、轮询结果、读取统一 JSON、下载并渲染 GLB，以及判断指定三维目标是否可被探测。

## 1. 接入概览

默认服务地址：

```text
http://127.0.0.1:8000
```

生产环境应将下文的 `API_BASE` 替换为实际后端地址。推荐由前端网关将 `/api` 和 `/outputs` 同源代理到后端，避免跨域和大文件下载问题。

完整调用流程：

```text
上传 DEM
  -> 获得 dem_id
  -> 创建雷达任务
  -> 获得 task_id
  -> 轮询任务至 finished/failed
  -> 读取 metrics、model、diagnostics 和 output_files
  -> 下载 scene_glb 并显示三维探测域
  -> 按需调用 evaluate-target 判断具体目标
```

健康检查：

```http
GET /api/health
```

正常响应：

```json
{"status":"ok"}
```

## 2. DEM 数据准备

雷达任务只接收 `dem_id`，不直接接收服务器文件路径。

上传 GeoTIFF：

```http
POST /api/dem/upload
Content-Type: multipart/form-data
```

```bash
curl -X POST "${API_BASE}/api/dem/upload" \
  -F "file=@/data/dem.tif"
```

响应中的 `dem_id` 用于后续雷达任务：

```json
{
  "dem_id": "dem_20260713_080113_884937cf",
  "filename": "dem.tif",
  "crs": "EPSG:4326",
  "bounds": [79.2, 31.0, 80.4, 32.0]
}
```

DEM 要求：

- 格式为带 CRS 的 GeoTIFF；
- 高程单位为米；
- 应覆盖雷达位置和请求的探测半径；
- NoData 会被视为未知区域，不会自动当成可探测区域；
- 雷达点必须落在有效 DEM 像元上。

## 3. 创建雷达探测任务

```http
POST /api/radar/coverage
Content-Type: application/json
```

推荐的全向 50 km 穹顶请求：

```json
{
  "dem_id": "dem_20260713_080113_884937cf",
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
    "beam_width_deg": 360
  },
  "advanced": {
    "use_curvature": true,
    "curvature_coeff": 0.75,
    "output_simplify_tolerance_m": 30,
    "voxel_grid_size": 128,
    "voxel_vertical_levels": 16,
    "voxel_max_height_m": 3000,
    "min_elevation_deg": 0,
    "max_elevation_deg": 90,
    "visual_dome_mode": true,
    "height_layers_m": [0, 100, 300, 500, 1000, 2000, 3000]
  },
  "reserved_radar_params": {}
}
```

主要字段：

| 字段 | 单位 | 说明 |
| --- | --- | --- |
| `radar.lon` / `radar.lat` | 度 | 雷达 WGS84 经纬度 |
| `radar.height_m` | 米 | 雷达离地高度，不是海拔 |
| `target.height_m` | 米 | 基础二维覆盖计算使用的目标离地高度 |
| `coverage.max_range_m` | 米 | 请求最大探测距离，允许值不超过 100 km |
| `coverage.scan_mode` | - | `omni` 全向或 `sector` 扇区 |
| `coverage.azimuth_deg` | 度 | 扇区中心方位角，正北为 0，顺时针增加 |
| `coverage.beam_width_deg` | 度 | 水平波束宽度；全向建议传 360 |
| `advanced.min_elevation_deg` | 度 | 最小俯仰角；设为 0 时不产生雷达以下的波束 |
| `advanced.max_elevation_deg` | 度 | 最大俯仰角；设为 90 时生成完整上半球穹顶 |
| `advanced.use_curvature` | - | 是否启用地球曲率修正 |
| `advanced.curvature_coeff` | - | 曲率修正系数，默认 0.75 |
| `advanced.height_layers_m` | 米 | 需要生成的离地高度分层 |

`vertical_beam_width_deg` 由后端根据最大、最小俯仰角重新计算，前端不需要自行维护。

### 3.1 可选雷达方程参数

当以下四项全部有效时，后端启用雷达方程距离限制：

- `frequency_hz`
- `transmit_power_w`
- `antenna_gain_db`
- `receiver_sensitivity_dbm`

示例：

```json
{
  "reserved_radar_params": {
    "frequency_hz": 3000000000,
    "transmit_power_w": 10000,
    "antenna_gain_db": 30,
    "receiver_sensitivity_dbm": -100,
    "target_rcs_m2": 1,
    "system_loss_db": 6,
    "noise_figure_db": 3
  }
}
```

参数不完整时，模型使用 `coverage.max_range_m`，并在 `diagnostics.notes` 中说明雷达方程未启用。

### 3.2 创建响应

成功创建返回 `202 Accepted`：

```json
{
  "task_id": "task_20260716_005136_d3218625",
  "dem_id": "dem_20260713_080113_884937cf",
  "status": "pending",
  "progress": 0,
  "message": "queued",
  "metrics": null,
  "outputs": null,
  "output_files": [],
  "model": null,
  "diagnostics": null,
  "warnings": [],
  "request": {}
}
```

前端必须保存 `task_id`。创建接口不会同步等待模型计算完成。

## 4. 轮询任务状态

```http
GET /api/radar/coverage/{task_id}
```

状态含义：

| 状态 | 处理方式 |
| --- | --- |
| `pending` | 已排队，继续轮询 |
| `running` | 正在计算，显示 `progress` 和 `message` |
| `finished` | 停止轮询并加载结果 |
| `failed` | 停止轮询并展示 `message` |

建议轮询间隔为 2 秒，页面离开或任务切换时使用 `AbortController` 取消请求。

```ts
type RadarTaskStatus = "pending" | "running" | "finished" | "failed";

async function waitForRadarTask(apiBase: string, taskId: string, signal?: AbortSignal) {
  while (true) {
    const response = await fetch(`${apiBase}/api/radar/coverage/${taskId}`, { signal });
    if (!response.ok) throw new Error(`查询任务失败: HTTP ${response.status}`);
    const task = await response.json();
    if (task.status === "finished") return task;
    if (task.status === "failed") throw new Error(task.message || "雷达任务失败");
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
}
```

## 5. 任务结果和统一 JSON

完成后的任务响应包含：

- `metrics`：面积统计；
- `model`：实际生效参数、投影和三维场景元数据；
- `diagnostics`：距离限制、遮挡和警告说明；
- `output_files`：所有输出文件及下载地址；
- `request`：原始任务请求。

统一结果文件为 `output_manifest.json`，当前模型合同版本位于：

```json
{
  "model": {
    "coverage_contract_version": 2
  }
}
```

下载统一 JSON：

```http
GET /api/radar/coverage/{task_id}/outputs/output_manifest_json
```

其顶层结构为：

```json
{
  "files": [],
  "metrics": {},
  "model": {},
  "diagnostics": {},
  "warnings": []
}
```

前端可使用任务响应中的结构化字段，也可以下载 manifest 做归档和跨系统交换。

## 6. 输出文件

列出输出：

```http
GET /api/radar/coverage/{task_id}/outputs
```

每个文件项示例：

```json
{
  "kind": "scene_glb",
  "label": "Radar Maximum Detection Domain GLB",
  "url": "/outputs/task_xxx/radar_detection_domain.glb",
  "download_url": "/api/radar/coverage/task_xxx/outputs/scene_glb",
  "filename": "radar_detection_domain.glb",
  "media_type": "model/gltf-binary",
  "size_bytes": 12000000,
  "exists": true
}
```

推荐前端使用 `download_url`，因为该接口会检查任务状态和输出类型。`url` 是同一文件的静态地址，适合受控同源部署。

主要输出类型：

| `kind` | 用途 |
| --- | --- |
| `scene_glb` | 雷达最大三维探测域，包含穹顶、DEM 下边界、网格和扫描动画 |
| `radar_platform_glb` | 雷达平台三维模型 |
| `visible_geojson` | 基准目标高度下的可探测区域 |
| `blocked_geojson` | 基准目标高度下的地形遮挡区域 |
| `range_geojson` | DEM 有效域裁剪后的理论覆盖范围 |
| `model_metadata_json` | 模型、指标、诊断和警告 |
| `output_manifest_json` | 统一输出清单 |
| `min_visible_height_tif` | 每个位置达到可见所需的最低离地高度 |
| `height_layers_manifest_json` | 分层高度输出索引 |

## 7. 下载 GLB

```http
GET /api/radar/coverage/{task_id}/outputs/scene_glb
```

响应类型为 `model/gltf-binary`。GLB 是自包含文件，不依赖外部纹理或 `.bin` 文件。

前端应在下载前检查：

- 任务必须为 `finished`；
- `output_files` 中 `scene_glb.exists` 必须为 `true`；
- 根据 `size_bytes` 提示加载进度；
- 当前服务端和内置前端的 GLB 硬限制为 50,000,000 字节；
- 大文件应支持取消下载并在卸载后释放 GPU 资源。

```ts
async function downloadGlb(apiBase: string, taskId: string, signal?: AbortSignal) {
  const url = `${apiBase}/api/radar/coverage/${taskId}/outputs/scene_glb`;
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`GLB 下载失败: HTTP ${response.status}`);
  return response.arrayBuffer();
}
```

## 8. GLB 地理参考合同

雷达 GLB 使用 glTF 标准 Y-up 坐标，但顶点是局部米制坐标，不能直接把整个模型放到经纬度位置后结束。地理参考存放在：

```text
asset.extras.scene3d
```

核心字段：

```json
{
  "schema_version": 1,
  "task_id": "task_xxx",
  "model_id": "radar",
  "units": "metre",
  "source_crs": "EPSG:32644",
  "geographic_crs": "EPSG:4326",
  "origin": {
    "projected_x": 386500,
    "projected_y": 3483700,
    "longitude": 79.805,
    "latitude": 31.482,
    "altitude_amsl_m": 3700
  },
  "axes": {
    "x": "east",
    "y": "up",
    "z": "south"
  }
}
```

局部 GLB 顶点 `[x, y, z]` 转回真实坐标：

```text
投影东坐标 = origin.projected_x + x
投影北坐标 = origin.projected_y - z
海拔 AMSL = origin.altitude_amsl_m + y
```

然后使用 `source_crs` 将投影坐标转换为 `EPSG:4326`。

必须校验：

- `schema_version === 1`
- `model_id === "radar"`
- `task_id` 与当前任务一致
- `units === "metre"`
- `axes` 为 `X=east, Y=up, Z=south`

## 9. Three.js 加载与扫描动画

基础加载：

```ts
import * as THREE from "three";
import {
  GLTFLoader,
  type GLTF
} from "three/examples/jsm/loaders/GLTFLoader.js";

function parseGlb(buffer: ArrayBuffer): Promise<GLTF> {
  return new Promise((resolve, reject) => {
    new GLTFLoader().parse(buffer, "", resolve, reject);
  });
}

const buffer = await downloadGlb(API_BASE, taskId, abortController.signal);
const gltf = await parseGlb(buffer);
const metadata = gltf.parser.json.asset?.extras?.scene3d;

if (metadata?.task_id !== taskId || metadata?.model_id !== "radar") {
  throw new Error("GLB 元数据与当前雷达任务不匹配");
}

scene.add(gltf.scene);

const mixer = new THREE.AnimationMixer(gltf.scene);
for (const clip of gltf.animations) mixer.clipAction(clip).play();

const clock = new THREE.Clock();
function render() {
  requestAnimationFrame(render);
  mixer.update(clock.getDelta());
  renderer.render(scene, camera);
}
render();
```

GLB 中已经包含扫描动画关键帧。前端不需要自行旋转扫描面，也不应假设所有扫描线长度相同。

### 9.1 MapLibre 叠加

MapLibre 中建议使用 `CustomLayerInterface` 和共享 WebGL context。为了在几十公里范围保持投影准确，应逐顶点执行：

1. 按上节公式恢复 UTM 坐标；
2. 使用 `proj4` 转换为 WGS84；
3. 使用 `MercatorCoordinate.fromLngLat({lng, lat}, altitude)` 转为 Mercator；
4. 所有顶点减去同一个 Mercator 锚点，模型组放置在该锚点；
5. 地图 terrain exaggeration 设置为 `1`，避免 GLB 与 DEM 高程不一致。

核心转换示例：

```ts
import maplibregl from "maplibre-gl";
import proj4 from "proj4";

function projectGlbVertex(
  point: [number, number, number],
  metadata: any,
  anchor: maplibregl.MercatorCoordinate
): [number, number, number] {
  const [x, y, z] = point;
  const east = metadata.origin.projected_x + x;
  const north = metadata.origin.projected_y - z;
  const altitude = metadata.origin.altitude_amsl_m + y;
  const [lng, lat] = proj4(metadata.source_crs, "EPSG:4326", [east, north]);
  const mercator = maplibregl.MercatorCoordinate.fromLngLat({ lng, lat }, altitude);
  return [mercator.x - anchor.x, mercator.y - anchor.y, mercator.z - anchor.z];
}
```

不要只用雷达经纬度平移整个局部模型。50 km 范围下，这种局部平面近似会产生可见偏差。

### 9.2 Three.js/MapLibre 渲染循环

自定义图层应满足：

```ts
const mixer = new THREE.AnimationMixer(group);
for (const clip of animations) mixer.clipAction(clip).play();

render(gl, matrix) {
  camera.projectionMatrix.fromArray(matrix).multiply(anchorMatrix);
  mixer.setTime(performance.now() / 1000);
  renderer.resetState();
  renderer.render(scene, camera);
  map.triggerRepaint();
}
```

移除图层时必须：

- `mixer.stopAllAction()`；
- 释放 geometry、material 和 texture；
- `renderer.dispose()`；
- 移除 WebGL context lost 监听；
- 当没有三维任务时恢复原 terrain exaggeration。

## 10. 三维目标点判定

任务完成后，可以判断指定经纬度和海拔目标是否位于雷达探测域内：

```http
POST /api/radar/coverage/{task_id}/evaluate-target
Content-Type: application/json
```

```json
{
  "x": 79.815663,
  "y": 31.482869,
  "z": 4745.88,
  "target_type": "aircraft"
}
```

坐标合同：

| 字段 | 含义 |
| --- | --- |
| `x` | WGS84 经度 |
| `y` | WGS84 纬度 |
| `z` | 海拔高程 AMSL，单位米 |
| `target_type` | 可选目标类型；当前原样返回，不参与 RCS 或距离计算 |

响应示例：

```json
{
  "task_id": "task_xxx",
  "detectable": true,
  "reason": "detectable",
  "target_type": "aircraft",
  "target_crs": "EPSG:4326",
  "projected_crs": "EPSG:32644",
  "input_x": 79.815663,
  "input_y": 31.482869,
  "input_z": 4745.88,
  "projected_x": 387506.07,
  "projected_y": 3483725.17,
  "distance_m": 1000,
  "slant_range_m": 1414.1,
  "azimuth_deg": 90,
  "elevation_deg": 45,
  "radar_altitude_m": 3746,
  "terrain_elevation_m": 3833,
  "target_height_agl_m": 912.88,
  "minimum_detectable_altitude_m": 3833,
  "maximum_detectable_altitude_m": 53736,
  "within_range": true,
  "within_beam": true,
  "within_elevation": true,
  "within_dem": true,
  "terrain_blocked": false
}
```

`reason` 枚举：

| 值 | 含义 |
| --- | --- |
| `detectable` | 位于完整探测域内 |
| `outside_range` | 超出有效斜距或解析球面上界 |
| `outside_sector` | 超出水平扫描扇区 |
| `below_min_elevation` | 低于最小俯仰角 |
| `above_max_elevation` | 高于最大俯仰角 |
| `outside_dem` | 位于 DEM 分析范围外 |
| `dem_nodata` | 落在 DEM 或最低可见高度的 NoData 像元 |
| `below_terrain` | 目标海拔低于地表 |
| `terrain_blocked` | 低于该位置的最低可探测高度 |

前端应以 `detectable` 作为最终布尔结果，以各个 `within_*` 字段和 `reason` 做诊断展示。

## 11. GeoJSON 和二维结果

如果前端只需要二维覆盖，可直接下载：

```text
/api/radar/coverage/{task_id}/outputs/visible_geojson
/api/radar/coverage/{task_id}/outputs/blocked_geojson
/api/radar/coverage/{task_id}/outputs/range_geojson
```

这些 GeoJSON 使用 WGS84，经纬度顺序为 `[longitude, latitude]`，可直接加入 MapLibre GeoJSON source。

## 12. 错误处理

业务错误格式：

```json
{
  "detail": {
    "code": "TASK_NOT_FINISHED",
    "message": "Target evaluation is available only after the task is finished."
  }
}
```

常见状态码：

| HTTP | 场景 |
| --- | --- |
| `202` | 任务已创建 |
| `400` | 参数、坐标或 DEM 范围不合法 |
| `404` | 任务、DEM 或输出不存在 |
| `409` | 任务未完成，结果暂不可用 |
| `422` | 请求 JSON 未通过 Pydantic 字段校验 |
| `500` | GDAL、栅格处理或 GLB 导出失败 |

不要只根据 HTTP 200 判断模型成功；异步任务仍需检查 `status`。

## 13. 部署与跨域

后端通过 `PYGEOMODEL_CORS_ORIGINS` 控制允许的前端来源。生产环境推荐同源反向代理：

```text
https://example.com/api/*     -> pygeomodel-backend:8000/api/*
https://example.com/outputs/* -> pygeomodel-backend:8000/outputs/*
```

需要保证代理：

- 不限制 GLB、GeoTIFF 的响应体大小；
- 保留 `Content-Type` 和 `Content-Length`；
- GLB 下载超时应高于普通 JSON 请求；
- `/outputs` 不应被前端 SPA fallback 接管；
- 如果启用鉴权，`fetch` 下载 GLB 时必须携带相同凭据。

## 14. 最小前端客户端

```ts
const API_BASE = "https://example.com";

export async function createRadarTask(request: unknown) {
  const response = await fetch(`${API_BASE}/api/radar/coverage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request)
  });
  if (!response.ok) throw await apiError(response);
  return response.json();
}

export async function getRadarTask(taskId: string) {
  const response = await fetch(`${API_BASE}/api/radar/coverage/${taskId}`);
  if (!response.ok) throw await apiError(response);
  return response.json();
}

export async function evaluateRadarTarget(
  taskId: string,
  target: { x: number; y: number; z: number; target_type?: string | null }
) {
  const response = await fetch(
    `${API_BASE}/api/radar/coverage/${taskId}/evaluate-target`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(target)
    }
  );
  if (!response.ok) throw await apiError(response);
  return response.json();
}

async function apiError(response: Response) {
  const payload = await response.json().catch(() => null);
  const message = payload?.detail?.message || `HTTP ${response.status}`;
  return new Error(message);
}
```

## 15. 接入检查清单

- [ ] DEM 上传后保存 `dem_id`
- [ ] 创建任务后保存 `task_id`
- [ ] 以 2 秒间隔轮询，并处理 `failed`
- [ ] 只在 `finished` 后下载输出
- [ ] 使用 `download_url` 获取 GLB
- [ ] 校验 `asset.extras.scene3d`
- [ ] 按 `X=east, Y=up, Z=south` 还原坐标
- [ ] MapLibre 中使用 1:1 地形高程
- [ ] 播放 GLB 内置扫描动画
- [ ] 切换任务时取消下载并释放 GPU 资源
- [ ] 目标判定使用经度、纬度和 AMSL 海拔
- [ ] 将 `target_type` 视为当前不参与探测方程的可选元数据
