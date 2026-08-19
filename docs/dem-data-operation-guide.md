# DEM 数据操作手册

本文档面向只调用 PyGeoModel 后端服务的使用方，说明两种 DEM 数据接入方式：

1. 全国范围的单个超大 TIFF：通过服务器本地路径导入，系统转换为 COG；
2. 多块已经切好的 TIFF：通过批次接口逐文件上传，系统合并为一个逻辑 DEM。

两种方式完成后，模型都只使用一个 `dem_id`。雷达、炮兵、无人机、岗哨、侦察车辆、机动性和空中走廊接口不需要知道底层是一个文件还是多个文件。

## 一、选择哪种方式

| 数据情况 | 推荐方式 | 说明 |
| --- | --- | --- |
| 全国级、20–200GB、文件已经在服务器磁盘上 | 本地导入 | 不经过浏览器或 HTTP 上传，适合超大 TIFF |
| 几块已经切好的区域 TIFF，由用户通过 API 提交 | 批次上传 | 多个文件归属同一个 `batch_id`，最终生成一个 `dem_id` |
| 单个普通小 TIFF | 现有单文件上传接口 | `POST /api/dem/upload`，原流程保持兼容 |

全国级 TIFF 不建议通过浏览器上传。多块批次接口当前每个文件使用一次完整的 multipart 请求；如果单块文件也非常大，应优先把文件放到服务器后使用本地导入，或后续接入批次专用的断点续传流程。

## 二、全国单个 TIFF：服务器本地导入

### 2.1 准备目录

在部署主机上，把全国原始 TIFF 放到项目的导入目录：

```text
项目目录/
└── data/
    └── import/
        └── national.tif
```

Docker Compose 会将该目录只读挂载到后端容器：

```text
宿主机 data/import/national.tif
    ↓ 只读挂载
容器 /workspace/import/national.tif
```

### 2.2 执行导入

在包含 `docker-compose.yml` 的项目目录执行：

```bash
docker compose exec -T backend \
  python /app/scripts/import_dem.py \
  --source /workspace/import/national.tif \
  --dem-id national-dem
```

Windows PowerShell 可以使用同一条命令；如果命令行不支持反斜杠换行，写成一行：

```powershell
docker compose exec -T backend python /app/scripts/import_dem.py --source /workspace/import/national.tif --dem-id national-dem
```

`--dem-id` 是后续所有模型请求使用的稳定标识，只允许字母、数字、下划线和连字符。例如：

```text
national-dem
qinghai-2026
region_001
```

### 2.3 导入时系统执行的检查

系统会拒绝以下输入：

- 文件不存在；
- 不是可读取的 GeoTIFF；
- 没有 CRS；
- 不是单波段；
- 数据类型不是数值类型；
- 宽、高无效；
- 地理范围不是有限的正面积范围。

检查通过后，系统会：

1. 在临时目录生成 COG；
2. 使用内部 `256×256` 瓦片、DEFLATE 压缩和 BILINEAR 金字塔；
3. 校验瓦片化和 overviews；
4. 原子重命名为 `dem.cog.tif`；
5. 最后写入 `metadata.json`。

失败时不会发布半成品 DEM。全国原始 TIFF 不会复制到应用数据目录，避免产生第二份全国数据。

### 2.4 导入后的文件位置

成功后，应用数据目录中主要保留：

```text
data/dem/national-dem/
├── dem.cog.tif
└── metadata.json
```

`metadata.json` 中的关键字段类似：

```json
{
  "dem_id": "national-dem",
  "filename": "national.tif",
  "cog_path": "dem.cog.tif"
}
```

其中 `filename` 保留原始文件名用于显示和兼容，`cog_path` 才是计算和渲染使用的文件。

### 2.5 检查导入结果

```bash
curl http://127.0.0.1:8000/api/dem/national-dem
```

确认返回：

- HTTP 状态码为 `200`；
- `dem_id` 为 `national-dem`；
- `cog_path` 为 `dem.cog.tif`；
- `bounds`、`resolution`、`width`、`height` 等元数据正常。

之后模型请求只需要传：

```json
{
  "dem_id": "national-dem"
}
```

模型不会全量加载全国 TIFF，而是根据任务范围从 COG 窗口读取，再投影到局部 UTM 网格计算。

## 三、多块 TIFF：批次上传并合并

### 3.1 处理流程

多块 TIFF 的调用顺序如下：

```text
创建批次
  ↓
使用同一个 batch_id 上传一个或多个 TIFF
  ↓
完成批次
  ↓
后台校验并合并为 dem.cog.tif
  ↓
轮询批次直到 ready
  ↓
使用返回的 dem_id 调用模型
```
### 3.2 创建批次

接口：

```text
POST /api/dem/batches
Content-Type: application/json
```

请求示例：

```json
{
  "dem_id": "region-001",
  "label": "西部测试区域"
}
```

`dem_id` 可以省略。省略时后端自动生成一个唯一 ID；如果调用方需要在后续请求中稳定引用，建议主动传入。

PowerShell 示例：

```powershell
$base = "http://127.0.0.1:8000"
$batch = curl.exe -s -X POST "$base/api/dem/batches" `
  -H "Content-Type: application/json" `
  --data '{"dem_id":"region-001","label":"西部测试区域"}' | ConvertFrom-Json

$batchId = $batch.batch_id
$demId = $batch.dem_id
```

创建成功返回 `201`，主要字段如下：

```json
{
  "batch_id": "batch_20260819_150000_ab12cd34",
  "dem_id": "region-001",
  "label": "西部测试区域",
  "status": "uploading",
  "filenames": [],
  "file_count": 0
}
```

必须保存返回的 `batch_id`。后续上传和完成操作都使用它。

### 3.3 逐个上传 TIFF

接口：

```text
POST /api/dem/batches/{batch_id}/tiles
Content-Type: multipart/form-data
字段名：files
```

可以一次上传多个文件：

```powershell
curl.exe -s -X POST "$base/api/dem/batches/$batchId/tiles" `
  -F "files=@D:\dem\tile_01.tif" `
  -F "files=@D:\dem\tile_02.tif"
```

也可以分别调用多次，每次上传一个文件：

```powershell
curl.exe -s -X POST "$base/api/dem/batches/$batchId/tiles" `
  -F "files=@D:\dem\tile_01.tif"

curl.exe -s -X POST "$base/api/dem/batches/$batchId/tiles" `
  -F "files=@D:\dem\tile_02.tif"

curl.exe -s -X POST "$base/api/dem/batches/$batchId/tiles" `
  -F "files=@D:\dem\tile_03.tif"
```

每次成功返回后，检查 `file_count` 是否递增：

```json
{
  "batch_id": "batch_20260819_150000_ab12cd34",
  "filenames": ["tile_01.tif", "tile_02.tif"],
  "file_count": 2
}
```

同一个批次内不能重复上传同名文件。文件名只取 basename，调用方应保证每块文件名称唯一且有明确含义。

### 3.4 完成批次

所有文件上传完成后调用：

```text
POST /api/dem/batches/{batch_id}/complete
```

示例：

```powershell
curl.exe -s -X POST "$base/api/dem/batches/$batchId/complete"
```

正常返回 `202`。批次可能进入 `merging`，也可能在很快完成后返回 `ready`。

### 3.5 轮询批次状态

接口：

```text
GET /api/dem/batches/{batch_id}
```

建议每 1–3 秒轮询一次，直到状态变为 `ready` 或 `failed`：

```powershell
do {
  Start-Sleep -Seconds 2
  $status = curl.exe -s "$base/api/dem/batches/$batchId" | ConvertFrom-Json
  Write-Host "status=$($status.status), files=$($status.file_count)"
} while ($status.status -notin @("ready", "failed"))

if ($status.status -eq "failed") {
  throw $status.error
}
```

成功状态示例：

```json
{
  "batch_id": "batch_20260819_150000_ab12cd34",
  "dem_id": "region-001",
  "status": "ready",
  "filenames": ["tile_01.tif", "tile_02.tif"],
  "file_count": 2,
  "error": null
}
```

失败状态需要查看 `error` 字段。失败批次不会生成可供模型使用的 ready DEM。

### 3.6 合并后的使用方式

批次变为 `ready` 后，使用返回的 `dem_id` 调用现有模型接口。例如雷达统一任务接口：

```text
POST /api/radar/tasks
```

请求中的 DEM 部分只需要：

```json
{
  "task_type": "single",
  "dem_id": "region-001"
}
```

多雷达、炮兵等其他模型也使用同一个 `dem_id`，不需要分别传入 `tile_01.tif`、`tile_02.tif`。

合并后的数据目录类似：

```text
data/dem/region-001/
├── dem.cog.tif
└── metadata.json
```

元数据会额外记录：

```json
{
  "source_type": "tiled_upload_batch",
  "source_tile_count": 2,
  "source_filenames": ["tile_01.tif", "tile_02.tif"],
  "cog_path": "dem.cog.tif"
}
```

## 四、多块 TIFF 的格式要求

同一个批次中的所有 TIFF 必须满足：

- 都是可读取的 GeoTIFF；
- 都有 CRS，且 CRS 完全一致；
- 都是单波段；
- 分辨率一致；
- 数据类型一致；
- NoData 定义一致；
- 像元网格对齐，不能出现半个像元的错位；
- 地理范围有效。

瓦片可以相邻，也可以有轻微重叠，但不建议使用存在明显高程冲突的重叠区域。需要重新投影、重采样或分辨率不同的瓦片，应先在数据处理环节统一后再上传。

常见错误及处理方式：

| 错误情况 | 处理建议 |
| --- | --- |
| `DEM_TILE_CRS_MISMATCH` | 将所有瓦片转换到同一个 CRS |
| `DEM_TILE_GRID_MISMATCH` | 统一分辨率、数据类型、NoData 和像元网格 |
| `DEM_TILE_BAND_MISMATCH` | 将输入处理为单波段高程数据 |
| 重复文件名 | 修改文件名后重新上传 |
| `DEM_COG_MERGE_FAILED` | 检查文件完整性、磁盘空间和容器 GDAL |

## 五、接口状态和重试建议

### 批次状态

```text
uploading → validating/merging → ready
                         └──────→ failed
```

调用方应遵守：

1. 只有 `uploading` 状态可以继续上传文件；
2. 只有确认所有文件上传完成后才调用 `/complete`；
3. `merging` 期间不要重复调用 `/complete`；
4. `ready` 后直接使用 `dem_id`，不要重复上传；
5. `failed` 时读取 `error`，修正数据后创建新批次重试。

### 资源和磁盘注意事项

- 全国导入会生成一份 COG，原始 TIFF 不会复制到 `data/dem`；
- 多块上传在合并完成前会暂存各个 TIFF，需保证 `data` 所在磁盘有足够空间；
- 合并完成后，暂存瓦片会被清理，只保留 COG 和元数据；
- 任务计算仍然使用任务范围窗口，不会因为全国 DEM 或大范围 COG 而全量读入内存；
- 后端镜像必须包含 `gdal-bin`，雷达等 viewshed 模型需要 `gdal_viewshed`；
- 本机直接运行 Python 虚拟环境时，如果没有 GDAL 命令行程序，DEM 合并的小数据回退可能可用，但雷达任务会因 `gdal_viewshed` 缺失失败。生产环境建议使用包含 GDAL 的后端 Docker 镜像。

## 六、完整调用顺序速查

### 全国单 TIFF

```text
把 national.tif 放入 data/import/
        ↓
docker compose exec backend python /app/scripts/import_dem.py ...
        ↓
GET /api/dem/national-dem
        ↓
使用 dem_id=national-dem 调用模型
```

### 多块 TIFF

```text
POST /api/dem/batches
        ↓
POST /api/dem/batches/{batch_id}/tiles    （可调用多次）
        ↓
POST /api/dem/batches/{batch_id}/complete
        ↓
GET /api/dem/batches/{batch_id}          （轮询 ready）
        ↓
使用返回的 dem_id 调用模型
```
