# 多瓦片 DEM 逻辑数据集设计

## 状态

设计已确认，等待进入实施计划。

## 背景与目标

用户会一次上传多块已经切好的 GeoTIFF 瓦片，但计算时希望像使用一个 DEM 一样选择和使用。当前系统的模型入口已经统一使用 `dem_id`，计算文件通过 `find_dem_compute_file(dem_id)` 获取，适合在 DEM 数据层完成多瓦片合并，而不是让每个模型分别处理瓦片。

本设计的目标是：

- 一次多文件上传形成一个逻辑 DEM 数据集；
- 上传完成后生成一个独立的 `dem.cog.tif`；
- 雷达、炮兵、无人机、岗哨、侦察车辆、机动性和空中走廊等模型继续只接收一个 `dem_id`；
- 任务计算仍按范围从 COG 读取窗口，不把全国或完整拼接结果一次性读入内存；
- 保留现有单文件上传和历史 DEM 的兼容性。

## 约束与范围

同一上传批次内的瓦片必须具有：

- 相同 CRS；
- 相同像元宽高分辨率；
- 相同波段数，第一阶段要求单波段；
- 相同数据类型和 NoData 规则；
- 对齐到同一像元网格。

瓦片可以相邻，也可以存在少量空间重叠；不要求完全覆盖成无缝矩形。未覆盖区域保留为 NoData。第一阶段不支持不同 CRS 或不同分辨率瓦片的自动重投影和重采样，也不引入对象存储或运行时动态瓦片索引。

## 总体架构

```text
多文件选择
    ↓
DEM 上传批次 batch_id
    ↓ 逐文件分片上传
临时瓦片目录
    ↓ 校验
临时 VRT
    ↓ GDAL 流式转换
单个 dem.cog.tif
    ↓ 原子发布 metadata.json
ready 状态的 dem_id
    ↓
模型按任务范围读取 COG window
```

批次合并在后台执行。上传完成接口只负责改变批次状态并返回合并任务状态，不在 HTTP 请求中同步等待大型 COG 生成。

## 数据模型与存储

上传期间使用临时目录：

```text
data/uploads/{batch_id}/
  batch.json
  files/{upload_id}/tile-001.tif
  files/{upload_id}/tile-002.tif
```

合并成功后发布：

```text
data/dem/{dem_id}/
  dem.cog.tif
  metadata.json
```

`metadata.json` 保留兼容字段 `filename`，多瓦片数据使用批次第一个文件名或可读的批次名称作为展示值，同时增加：

- `source_type: tiled_upload_batch`；
- `source_tile_count`；
- `source_filenames`；
- `cog_path: dem.cog.tif`；
- 合并后的 CRS、范围、分辨率、宽高和 NoData 信息；
- `merge_method` 和发布时间；
- 可选的批次 ID。

最终模型和渲染接口只把 `dem.cog.tif` 作为计算数据源。上传成功后，临时瓦片可以清理；如果合并失败则保留批次临时文件用于重试，但不得发布最终 DEM 元数据。

## 接口与状态

新增批次接口：

```text
POST /api/dem/batches
POST /api/dem/batches/{batch_id}/files
POST /api/dem/batches/{batch_id}/complete
GET  /api/dem/batches/{batch_id}
```

批次状态：

```text
uploading → validating → merging → ready
                                      ↘ failed
```

每个文件继续复用现有分片上传和断点续传机制。批次状态接口返回每个文件的大小、已上传分片、错误信息、合并进度和最终 `dem_id`。

现有单文件接口不改变：单文件上传可视为只有一个文件的批次，并直接走同一套 COG 发布流程。

## 瓦片校验与重叠规则

批次完成后按以下顺序校验：

1. 文件存在且可被 Rasterio/GDAL 打开；
2. 是单波段 GeoTIFF；
3. CRS、分辨率、数据类型、NoData 和像元网格对齐一致；
4. 每块瓦片的范围和尺寸有效；
5. 至少存在一个有效高程像元；
6. 生成后的范围、瓦片化和 overviews 满足 COG 校验要求。

瓦片按规范化文件名排序后参与 VRT 构建，重叠区域使用固定的后者覆盖前者规则，保证同一批次重复合并结果稳定。合并过程中不依赖上传完成顺序。

## COG 合并流程

生产环境使用 GDAL 流式处理：

1. 根据已校验的瓦片生成临时 VRT；
2. 通过 `gdal_translate` 输出临时 COG；
3. 使用 256×256 内部块、DEFLATE 压缩和 BILINEAR overviews；
4. 对临时 COG 检查单波段、内部瓦片和 overviews；
5. 原子重命名为 `dem.cog.tif`；
6. 最后写入 `metadata.json`，再将批次标记为 `ready`。

合并过程不能使用把完整 DEM 拼接到 Python/Numpy 内存中的实现。开发环境如果没有 GDAL，多文件合并应返回明确的 `DEM_COG_MERGE_FAILED`，而不是使用可能导致内存失控的全量 fallback；现有单文件小数据的兼容 fallback 可以继续保留。

## 模型计算接入

所有模型继续执行现有数据流：

```text
dem_id
  ↓ find_dem_compute_file
dem.cog.tif
  ↓ 任务范围 window
局部 DEM
  ↓ 局部 UTM 投影
模型计算
```

不修改雷达、炮兵、无人机、岗哨等模型公式，也不修改基本请求结构。`find_dem_compute_file` 优先返回 COG；历史 DEM 没有 COG 时按现有兼容逻辑生成一次。DEM 列表只展示 `ready` 数据集，计算接口拒绝引用 `uploading`、`merging` 或 `failed` 批次。

## 前端交互

DEM 上传页面支持多选 TIF，并显示：

- 每个文件的上传进度；
- 批次总体进度；
- 校验中和合并中的状态；
- 完成后的统一 DEM 名称和 `dem_id`；
- CRS、分辨率或波段不一致等可操作错误。

只有批次为 `ready` 后才刷新 DEM 选择列表。合并失败时保留批次记录，允许重新触发合并或清理批次。普通单文件上传的用户体验保持不变。

## 错误处理与清理

稳定错误码包括：

- `DEM_TILE_CRS_MISMATCH`；
- `DEM_TILE_GRID_MISMATCH`；
- `DEM_TILE_BAND_MISMATCH`；
- `DEM_TILE_FORMAT_INVALID`；
- `DEM_COG_MERGE_FAILED`；
- `DEM_BATCH_NOT_READY`。

发布采用临时目录和原子重命名。任何校验或转换失败都不能留下可被模型发现的半成品 `metadata.json`。批次清理接口只允许删除没有被任务引用的批次或 DEM；已有 DEM 的引用保护规则继续有效。

## 测试与验收

后端测试覆盖：

- 多文件批次创建、分片上传和完成状态；
- 一致瓦片成功合并为一个 COG；
- CRS、网格、波段和格式不一致时拒绝；
- 重叠瓦片按固定顺序产生稳定结果；
- COG 的内部块和 overviews 正确；
- COG 生成失败时不发布元数据；
- ready DEM 可通过 `find_dem_compute_file` 被所有模型使用；
- 历史单文件 DEM 和现有上传接口继续工作；
- 任务只读取窗口，不全量加载合并后的 DEM。

前端测试覆盖：

- 多文件选择和逐文件进度；
- 批次合并状态轮询；
- ready 前不可选择 DEM；
- 校验错误和重试提示；
- 单文件上传兼容。

验收标准：

- 用户一次上传多块 TIF 后只得到一个可选 DEM；
- 所有模型请求仍只携带一个 `dem_id`；
- 合并过程的内存占用与 GDAL 流程和磁盘窗口相关，不随完整 DEM 像元数线性复制到 Python 内存；
- 合并失败不污染 DEM 列表；
- 现有单文件 DEM、COG 读取和任务计算结果不回归。

## 非目标

- 第一阶段不支持批次内混合 CRS 或自动重投影；
- 不在每个模型中实现多瓦片读取；
- 不增加永久的按行政区裁剪缓存；
- 不改变现有模型计算公式；
- 不引入对象存储或远程瓦片服务。
