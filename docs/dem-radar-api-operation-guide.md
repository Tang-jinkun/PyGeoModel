# DEM 数据与雷达模型端到端 API 操作手册

更新日期：2026-08-21
适用版本：当前 `agent/multi-tile-dem` 分支源码
适用对象：只调用 PyGeoModel 后端 API 的业务系统、数据处理程序和前端应用

本次更新补充：`scene_glb` 和 `fusion_scene_glb` 现在可包含独立的地形遮挡红色体积；红色只表示确定的地形遮挡，不表示 DEM 缺失或计算未知。三维雷达网格默认使用标准 LOD，白色网格线保持可见。

本文覆盖两块能力：

1. DEM 数据如何进入系统、如何确认可用、如何渲染和删除；
2. 使用已经准备好的 `dem_id` 创建单雷达或多雷达任务，轮询任务，读取统计结果，下载产物，以及判断目标点是否可探测。

本文按照真实业务流程编排。调用方不需要知道 DEM 最终是全国单 TIFF、多个裁剪 TIFF 还是普通小文件；上传或导入完成后，雷达接口统一只接收一个 `dem_id`。

## 0. 端到端业务流程

```text
启动后端
  ↓
健康检查 GET /api/health
  ↓
准备 DEM
  ├─ 全国单个大 TIFF：服务器本地导入
  ├─ 多块裁剪 TIFF：创建批次、上传 tiles、完成合并、轮询 ready
  └─ 普通小 TIFF：单文件上传或分块上传
  ↓
GET /api/dem/{dem_id} 确认 DEM 已发布
  ↓
POST /api/radar/tasks 创建单雷达或多雷达任务
  ↓
GET /api/radar/tasks/{task_id} 轮询 pending/running/finished/failed
  ↓
读取 metrics、stations、outputs，下载 GeoJSON/TIF/JSON/GLB
  ↓
POST evaluate-target 或 evaluate-targets 查询目标可探测性
```

最重要的业务约束：

- DEM 必须先完成导入或上传，并能通过 `GET /api/dem/{dem_id}` 查询；
- 雷达任务创建时只传 `dem_id`，不在雷达请求中上传 TIFF；
- 雷达计算是异步任务，创建接口返回 `202` 后必须轮询任务状态；
- 目标评估必须在雷达覆盖计算完成后执行；
- 任务结果的下载类型以 `GET /api/radar/tasks/{task_id}/outputs` 返回的产物清单为准，不要猜测文件名。

---

## 1. 基础约定

### 1.1 服务地址

默认后端地址：

```text
http://127.0.0.1:8000
```

本文将它记为 `API_BASE`。

Linux/macOS：

```bash
export API_BASE=http://127.0.0.1:8000
```

Windows PowerShell：

```powershell
$API_BASE = "http://127.0.0.1:8000"
```

如果后端部署在其他机器，只需要把地址替换为实际协议、IP 和端口，例如 `http://192.168.1.20:8000`。

当前接口没有额外的登录 Token 要求。生产环境如果在网关后面增加认证，应由网关统一补充认证头，本文的业务请求体不变。

### 1.2 启动与健康检查

使用 Docker Compose 启动后端：

```bash
docker compose up -d backend
```

健康检查：

```bash
curl -sS "$API_BASE/api/health"
```

预期响应：

```json
{
  "status": "ok",
  "integrations": {
    "tianditu": {
      "configured": false
    }
  }
}
```

`status=ok` 只说明 API 服务已经响应。DEM 是否存在、GDAL 是否可用、某个雷达任务是否成功，要分别通过后续接口确认。

接口契约也可以通过 FastAPI 自动文档查看：

```text
GET /openapi.json
GET /docs
```

### 1.3 请求和响应格式

除文件上传、图片瓦片和文件下载外，接口均使用 JSON。

JSON 请求统一带上：

```http
Content-Type: application/json
```

成功的常见状态码：

| 状态码 | 含义 |
| --- | --- |
| `200` | 查询、评估、下载前置检查或删除成功 |
| `201` | DEM 上传、上传会话创建或分块上传完成 |
| `202` | 异步任务或 DEM 批次已经接受，后台继续处理 |

失败响应通常是：

```json
{
  "detail": {
    "code": "ERROR_CODE",
    "message": "可读的错误说明"
  }
}
```

调用方应记录 `code`、`message`、`dem_id`、`batch_id` 或 `task_id`，不要只记录 HTTP 状态码。

### 1.4 坐标、高程和异步约定

- 雷达站位置和目标点的 `lon`、`lat` 使用 WGS84 经纬度，也就是 `EPSG:4326`；
- 雷达站 `radar.height_m` 是天线相对雷达站地面的高度，单位米；
- 覆盖任务中的 `target.height_m` 是目标相对目标地面的高度，单位米；
- 单目标评估接口中的 `z` 是目标的海拔高度（AMSL），不是离地高度；
- 批量目标评估可以使用 `altitude_reference: "amsl"` 或 `"agl"`；
- 创建雷达任务后，不能用固定等待时间判断完成，必须轮询任务详情。

---

## 2. DEM 数据接入方式选择

| 数据情况 | 推荐方式 | 结果 |
| --- | --- | --- |
| 全国级、20–200GB、原始 TIFF 已在服务器磁盘 | 服务器本地导入 | 生成 COG-only DEM，原始全国 TIFF 不复制进应用数据目录 |
| 几块已经切好的 TIFF，由调用方通过 API 传入 | DEM 批次上传 | 多个 TIFF 合并为一个 `dem_id`，雷达只使用这个 `dem_id` |
| 一个普通的小 TIFF | `POST /api/dem/upload` | 系统生成一个唯一 `dem_id` 并转换为 COG |
| 一个较大的 TIFF，需要断点续传 | 上传会话接口 | 先传分块，最后合并为一个 DEM |

### 2.1 DEM 在系统中的逻辑结构

对模型而言，DEM 是一个逻辑数据集：

```text
dem_id
  ├── metadata.json
  └── dem.cog.tif       # 计算和地形渲染的标准数据源
```

全国导入完成后，应用数据目录主要保留 COG 和元数据。多块 TIFF 批次完成后，上传暂存目录会被清理，只保留合并后的 COG 和元数据。

历史 DEM 如果只有原始 TIFF、尚未有 COG，第一次执行模型计算或 DEM 瓦片渲染时会按需生成 COG。新数据建议在导入或上传阶段直接生成 COG。

### 2.2 计算范围和内存行为

雷达任务不会把全国 DEM 全量读入内存。计算流程是：

```text
全国或批次 COG
    ↓
以雷达位置和有效探测距离确定任务窗口
    ↓
Rasterio window 读取局部窗口
    ↓
投影到雷达所在区域的局部 UTM
    ↓
执行地形遮挡和覆盖计算
```

系统仍然会限制最大计算网格。最大探测距离越大、DEM 分辨率越高，任务通常越耗时，也越容易触发范围或网格限制。

---

## 3. 流程 A：全国单个 TIFF 的服务器本地导入

全国 TIFF 不建议通过浏览器或普通 HTTP 上传。正确流程是把文件放到部署主机的导入目录，再在后端容器内执行导入脚本。

### 3.1 准备宿主机导入目录

在包含 `docker-compose.yml` 的项目目录下创建：

```text
data/
└── import/
    └── national.tif
```

Compose 会将它只读挂载到后端容器：

```text
宿主机：data/import/national.tif
容器内：/workspace/import/national.tif
```

确认文件路径和磁盘空间后，再执行下一步。导入过程中需要在 `data` 所在磁盘写入 COG 临时文件，必须预留足够空间。

### 3.2 执行导入命令

在项目根目录执行：

```bash
docker compose exec -T backend \
  python /app/scripts/import_dem.py \
  --source /workspace/import/national.tif \
  --dem-id national-dem
```

Windows PowerShell 使用单行命令最稳妥：

```powershell
docker compose exec -T backend python /app/scripts/import_dem.py --source /workspace/import/national.tif --dem-id national-dem
```

参数说明：

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--source` | 是 | 容器内可访问的源 GeoTIFF 路径 |
| `--dem-id` | 是 | 后续所有 API 请求引用的稳定 DEM ID |
| `--data-dir` | 否 | 覆盖应用数据目录，通常不需要传 |

`dem_id` 只能使用字母、数字、下划线和连字符，并且必须以字母或数字开头。例如：`national-dem`、`national-dem-2026`、`region_001`。

如果目标 `dem_id` 已经存在，导入会返回 `DEM_ALREADY_EXISTS`，不会覆盖原数据。需要换一个 ID，或者在确认没有任务引用旧 DEM 后先删除旧 DEM。

### 3.3 导入时的自动校验

导入流程会依次检查：

- 源文件存在且可读取；
- 文件是 GeoTIFF；
- 存在 CRS；
- 只有一个波段；
- 波段是数值类型；
- 宽度、高度有效；
- 地理范围有限且面积大于零。

检查通过后生成 COG，配置为：

- 内部瓦片大小 `256×256`；
- `DEFLATE` 压缩；
- `PREDICTOR=2`；
- `BILINEAR` 金字塔重采样；
- 自动生成 overviews。

系统会在发布前校验 COG 的单波段、内部瓦片、`256×256` block 和 overviews。发布采用临时目录加原子重命名，失败时不会留下可被模型误用的半成品 `metadata.json`。

### 3.4 导入成功后的确认

先列出 DEM：

```bash
curl -sS "$API_BASE/api/dem" | jq .
```

再查询指定 DEM：

```bash
curl -sS "$API_BASE/api/dem/national-dem" | jq .
```

重点确认：

```json
{
  "dem_id": "national-dem",
  "filename": "national.tif",
  "crs": "EPSG:4326",
  "bounds": [70.0, 15.0, 140.0, 55.0],
  "resolution": [0.0002777778, 0.0002777778],
  "width": 252000,
  "height": 144000,
  "cog_path": "dem.cog.tif",
  "cog_file_size_bytes": 123456789,
  "task_count": 0,
  "active_task_count": 0
}
```

示例中的范围和尺寸只是格式示例，实际值以服务返回为准。雷达请求使用的就是：

```json
{
  "dem_id": "national-dem"
}
```

### 3.5 导入失败时怎么处理

命令失败时会在标准错误输出 JSON，例如：

```json
{
  "error": "DEM_WITHOUT_CRS",
  "message": "DEM is missing coordinate reference system."
}
```

处理顺序：

1. 记录错误码和消息；
2. 检查源 TIFF 的 CRS、波段数、数据类型和文件完整性；
3. 检查 `data` 所在磁盘空间；
4. 确认目标 `dem_id` 没有残留的旧目录；
5. 修正数据或换新的 `dem_id` 后重新导入；
6. 再通过 `GET /api/dem/{dem_id}` 确认成功。

---

## 4. 流程 B：多块 TIFF 批次上传并合并

这个流程适用于用户手上有几块已经切好的 GeoTIFF，希望后端把它们当作一个 DEM 使用。调用方不需要先自己拼接，也不需要在雷达请求中分别传每个 TIFF。

### 4.1 批次内 TIFF 的格式要求

同一个批次中的所有 TIFF 必须满足：

- 是可读取的 GeoTIFF；
- 都有 CRS，且 CRS 完全一致；
- 都是单波段；
- 分辨率一致；
- 数据类型一致；
- NoData 定义一致；
- 像元网格对齐；
- 地理范围有效。

瓦片可以相邻，也可以有轻微重叠，但不建议在重叠区域存在明显高程冲突。若瓦片的 CRS、分辨率或网格不一致，应先在数据处理环节统一，再上传。

### 4.2 创建批次

接口：

```http
POST /api/dem/batches
Content-Type: application/json
```

请求：

```json
{
  "dem_id": "region-west-2026",
  "label": "西部测试区域 DEM"
}
```

调用：

```bash
curl -sS -X POST "$API_BASE/api/dem/batches" \
  -H "Content-Type: application/json" \
  -d '{
    "dem_id": "region-west-2026",
    "label": "西部测试区域 DEM"
  }'
```

成功返回 `201`：

```json
{
  "batch_id": "batch_20260821_100000_ab12cd34",
  "dem_id": "region-west-2026",
  "label": "西部测试区域 DEM",
  "status": "uploading",
  "filenames": [],
  "file_count": 0,
  "error": null
}
```

必须保存 `batch_id`。后续上传、完成和状态查询都使用它。`dem_id` 可以省略，省略后服务自动生成一个唯一 ID；如果业务系统要长期保存和复用 DEM，建议主动传入稳定的 `dem_id`。

### 4.3 上传 TIFF 文件

接口：

```http
POST /api/dem/batches/{batch_id}/tiles
Content-Type: multipart/form-data
字段名：files
```

一次上传多个文件：

```bash
curl -sS -X POST "$API_BASE/api/dem/batches/batch_20260821_100000_ab12cd34/tiles" \
  -F "files=@/data/dem/tile_01.tif" \
  -F "files=@/data/dem/tile_02.tif" \
  -F "files=@/data/dem/tile_03.tif"
```

也可以分多次上传，每次只传一个文件：

```powershell
$batchId = "batch_20260821_100000_ab12cd34"

curl.exe -sS -X POST "$API_BASE/api/dem/batches/$batchId/tiles" -F "files=@D:\dem\tile_01.tif"
curl.exe -sS -X POST "$API_BASE/api/dem/batches/$batchId/tiles" -F "files=@D:\dem\tile_02.tif"
curl.exe -sS -X POST "$API_BASE/api/dem/batches/$batchId/tiles" -F "files=@D:\dem\tile_03.tif"
```

成功返回：

```json
{
  "batch_id": "batch_20260821_100000_ab12cd34",
  "filenames": ["tile_01.tif", "tile_02.tif", "tile_03.tif"],
  "file_count": 3
}
```

上传规则：

- 字段名必须是 `files`；
- 文件名只保留 basename，不要依赖客户端路径；
- 同一个批次内不能重复上传同名文件；
- 当前批次接口按完整文件接收，不是单文件分块续传接口；
- 很大的单块 TIFF 如果不适合 HTTP 传输，应改用服务器本地导入，或使用普通 DEM 的分块上传会话接口；
- 每次成功后建议检查 `file_count` 是否递增。

### 4.4 完成批次合并

确认所有文件都已经上传后调用：

```bash
curl -sS -X POST "$API_BASE/api/dem/batches/batch_20260821_100000_ab12cd34/complete"
```

接口返回 `202`，返回状态可能是 `merging`，也可能因为处理很快直接变为 `ready`：

```json
{
  "batch_id": "batch_20260821_100000_ab12cd34",
  "dem_id": "region-west-2026",
  "status": "merging",
  "filenames": ["tile_01.tif", "tile_02.tif", "tile_03.tif"],
  "file_count": 3,
  "error": null
}
```

不要在 `merging` 或 `validating` 状态重复调用 `/complete`。重复提交会返回 `DEM_BATCH_BUSY`。

### 4.5 轮询批次状态

接口：

```http
GET /api/dem/batches/{batch_id}
```

Linux/macOS 逻辑：

```text
循环执行 GET /api/dem/batches/{batch_id}
读取 status
如果 status=ready，继续雷达流程
如果 status=failed，读取 error 并停止
否则等待 1–3 秒后继续
```

Windows PowerShell：

```powershell
$batchId = "batch_20260821_100000_ab12cd34"

do {
    Start-Sleep -Seconds 2
    $batchStatus = curl.exe -sS "$API_BASE/api/dem/batches/$batchId" | ConvertFrom-Json
    Write-Host "status=$($batchStatus.status), files=$($batchStatus.file_count)"
} while ($batchStatus.status -notin @("ready", "failed"))

if ($batchStatus.status -eq "failed") {
    throw $batchStatus.error
}

$demId = $batchStatus.dem_id
Write-Host "ready dem_id=$demId"
```

状态及调用方动作：

| 状态 | 含义 | 调用方动作 |
| --- | --- | --- |
| `uploading` | 仍可上传文件 | 继续上传，全部完成后调用 `/complete` |
| `validating` | 正在校验瓦片 | 等待，不要重复完成 |
| `merging` | 正在构建 COG | 等待，不要调用雷达 |
| `ready` | DEM 已发布 | 使用返回的 `dem_id` 调用雷达 |
| `failed` | 校验或合并失败 | 读取 `error`，修正数据后创建新批次 |

### 4.6 批次完成后的确认

```bash
curl -sS "$API_BASE/api/dem/region-west-2026"
```

重点确认：

```json
{
  "dem_id": "region-west-2026",
  "source_type": "tiled_upload_batch",
  "source_tile_count": 3,
  "source_filenames": ["tile_01.tif", "tile_02.tif", "tile_03.tif"],
  "cog_path": "dem.cog.tif"
}
```

从这一刻开始，雷达请求只传：

```json
{
  "dem_id": "region-west-2026"
}
```

---

## 5. 流程 C：普通小 TIFF 上传

### 5.1 单文件上传

接口：

```http
POST /api/dem/upload
Content-Type: multipart/form-data
字段名：file
```

Linux/macOS：

```bash
curl -sS -X POST "$API_BASE/api/dem/upload" \
  -F "file=@/data/dem/test.tif"
```

Windows PowerShell：

```powershell
curl.exe -sS -X POST "$API_BASE/api/dem/upload" -F "file=@D:\dem\test.tif"
```

成功返回 `201`，例如：

```json
{
  "dem_id": "dem_20260821_100501_9f2b4c1a",
  "filename": "test.tif",
  "crs": "EPSG:4326",
  "bounds": [102.0, 29.0, 102.5, 29.5],
  "resolution": [0.0002777778, 0.0002777778],
  "width": 1800,
  "height": 1800,
  "nodata": -9999.0,
  "file_size_bytes": 12345678,
  "cog_path": "dem.cog.tif",
  "cog_file_size_bytes": 9876543,
  "task_count": 0,
  "active_task_count": 0
}
```

单文件上传不会由调用方指定 `dem_id`，必须保存响应中的 ID，后续雷达请求引用该 ID。

### 5.2 分块上传

当单个 TIFF 不适合一次性上传时，可以使用上传会话接口。它和多块 TIFF 批次是两种不同的概念：

- 分块上传：一个 TIFF 被拆成多个二进制块，最后合并成一个 DEM；
- 批次上传：多个独立 TIFF 作为多块瓦片合并成一个 DEM。

#### 第一步：创建上传会话

接口：

```http
POST /api/dem/uploads
Content-Type: application/json
```

请求示例：

```json
{
  "filename": "large-region.tif",
  "file_size_bytes": 104857600,
  "chunk_size_bytes": 8388608,
  "total_chunks": 13
}
```

`total_chunks` 必须满足：

```text
ceil(file_size_bytes / chunk_size_bytes)
```

调用：

```bash
curl -sS -X POST "$API_BASE/api/dem/uploads" \
  -H "Content-Type: application/json" \
  -d '{
    "filename": "large-region.tif",
    "file_size_bytes": 104857600,
    "chunk_size_bytes": 8388608,
    "total_chunks": 13
  }'
```

响应：

```json
{
  "upload_id": "upload_20260821_101000_3ab2cd11",
  "filename": "large-region.tif",
  "file_size_bytes": 104857600,
  "chunk_size_bytes": 8388608,
  "total_chunks": 13,
  "uploaded_chunks": []
}
```

#### 第二步：逐块上传

接口：

```http
PUT /api/dem/uploads/{upload_id}/chunks/{chunk_index}
Content-Type: multipart/form-data
字段名：file
```

块索引从 `0` 开始，最后一块可以小于 `chunk_size_bytes`，其他块必须是完整块。

```bash
curl -sS -X PUT \
  "$API_BASE/api/dem/uploads/upload_20260821_101000_3ab2cd11/chunks/0" \
  -F "file=@/tmp/large-region.part0000"
```

每次成功返回：

```json
{
  "upload_id": "upload_20260821_101000_3ab2cd11",
  "chunk_index": 0,
  "uploaded_chunks": 1,
  "total_chunks": 13
}
```

调用方可以重试某个块；上传完成判断以服务返回的 `uploaded_chunks` 为准。块大小不匹配会返回 `INVALID_CHUNK_SIZE`。

#### 第三步：完成上传

```bash
curl -sS -X POST \
  "$API_BASE/api/dem/uploads/upload_20260821_101000_3ab2cd11/complete"
```

服务会按块索引合并文件，读取 GeoTIFF 元数据，生成 COG，并返回最终自动生成的 `dem_id`。缺块时返回 `UPLOAD_INCOMPLETE`。

---

## 6. DEM 查询、渲染和删除接口

### 6.1 查询 DEM 列表

```http
GET /api/dem
```

```bash
curl -sS "$API_BASE/api/dem"
```

返回数组。每项包含 `dem_id`、文件元数据、COG 信息和任务引用数量：

| 字段 | 说明 |
| --- | --- |
| `dem_id` | 雷达请求引用的稳定 ID |
| `filename` | 原始文件名或批次标签，仅用于显示和兼容 |
| `crs` | 源 DEM CRS |
| `bounds` | `[left, bottom, right, top]` |
| `resolution` | `[x_resolution, y_resolution]` |
| `width` / `height` | 栅格尺寸 |
| `nodata` | NoData 值，可能为 `null` |
| `cog_path` | 计算和渲染使用的 COG 文件名，通常为 `dem.cog.tif` |
| `source_type` | 例如批次上传时为 `tiled_upload_batch` |
| `source_tile_count` | 批次来源瓦片数 |
| `task_count` | 引用该 DEM 的历史任务数 |
| `active_task_count` | 当前运行或排队任务数 |

### 6.2 查询单个 DEM

```http
GET /api/dem/{dem_id}
```

```bash
curl -sS "$API_BASE/api/dem/region-west-2026"
```

找不到时返回 `404` 和 `DEM_NOT_FOUND`。

### 6.3 获取 DEM 颜色瓦片

```http
GET /api/dem/{dem_id}/tiles/{z}/{x}/{y}.png
```

```bash
curl -fL \
  "$API_BASE/api/dem/region-west-2026/tiles/8/210/98.png" \
  -o dem-color.png
```

这个接口用于地图上的 DEM 颜色渲染。

### 6.4 获取地形高度瓦片

```http
GET /api/dem/{dem_id}/terrain/{z}/{x}/{y}.png
```

```bash
curl -fL \
  "$API_BASE/api/dem/region-west-2026/terrain/8/210/98.png" \
  -o dem-terrain.png
```

这个接口用于三维地形或 Terrarium 类高度渲染。`z`、`x`、`y` 必须是合法的 Web Mercator 瓦片坐标。

### 6.5 删除 DEM

```http
DELETE /api/dem/{dem_id}
```

```bash
curl -sS -X DELETE "$API_BASE/api/dem/region-west-2026"
```

只有没有被任务引用的 DEM 才能删除。被任务引用时返回 `409`、`DEM_IN_USE`。推荐顺序：

1. 停止或等待相关任务；
2. 删除不再需要的雷达任务；
3. 重新查询 `GET /api/dem/{dem_id}`，确认 `task_count` 为 `0`；
4. 再删除 DEM。

---

## 7. 雷达模型请求模型

雷达单站和多站使用同一个创建接口：

```http
POST /api/radar/tasks
```

通过请求体的 `task_type` 区分：

```json
{
  "task_type": "single"
}
```

或：

```json
{
  "task_type": "multi"
}
```

旧接口已经移除，不要调用：

```text
/api/radar/coverage/*
/api/radar/multi-coverage/*
```

### 7.1 单雷达请求字段

单雷达请求结构：

```json
{
  "task_type": "single",
  "dem_id": "region-west-2026",
  "radar": {},
  "target": {},
  "coverage": {},
  "advanced": {},
  "reserved_radar_params": {}
}
```

#### `dem_id`

必须是已经存在并可读取的 DEM ID。服务创建任务时会检查 DEM 和计算范围；不存在时返回 `404`。

#### `radar`

| 字段 | 约束 | 说明 |
| --- | --- | --- |
| `lon` | `-180` 到 `180` | WGS84 经度 |
| `lat` | `-90` 到 `90` | WGS84 纬度 |
| `height_m` | 大于等于 `0` | 天线离地高度，米 |

#### `target`

| 字段 | 约束 | 说明 |
| --- | --- | --- |
| `height_m` | 大于等于 `0`，默认 `0` | 覆盖计算所使用的目标离地高度，米 |

#### `coverage`

| 字段 | 约束 | 说明 |
| --- | --- | --- |
| `max_range_m` | `0 < value <= 100000` | 最大名义探测距离，米 |
| `scan_mode` | `omni` 或 `sector` | 全向或扇区 |
| `azimuth_deg` | `0 <= value < 360` | 扇区中心方位角，度 |
| `beam_width_deg` | `0 < value <= 360` | 扇区开角，度 |

`scan_mode=omni` 时，方位角和波束宽度不作为扇区裁剪；仍建议传清晰一致的值，例如 `azimuth_deg=0`、`beam_width_deg=360`。

#### `advanced`

| 字段 | 默认值 | 约束和说明 |
| --- | --- | --- |
| `use_curvature` | `true` | 是否考虑地球曲率 |
| `curvature_coeff` | `0.75` | `0` 到 `1` |
| `output_simplify_tolerance_m` | `null` | GeoJSON 简化容差，非负米数 |
| `voxel_grid_size` | `128` | `32` 到 `512` |
| `voxel_vertical_levels` | `16` | `4` 到 `64` |
| `voxel_max_height_m` | `3000` | `500` 到 `10000` |
| `min_elevation_deg` | `-8` | `-10` 到 `89` |
| `max_elevation_deg` | `90` | `0` 到 `90`，必须不小于最小仰角 |
| `vertical_beam_width_deg` | `32` | 服务会根据最大/最小仰角重新归一化 |
| `visual_dome_mode` | `true` | 三维可视化退化或补齐时使用视觉穹顶模式 |
| `height_layers_m` | `[]` | 0 到 `voxel_max_height_m`，最多 20 个值 |

如果没有明确的精度和三维体素需求，建议先使用默认 `advanced`。提高 `voxel_grid_size`、`voxel_vertical_levels` 或 `voxel_max_height_m` 会增加计算时间和结果体积。

#### `reserved_radar_params`

该对象用于保留雷达方程相关参数，例如 `frequency_hz`、`transmit_power_w`、`antenna_gain_db`、`receiver_sensitivity_dbm`、`target_rcs_m2` 等。当前不需要电磁参数时可以省略；不要把它当作普通必填参数。

### 7.2 多雷达请求字段

多雷达请求结构：

```json
{
  "task_type": "multi",
  "dem_id": "region-west-2026",
  "presentation_mode": "aggregate",
  "radars": [
    {
      "radar_id": "R1",
      "name": "西侧雷达",
      "radar": {},
      "target": {},
      "coverage": {},
      "advanced": {},
      "reserved_radar_params": {}
    }
  ]
}
```

`radars` 必须有 `2` 至 `256` 个站点。每个站点都有独立的 `radar`、`target`、`coverage`、`advanced` 和预留参数。

`radar_id`：

- 必填；
- 长度 1 到 64；
- 只能使用字母、数字、下划线和连字符；
- 同一个任务内必须唯一。

`presentation_mode`：

| 值 | 站点数 | 结果 |
| --- | --- | --- |
| `aggregate` | 2–256 | 联合可见区、重叠区、盲区、覆盖次数、站点汇总 |
| `cooperative_3d` | 2–5 | 聚合结果，加各站三维资产、设备模型和协同交会 GLB |

---

## 8. 完整流程一：调用单雷达模型

下面假设 DEM 已经准备好，ID 为 `region-west-2026`。

### 8.1 创建单雷达任务

最小可用请求：

```bash
curl -sS -X POST "$API_BASE/api/radar/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "single",
    "dem_id": "region-west-2026",
    "radar": {
      "lon": 102.1000,
      "lat": 29.6000,
      "height_m": 15
    },
    "target": {
      "height_m": 0
    },
    "coverage": {
      "max_range_m": 50000,
      "scan_mode": "omni",
      "azimuth_deg": 0,
      "beam_width_deg": 360
    }
  }'
```

成功返回 `202`。示例：

```json
{
  "task_type": "single",
  "task_id": "task_20260821_102000_8cd1ef20",
  "dem_id": "region-west-2026",
  "status": "pending",
  "progress": 0,
  "message": "",
  "created_at": "2026-08-21T10:20:00+00:00",
  "updated_at": "2026-08-21T10:20:00+00:00",
  "metrics": null,
  "outputs": null,
  "output_files": [],
  "warnings": []
}
```

调用方必须保存 `task_id`。后面的轮询、结果下载、剖面和目标评估都使用它。

如果雷达点不在 DEM 范围内、雷达点落在 NoData、探测范围大部分超出 DEM，创建阶段会直接失败。例如：

| 错误码 | 含义 |
| --- | --- |
| `DEM_NOT_FOUND` | `dem_id` 不存在 |
| `RADAR_OUTSIDE_DEM` | 雷达点在 DEM 外 |
| `RADAR_ON_DEM_NODATA` | 雷达点落在 DEM 无效像元 |
| `RANGE_OUTSIDE_DEM` | 探测范围与 DEM 覆盖不足 |
| `INVALID_DEM` | DEM 元数据或数据本身无效 |

### 8.2 轮询单雷达任务

接口：

```http
GET /api/radar/tasks/{task_id}
```

```bash
curl -sS "$API_BASE/api/radar/tasks/task_20260821_102000_8cd1ef20"
```

轮询示例（PowerShell）：

```powershell
$taskId = "task_20260821_102000_8cd1ef20"

do {
    $task = curl.exe -sS "$API_BASE/api/radar/tasks/$taskId" | ConvertFrom-Json
    Write-Host "status=$($task.status), progress=$($task.progress), message=$($task.message)"

    if ($task.status -in @("pending", "running")) {
        Start-Sleep -Seconds 2
    }
} while ($task.status -in @("pending", "running"))

if ($task.status -ne "finished") {
    Write-Error ("Radar task failed: " + $task.message)
}
```

单雷达终态：

| 状态 | 含义 | 下一步 |
| --- | --- | --- |
| `pending` | 已创建，等待执行 | 继续轮询 |
| `running` | 正在计算 | 继续轮询 |
| `finished` | 计算成功 | 读取指标、产物和目标评估 |
| `failed` | 计算失败 | 读取 `message`、`warnings`，修正后重跑 |

### 8.3 查询单雷达指标

只有任务 `finished` 后才能查询：

```http
GET /api/radar/tasks/{task_id}/metrics
```

```bash
curl -sS "$API_BASE/api/radar/tasks/task_20260821_102000_8cd1ef20/metrics"
```

返回示例：

```json
{
  "requested_theoretical_area_m2": 7850000000.0,
  "theoretical_area_m2": 7800000000.0,
  "unknown_area_m2": 5000000.0,
  "visible_area_m2": 5400000000.0,
  "blocked_area_m2": 2400000000.0,
  "blocked_ratio": 0.307692,
  "terrain_visible_area_m2": 5400000000.0,
  "beam_eligible_area_m2": 7800000000.0,
  "radar_equation_limited_area_m2": 0.0
}
```

面积单位是平方米。指标适合在相同 DEM、参数和模型版本下做方案对比，不应直接理解为真实设备的绝对探测概率。

### 8.4 查询单雷达产物清单

```http
GET /api/radar/tasks/{task_id}/outputs
```

```bash
curl -sS "$API_BASE/api/radar/tasks/task_20260821_102000_8cd1ef20/outputs"
```

返回的每个产物描述包含：

- `kind`：下载接口使用的产物类型；
- `label`：可读名称；
- `filename`：实际文件名；
- `media_type`：媒体类型；
- `required`：是否为标准必选产物；
- `exists`：文件是否存在；
- `download_path`、`download_url`：下载路径。

### 8.5 下载单雷达产物

不要根据任务目录或文件名自行拼接下载地址，使用产物清单中的 `kind`：

```http
GET /api/radar/tasks/{task_id}/outputs/{kind}
```

下载可见区：

```bash
curl -fL \
  "$API_BASE/api/radar/tasks/task_20260821_102000_8cd1ef20/outputs/visible_geojson" \
  -o visible.geojson
```

下载地形遮挡区：

```bash
curl -fL \
  "$API_BASE/api/radar/tasks/task_20260821_102000_8cd1ef20/outputs/blocked_geojson" \
  -o blocked.geojson
```

下载雷达探测域 GLB：

```bash
curl -fL \
  "$API_BASE/api/radar/tasks/task_20260821_102000_8cd1ef20/outputs/scene_glb" \
  -o radar_detection_domain.glb
```

下载雷达平台 GLB：

```bash
curl -fL \
  "$API_BASE/api/radar/tasks/task_20260821_102000_8cd1ef20/outputs/radar_platform_glb" \
  -o radar_platform.glb
```

`scene_glb` 内的雷达结果节点具有独立语义：

| 节点 | 含义 |
| --- | --- |
| `radar_result/detectable_shell` | 当前雷达可见体积，绿色 |
| `radar_result/blocked_volume` | 理论探测域内、确定被地形遮挡的体积，红色半透明 |
| `radar_result/detection_floor` | 雷达探测底面（如果该任务生成） |
| `radar_result/shell_grid` | 默认显示的标准白色网格 |
| `radar_result/shell_grid_sparse` | 稀疏网格，默认隐藏 |
| `radar_result/shell_grid_detailed` | 细密网格，默认隐藏 |

红色节点写入 `visibility_semantics=terrain_occluded`。前端默认显示红色节点，并在三维图层面板提供独立的“遮挡”开关；关闭该开关只隐藏红色遮挡体，不影响绿色可见体积或扫描面。绿色配色调整不会覆盖红色语义材质；历史没有 `blocked_volume` 节点的 GLB 仍可正常加载。网格线是显示辅助线，不代表额外的雷达 API 字段。

只有重新生成任务后，新的 GLB 才会包含上述节点和最新网格显示参数；已下载的历史 GLB 不会被服务端原地修改。

单雷达标准产物：

| `kind` | 文件类型 | 用途 |
| --- | --- | --- |
| `viewshed_tif` | GeoTIFF | 可见性栅格 |
| `visible_geojson` | GeoJSON | 可见区域 |
| `blocked_geojson` | GeoJSON | 地形遮挡区域 |
| `range_geojson` | GeoJSON | 理论探测范围 |
| `min_visible_height_tif` | GeoTIFF | 最小可见高度 |
| `height_layers_manifest_json` | JSON | 高度分层清单 |
| `voxel_manifest_json` | JSON | 体素数据清单 |
| `voxel_points_bin` | BIN | 体素点数据 |
| `clipped_volume_manifest_json` | JSON | 裁剪体清单 |
| `clipped_volume_cells_bin` | BIN | 裁剪体数据 |
| `model_metadata_json` | JSON | 模型元数据和计算口径 |
| `output_manifest_json` | JSON | 产物清单、大小和校验信息 |
| `scene_glb` | GLB | 雷达探测域三维模型 |
| `radar_platform_glb` | GLB | 雷达设备平台三维模型 |

如果某个可选或延迟生成的资产不存在，以 `outputs` 或产物清单中的 `exists` 为准。

### 8.6 查询地形剖面

剖面只支持单雷达任务，并且任务必须已经完成。

单条剖面：

```http
GET /api/radar/tasks/{task_id}/profile?lon={lon}&lat={lat}&samples={samples}
```

```bash
curl -sS \
  "$API_BASE/api/radar/tasks/task_20260821_102000_8cd1ef20/profile?lon=102.1200&lat=29.6200&samples=160"
```

返回包含：

- 目标距离和方位角；
- 雷达地面高程和目标地面高程；
- 雷达海拔和目标海拔；
- 是否被遮挡；
- 遮挡点位置和净空；
- 目标所需最低高度；
- 采样点列表。

批量剖面：

```http
POST /api/radar/tasks/{task_id}/profiles
Content-Type: application/json
```

```bash
curl -sS -X POST \
  "$API_BASE/api/radar/tasks/task_20260821_102000_8cd1ef20/profiles" \
  -H "Content-Type: application/json" \
  -d '{
    "targets": [
      {"id": "target-001", "lon": 102.1200, "lat": 29.6200},
      {"id": "target-002", "lon": 102.1400, "lat": 29.6300}
    ],
    "samples": 180,
    "include_samples": false
  }'
```

一次最多提交 500 个剖面目标。

### 8.7 查询单个目标是否可探测

接口：

```http
POST /api/radar/tasks/{task_id}/evaluate-target
Content-Type: application/json
```

请求中的 `z` 是 AMSL 海拔高度：

```bash
curl -sS -X POST \
  "$API_BASE/api/radar/tasks/task_20260821_102000_8cd1ef20/evaluate-target" \
  -H "Content-Type: application/json" \
  -d '{
    "x": 102.1200,
    "y": 29.6200,
    "z": 3250,
    "target_type": "aircraft"
  }'
```

响应中的核心字段：

```json
{
  "task_id": "task_20260821_102000_8cd1ef20",
  "task_type": "single",
  "detected": true,
  "detail": {
    "detectable": true,
    "reason": "detectable",
    "distance_m": 2100.4,
    "slant_range_m": 2200.1,
    "azimuth_deg": 35.2,
    "elevation_deg": 12.4,
    "terrain_elevation_m": 1700.0,
    "target_height_agl_m": 1550.0,
    "minimum_detectable_altitude_m": 1900.0,
    "maximum_detectable_altitude_m": 4800.0,
    "within_range": true,
    "within_beam": true,
    "within_elevation": true,
    "within_dem": true,
    "terrain_blocked": false
  },
  "contributors": []
}
```

常见 `reason`：

| `reason` | 含义 |
| --- | --- |
| `detectable` | 满足距离、扇区、仰角、DEM 和地形通视条件 |
| `outside_range` | 超出有效探测距离 |
| `outside_sector` | 不在雷达扇区内 |
| `below_min_elevation` | 低于最小仰角 |
| `above_max_elevation` | 高于最大仰角 |
| `outside_dem` | 目标点不在 DEM 覆盖范围内 |
| `dem_nodata` | 目标点落在 DEM NoData |
| `below_terrain` | 目标海拔低于当地地形 |
| `terrain_blocked` | 被中间地形遮挡 |

单目标评估仅在单雷达任务 `finished` 后可用。若任务未完成，返回 `409` 和 `TASK_NOT_FINISHED`。

### 8.8 批量评估多个目标

一次可以提交 1 到 500 个目标，`target_id` 必须唯一：

```http
POST /api/radar/tasks/{task_id}/evaluate-targets
Content-Type: application/json
```

```bash
curl -sS -X POST \
  "$API_BASE/api/radar/tasks/task_20260821_102000_8cd1ef20/evaluate-targets" \
  -H "Content-Type: application/json" \
  -d '{
    "targets": [
      {
        "target_id": "aircraft-001",
        "x": 102.1200,
        "y": 29.6200,
        "altitude_reference": "amsl",
        "altitude_m": 3250,
        "target_type": "aircraft"
      },
      {
        "target_id": "ground-001",
        "x": 102.1300,
        "y": 29.6250,
        "altitude_reference": "agl",
        "altitude_m": 20,
        "target_type": "ground"
      }
    ]
  }'
```

高度规则：

- `amsl`：`altitude_m` 必填，直接作为目标海拔；
- `agl`：`altitude_m` 可省略，省略时按 `0` 处理，服务会读取目标点 DEM 高程并相加；
- 结果按 `target_id` 关联，不要假定成功结果数组与输入数组长度相同；
- 单个目标失败不会中断整个批次，成功项在 `results`，失败项在 `errors`。

### 8.9 重跑、取消和删除单雷达任务

重跑需要 `Idempotency-Key`，长度为 8–128 个字符：

```bash
curl -sS -X POST \
  "$API_BASE/api/radar/tasks/task_20260821_102000_8cd1ef20/rerun" \
  -H "Idempotency-Key: rerun-20260821-001"
```

同一次网络重试必须复用同一个幂等键；明确要发起新的重跑时才更换幂等键。

取消排队或运行中的任务：

```bash
curl -sS -X POST \
  "$API_BASE/api/radar/tasks/task_20260821_102000_8cd1ef20/cancel"
```

删除任务记录和可清理产物：

```bash
curl -sS -X DELETE \
  "$API_BASE/api/radar/tasks/task_20260821_102000_8cd1ef20"
```

删除前应确认调用方已经下载并归档需要保留的产物。

---

## 9. 完整流程二：调用多雷达模型

### 9.1 创建多雷达任务

```bash
curl -sS -X POST "$API_BASE/api/radar/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "multi",
    "dem_id": "region-west-2026",
    "presentation_mode": "aggregate",
    "radars": [
      {
        "radar_id": "R1",
        "name": "西侧雷达",
        "radar": {
          "lon": 102.1000,
          "lat": 29.6000,
          "height_m": 15
        },
        "target": {
          "height_m": 0
        },
        "coverage": {
          "max_range_m": 50000,
          "scan_mode": "omni",
          "azimuth_deg": 0,
          "beam_width_deg": 360
        }
      },
      {
        "radar_id": "R2",
        "name": "东侧雷达",
        "radar": {
          "lon": 102.2500,
          "lat": 29.6600,
          "height_m": 20
        },
        "target": {
          "height_m": 0
        },
        "coverage": {
          "max_range_m": 50000,
          "scan_mode": "omni",
          "azimuth_deg": 0,
          "beam_width_deg": 360
        }
      }
    ]
  }'
```

多雷达创建成功返回 `202`，任务 ID 通常以 `multi_task_` 开头。不要在业务代码中只依赖 ID 前缀分派功能，应该读取响应中的 `task_type`。

### 9.2 多雷达任务状态

```bash
curl -sS "$API_BASE/api/radar/tasks/multi_task_20260821_103000_7ef10a22"
```

多雷达状态包括：

```text
pending → running → finished
                    └→ partial
                    └→ failed
```

`partial` 表示部分站点完成或部分站点失败，不等于整个任务完全成功。此时必须读取 `stations`、`warnings` 和 `message`，按站点决定哪些结果可以使用。

### 9.3 查询多雷达站点结果

所有站点概览：

```http
GET /api/radar/tasks/{task_id}/radars
```

```bash
curl -sS "$API_BASE/api/radar/tasks/multi_task_20260821_103000_7ef10a22/radars"
```

指定站点：

```http
GET /api/radar/tasks/{task_id}/radars/{radar_id}
```

```bash
curl -sS \
  "$API_BASE/api/radar/tasks/multi_task_20260821_103000_7ef10a22/radars/R1"
```

站点摘要通常包含：

- `radar_id`、`name`；
- `status` 和 `message`；
- 该站点的 `metrics`；
- `diagnostics`；
- 该站点的 `outputs`；
- 如果生成三维资产，对应的 `scene_task_id` 和 `scene_status`。

### 9.4 下载多雷达聚合产物

多雷达仍使用同一个下载入口：

```bash
curl -fL \
  "$API_BASE/api/radar/tasks/multi_task_20260821_103000_7ef10a22/outputs/visible_union_geojson" \
  -o visible_union.geojson

curl -fL \
  "$API_BASE/api/radar/tasks/multi_task_20260821_103000_7ef10a22/outputs/overlap_geojson" \
  -o overlap.geojson

curl -fL \
  "$API_BASE/api/radar/tasks/multi_task_20260821_103000_7ef10a22/outputs/blind_geojson" \
  -o blind.geojson

curl -fL \
  "$API_BASE/api/radar/tasks/multi_task_20260821_103000_7ef10a22/outputs/coverage_count_geojson" \
  -o coverage_count.geojson
```

多雷达标准产物：

| `kind` | 用途 |
| --- | --- |
| `visible_union_geojson` | 至少一个雷达可见的联合区域 |
| `overlap_geojson` | 两个或更多雷达重叠可见区域 |
| `blind_geojson` | 联合分析范围内的盲区 |
| `coverage_count_geojson` | 每个位置被多少雷达覆盖 |
| `stations_geojson` | 雷达站位置 |
| `station_summaries_json` | 各站状态和指标汇总 |
| `fusion_scene_glb` | 多雷达融合三维场景，可选 |
| `cooperative_intersection_glb` | 协同三维交会体，可选 |

`aggregate` 模式的 `fusion_scene_glb` 还可能包含 `multi_radar_fusion/blocked_volume`：它表示联合理论探测域内所有已完成雷达都不可见的区域。任意一个雷达可见时仍归入联合绿色区域。任务为 `partial` 或存在站点失败时，不生成确定性的联合红色体积，以免把失败站点造成的数据未知误判为遮挡。

`cooperative_3d` 模式下，各站自己的 `scene_glb` 分别包含本站绿色可见体积和红色地形遮挡体；`cooperative_intersection_glb` 继续只表示所有站点共同可见的绿色交会体，不把单站红色体积合并为共同交会红色。

### 9.5 协同三维模式

如果需要各站探测域、设备平台和协同交会 GLB，创建任务时使用：

```json
{
  "presentation_mode": "cooperative_3d"
}
```

此模式只允许 2 到 5 个站点。超过 5 个站点时应改用 `aggregate`。

任务完成后先查询产物清单：

```bash
curl -sS \
  "$API_BASE/api/radar/tasks/multi_task_20260821_103000_7ef10a22/outputs"
```

再根据 `kind` 下载：

```bash
curl -fL \
  "$API_BASE/api/radar/tasks/multi_task_20260821_103000_7ef10a22/outputs/fusion_scene_glb" \
  -o fusion_scene.glb

curl -fL \
  "$API_BASE/api/radar/tasks/multi_task_20260821_103000_7ef10a22/outputs/cooperative_intersection_glb" \
  -o cooperative_intersection.glb
```

如果没有实际重叠区域或资产没有生成，不能假定上述可选 GLB 一定存在，应检查 `exists` 和 `download_path`。

### 9.6 多雷达目标评估

单个目标接口相同：

```bash
curl -sS -X POST \
  "$API_BASE/api/radar/tasks/multi_task_20260821_103000_7ef10a22/evaluate-target" \
  -H "Content-Type: application/json" \
  -d '{
    "x": 102.1800,
    "y": 29.6300,
    "z": 3250,
    "target_type": "aircraft"
  }'
```

多雷达响应重点看：

```json
{
  "task_id": "multi_task_20260821_103000_7ef10a22",
  "task_type": "multi",
  "detected": true,
  "detail": null,
  "contributors": [
    {"radar_id": "R1", "detected": true},
    {"radar_id": "R2", "detected": false}
  ]
}
```

当前多雷达目标评估使用各站的可见性栅格判定，`contributors` 表示各站是否贡献了可见性。它与单雷达详细三维评估不同，当前多雷达贡献判断不按目标高度重新执行单站 DEM 高度换算。

批量目标调用方式与单雷达相同：

```text
POST /api/radar/tasks/{multi_task_id}/evaluate-targets
```

批量请求允许 1–500 个目标，`target_id` 必须唯一。任务状态为 `finished` 或 `partial` 后才可以评估。

### 9.7 获取某个站点的详细单雷达任务

多雷达聚合结果中，如果需要对某一个站点进一步生成完整的单雷达产物，可以调用：

```http
POST /api/radar/tasks/{multi_task_id}/radars/{radar_id}/detail
```

```bash
curl -sS -X POST \
  "$API_BASE/api/radar/tasks/multi_task_20260821_103000_7ef10a22/radars/R1/detail"
```

该接口会新建一个单雷达任务，返回新的 `task_id`，不会修改原多雷达任务。新任务完成后，按照单雷达流程查询指标、剖面、目标评估和下载 `scene_glb`、`radar_platform_glb` 等产物。

---

## 10. 雷达任务列表、融合和通用管理

### 10.1 查询任务列表

全部任务：

```bash
curl -sS "$API_BASE/api/radar/tasks"
```

只查单雷达：

```bash
curl -sS "$API_BASE/api/radar/tasks?task_type=single"
```

只查多雷达：

```bash
curl -sS "$API_BASE/api/radar/tasks?task_type=multi"
```

### 10.2 融合多个已完成的单雷达任务

如果业务上创建的是多个独立单雷达任务，也可以在它们都完成后计算融合分析：

```http
POST /api/radar/fusion
Content-Type: application/json
```

```bash
curl -sS -X POST "$API_BASE/api/radar/fusion" \
  -H "Content-Type: application/json" \
  -d '{
    "task_ids": [
      "task_20260821_102000_8cd1ef20",
      "task_20260821_102100_4ab7de91"
    ]
  }'
```

要求：

- 至少两个唯一任务；
- 最多 12 个任务；
- 所有任务必须是已完成的单雷达任务；
- 覆盖契约版本必须兼容。

返回联合可见区、重叠区、盲区和面积指标。融合接口直接返回 JSON，不生成新的任务 ID。

---

## 11. 推荐的业务系统实现顺序

### 11.1 第一次接入

建议按以下顺序开发：

1. 封装 `GET /api/health`，服务不可用时不要继续上传或创建任务；
2. 封装 DEM 选择逻辑：全国导入、批次上传、单文件上传分别保存 `dem_id`；
3. 封装 `GET /api/dem/{dem_id}`，创建雷达前校验 DEM 元数据；
4. 封装统一的 `POST /api/radar/tasks`，由 `task_type` 选择单雷达或多雷达请求体；
5. 保存每个任务的 `task_id` 和提交参数；
6. 轮询 `GET /api/radar/tasks/{task_id}`，直到进入终态；
7. 对 `finished` 或 `partial` 任务读取产物清单；
8. 根据产物 `kind` 下载文件并归档；
9. 需要点查询时再调用单目标或批量目标评估；
10. 删除任务和 DEM 前先确认文件已经归档，且没有其他任务引用 DEM。

### 11.2 推荐保存的业务记录

至少保存：

```text
dem_id
dem metadata snapshot
task_id
task_type
原始请求 JSON
任务创建时间和完成时间
任务终态
metrics
warnings / message
output_manifest.json
下载文件的本地路径和 SHA-256
```

这样可以在同一个 DEM、同一套雷达参数和同一版本下追溯结果，也能区分“数据问题”“任务参数问题”和“服务运行问题”。

---

## 12. 常见错误和处理方式

### 12.1 DEM 相关错误

| 错误码或现象 | 原因 | 处理 |
| --- | --- | --- |
| `DEM_NOT_FOUND` | `dem_id` 不存在或文件已被删除 | 先查询 `/api/dem`，使用正确 ID |
| `DEM_WITHOUT_CRS` | TIFF 没有 CRS | 先给源数据写入正确 CRS |
| `INVALID_DEM` | 非 GeoTIFF、波段或尺寸不合法 | 检查源文件和波段 |
| `DEM_ALREADY_EXISTS` | 目标 ID 已存在 | 使用新 ID 或确认无引用后删除旧 ID |
| `DEM_TILE_CRS_MISMATCH` | 批次瓦片 CRS 不一致 | 统一 CRS 后重新建批次 |
| `DEM_TILE_BAND_MISMATCH` | 批次瓦片不是单波段 | 处理为单波段高程 TIFF |
| `DEM_TILE_GRID_MISMATCH` | 分辨率、NoData 或像元网格不一致 | 先对齐瓦片 |
| `DEM_COG_MERGE_FAILED` | COG 或拼接失败 | 检查 GDAL、磁盘空间和 TIFF 完整性 |
| `UPLOAD_INCOMPLETE` | 分块上传缺少块 | 补齐所有 chunk 后再 complete |
| `DEM_IN_USE` | DEM 被任务引用 | 删除任务或保留 DEM，不要强删 |

### 12.2 雷达创建错误

| 错误码或现象 | 原因 | 处理 |
| --- | --- | --- |
| `422` | 请求字段、范围或枚举不符合 Schema | 根据响应字段逐项修正 |
| `RADAR_OUTSIDE_DEM` | 雷达点不在 DEM 范围 | 检查经纬度顺序和 DEM bounds |
| `RADAR_ON_DEM_NODATA` | 雷达点位于 NoData | 更换站点或修复 DEM |
| `RANGE_OUTSIDE_DEM` | 探测范围大部分在 DEM 外 | 缩小 `max_range_m` 或提供更大范围 DEM |
| `INVALID_TASK_ID` | URL 中任务 ID 格式不支持 | 使用接口返回的完整 task ID |
| `TASK_VARIANT_UNSUPPORTED` | 调用了不适合该任务类型的端点 | 单雷达才调用 metrics/profile，多雷达查询 stations |
| `TASK_METRICS_NOT_READY` | 任务尚未完成 | 继续轮询 |
| `TASK_NOT_FINISHED` | 目标评估或剖面时任务未完成 | 等待 `finished` 或多雷达 `partial` |
| `MULTI_RADAR_NOT_FOUND` | 站点 ID 不存在 | 先查询 `/radars` 获取准确 ID |
| `TASK_NOT_ACTIVE` | 取消时任务已经不在当前队列 | 重新查询任务状态 |

### 12.3 结果为空或三维模型看不到

按以下顺序排查：

1. 查询任务详情，确认状态为 `finished` 或 `partial`；
2. 查询 `/outputs`，确认目标 `kind` 的 `exists` 为 `true`；
3. 检查下载响应的 HTTP 状态码和文件大小；
4. 检查 `output_manifest_json` 和 `model_metadata_json`；
5. 检查雷达位置、最大距离、扫描扇区和 DEM 范围是否匹配；
6. 目标评估时确认单目标接口的 `z` 是海拔高度，而不是离地高度；
7. 多雷达协同三维模式确认站点数为 2–5，且确实存在空间重叠；
8. 如果是前端三维显示，确认加载的是 `scene_glb` 或 `fusion_scene_glb`，而不是把 GeoJSON 当作 GLB 加载。

### 12.4 “雷达高度场没有有效表面单元”类错误

如果出现类似：

```text
radar height-field envelope contains no valid surface cells
```

优先判断为任务窗口内 DEM 有效地形不足，而不是先认为雷达公式错误。常见原因：

- 雷达点落在 NoData；
- DEM 的 CRS 或坐标轴顺序不正确，导致窗口读到了错误位置；
- 雷达位置接近 DEM 边界，实际计算窗口大部分在 DEM 外；
- DEM 高程值为 NaN、无穷值或错误 NoData；
- 雷达高度、仰角范围和 DEM 局部高程组合后没有可用的表面单元；
- 多块瓦片拼接后存在未覆盖的缝隙。

建议按顺序检查：

1. `GET /api/dem/{dem_id}` 的 `crs` 和 `bounds`；
2. 雷达 `lon`、`lat` 是否确实落在 bounds 内；
3. 雷达点是否处于有效像元而不是 NoData；
4. 降低 `max_range_m`，先验证小窗口是否能计算；
5. 检查批次瓦片是否有缝隙、错位或错误 CRS；
6. 下载或渲染附近 DEM 瓦片确认位置是否正确；
7. 再检查高级仰角和体素参数。

---

## 13. 一套最短可执行流程

### 13.1 已有全国 DEM

```bash
# 1. 将 national.tif 放到 data/import/
# 2. 导入
docker compose exec -T backend python /app/scripts/import_dem.py \
  --source /workspace/import/national.tif \
  --dem-id national-dem

# 3. 确认 DEM
curl -sS "$API_BASE/api/dem/national-dem"

# 4. 创建单雷达
curl -sS -X POST "$API_BASE/api/radar/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "single",
    "dem_id": "national-dem",
    "radar": {"lon": 102.1, "lat": 29.6, "height_m": 15},
    "target": {"height_m": 0},
    "coverage": {"max_range_m": 50000, "scan_mode": "omni"}
  }'

# 5. 使用返回的 task_id 轮询
curl -sS "$API_BASE/api/radar/tasks/<task_id>"

# 6. 任务完成后下载可见区
curl -fL "$API_BASE/api/radar/tasks/<task_id>/outputs/visible_geojson" \
  -o visible.geojson
```

### 13.2 已有多块裁剪 TIFF

```bash
# 1. 创建批次，保存 batch_id 和 dem_id
curl -sS -X POST "$API_BASE/api/dem/batches" \
  -H "Content-Type: application/json" \
  -d '{"dem_id":"region-west-2026","label":"西部区域"}'

# 2. 上传所有瓦片
curl -sS -X POST "$API_BASE/api/dem/batches/<batch_id>/tiles" \
  -F "files=@tile_01.tif" \
  -F "files=@tile_02.tif"

# 3. 触发合并
curl -sS -X POST "$API_BASE/api/dem/batches/<batch_id>/complete"

# 4. 轮询到 ready
curl -sS "$API_BASE/api/dem/batches/<batch_id>"

# 5. 使用同一个 dem_id 创建雷达任务
curl -sS -X POST "$API_BASE/api/radar/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "task_type":"multi",
    "dem_id":"region-west-2026",
    "presentation_mode":"aggregate",
    "radars":[
      {"radar_id":"R1","radar":{"lon":102.1,"lat":29.6,"height_m":15},"coverage":{"max_range_m":50000}},
      {"radar_id":"R2","radar":{"lon":102.25,"lat":29.66,"height_m":20},"coverage":{"max_range_m":50000}}
    ]
  }'
```

最后，客户端只需要围绕两个稳定 ID 管理业务状态：

```text
dem_id  → 哪一份地形数据
task_id → 哪一次雷达计算
```
