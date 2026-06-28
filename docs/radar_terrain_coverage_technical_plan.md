# 基于 DEM 的雷达地形遮挡探测范围计算与三维可视化技术方案

## 1. 文档目标

本文档面向第一版 MVP 开发，目标是把“基于 DEM 的雷达地形遮挡探测范围计算与 MapLibre 三维可视化系统”从概念方案细化为可实施的技术方案。

第一版不追求完整雷达方程、电磁传播仿真或概率探测模型，而是优先完成一个可运行、可演示、可扩展的工具：

```text
可探测区 = 最大探测半径范围 ∩ 雷达扫描范围 ∩ DEM 地形通视范围
```

## 2. 技术可行性结论

### 2.1 总体结论

第一版 MVP 技术可行，建议采用“FastAPI + GDAL/Rasterio + pyproj + Shapely/GeoPandas + MapLibre GL JS”的工程组合。

核心原因：

1. DEM 可视域计算已有成熟工具链。GDAL 提供 `gdal_viewshed`，可直接基于 DEM、观察点高度、目标高度、最大距离和曲率修正生成 viewshed 栅格。
2. 坐标转换和投影处理可由 PROJ/pyproj、GDAL、Rasterio 完成，适合把 WGS84 输入转换到 UTM 等米制投影坐标系下计算。
3. MapLibre GL JS 支持 `raster-dem` 和 terrain，可满足三维地形展示；GeoJSON 面图层可直接展示可探测区、遮挡区和理论覆盖范围。
4. 第一版计算链路是离线批处理性质，不需要实时毫秒级响应，FastAPI 任务式接口足够支撑演示和早期试用。

### 2.2 可行性分项判断

| 分项 | 结论 | 说明 |
| --- | --- | --- |
| DEM 上传与元数据读取 | 可行 | Rasterio/GDAL 可读取 CRS、bounds、resolution、nodata、transform 等信息。 |
| 经纬度到投影坐标转换 | 可行 | pyproj 可根据雷达经纬度自动选择 UTM 分区，并完成 EPSG:4326 到 UTM 的转换。 |
| 地形通视计算 | 可行 | `gdal_viewshed` 可直接生成通视栅格，适合第一版。 |
| 曲率/折射近似 | 可行但需解释边界 | `gdal_viewshed -cc` 可引入曲率系数；第一版只作为工程近似，不声明为高精度雷达传播模型。 |
| 扫描圆/扇区裁剪 | 可行 | Shapely 可生成圆/扇区，并与 viewshed 矢量化结果求交。 |
| 栅格转 GeoJSON | 可行但需控制数据量 | Rasterio features 或 GDAL polygonize 可做矢量化；大 DEM 需裁剪、简化、限制输出。 |
| MapLibre 三维展示 | 可行 | 第一版建议使用现成 terrain DEM 瓦片做三维底图，用户上传 DEM 先只参与计算。 |
| 用户 DEM 生成地形瓦片 | 可行但不建议进 MVP | 需要 Terrain-RGB/Terrarium 编码、切片、瓦片服务和 NoData 处理，建议放到增强版。 |
| Docker 化部署 | 可行但要重点处理 GDAL | GDAL Python 依赖和命令行工具版本要在 Docker 镜像中固定。 |

### 2.3 关键技术依据

本方案参考的关键官方文档：

- GDAL `gdal_viewshed`：https://gdal.org/en/stable/programs/gdal_viewshed.html
- GRASS `r.viewshed`：https://grass.osgeo.org/grass-stable/manuals/r.viewshed.html
- MapLibre 3D Terrain 示例：https://maplibre.org/maplibre-gl-js/docs/examples/3d-terrain/
- MapLibre Custom Layer 示例：https://maplibre.org/maplibre-gl-js/docs/examples/add-a-3d-model/
- FastAPI 文件上传：https://fastapi.tiangolo.com/tutorial/request-files/
- FastAPI Background Tasks：https://fastapi.tiangolo.com/tutorial/background-tasks/
- Rasterio features：https://rasterio.readthedocs.io/en/stable/topics/features.html

## 3. MVP 范围定义

### 3.1 第一版必须完成

1. 上传单个 GeoTIFF/COG DEM。
2. 读取并展示 DEM 元数据。
3. 输入雷达经纬度、雷达架设高度、目标高度、最大探测半径。
4. 支持全向和扇区两种扫描模式。
5. 自动选择适合的 UTM 投影，并将 DEM 和雷达点转换到投影坐标系。
6. 调用 `gdal_viewshed` 生成通视栅格。
7. 生成理论覆盖范围、可探测区、遮挡区。
8. 输出 GeoTIFF 和 GeoJSON 结果。
9. 在 MapLibre 三维地图中展示雷达点、理论覆盖范围、可探测区、遮挡区。
10. 输出理论覆盖面积、实际可探测面积、遮挡面积、遮挡比例。

### 3.2 第一版明确不做

1. 完整雷达方程。
2. RCS、频率、功率、天线增益、接收灵敏度参与计算。
3. 多雷达融合。
4. 动态目标轨迹。
5. 概率探测、虚警概率、检测概率模型。
6. 气象衰减、雨衰、大气层结传播。
7. 建筑物、植被、DSM 遮挡建模。
8. 用户上传 DEM 自动生产三维 terrain 瓦片。
9. PostGIS、MVT、PMTiles、3D Tiles 生产级发布链路。

## 4. 推荐技术架构

```text
frontend/
  MapLibre GL JS
  参数面板
  任务状态轮询
  GeoJSON 结果图层
  三维地形显示

backend/
  FastAPI
  DEM 上传与管理
  坐标转换
  DEM 裁剪/重投影
  gdal_viewshed 调用
  栅格矢量化
  面积统计
  文件输出服务

storage/
  data/dem/
  data/tasks/
  data/outputs/
```

### 4.1 后端技术栈

| 模块 | 技术 |
| --- | --- |
| Web API | FastAPI |
| 数据模型 | Pydantic |
| DEM 读取 | Rasterio / GDAL |
| DEM 重投影 | GDAL Warp / Rasterio warp |
| 坐标转换 | pyproj / PROJ |
| 可视域计算 | `gdal_viewshed` |
| 几何处理 | Shapely |
| 可选矢量处理 | GeoPandas / Fiona |
| 任务执行 | FastAPI BackgroundTasks；后续替换 Celery/RQ |
| 文件存储 | 本地文件系统；后续替换 MinIO |
| 部署 | Docker Compose |

### 4.2 前端技术栈

| 模块 | 技术 |
| --- | --- |
| 构建工具 | Vite |
| UI 框架 | Vue + Element Plus 或 React + Ant Design |
| 地图引擎 | MapLibre GL JS |
| 三维地形 | MapLibre `raster-dem + terrain` |
| 结果展示 | GeoJSON fill/line/circle layer |
| 波束可视化 | 第一版可用 GeoJSON 扇区；增强版再接 Three.js Custom Layer |

建议第一版使用 Vue + Element Plus，表单开发快，适合工具型原型。如果团队已有 React 技术栈，也可以直接选择 React + Ant Design。

## 5. 核心计算流程

### 5.1 总流程

```text
1. 用户上传 DEM
2. 后端读取 DEM 元数据
3. 用户提交雷达覆盖计算参数
4. 校验雷达点是否落在 DEM 范围内
5. 根据雷达经纬度自动选择 UTM EPSG
6. 裁剪 DEM 到最大探测半径外接范围
7. 将裁剪 DEM 重投影到 UTM
8. 将雷达经纬度转换为 UTM x/y
9. 调用 gdal_viewshed
10. 根据全向/扇区参数生成理论扫描范围
11. 将 viewshed 栅格转为可视区/遮挡区矢量
12. 与理论扫描范围求交
13. 统计面积
14. 输出 GeoTIFF/GeoJSON
15. 前端加载结果并展示
```

### 5.2 自动 UTM 投影选择

UTM zone 计算：

```text
zone = floor((lon + 180) / 6) + 1
```

EPSG 选择：

```text
lat >= 0: EPSG = 32600 + zone
lat <  0: EPSG = 32700 + zone
```

第一版适用边界：

1. 最大探测半径建议不超过 100 km。
2. 雷达点不要靠近 UTM 分区边界太近。
3. 不覆盖极区。
4. 若后续支持更大范围，应改用本地等距投影或以雷达点为中心的方位等距投影。

### 5.3 `gdal_viewshed` 调用

示例命令：

```bash
gdal_viewshed \
  -ox <radar_x> \
  -oy <radar_y> \
  -oz <radar_height_m> \
  -tz <target_height_m> \
  -md <max_range_m> \
  -cc <curvature_coeff> \
  -om NORMAL \
  <dem_projected.tif> \
  <viewshed.tif>
```

参数说明：

| 参数 | 含义 |
| --- | --- |
| `-ox` / `-oy` | 观察点在投影坐标系下的 x/y。 |
| `-oz` | 雷达相对 DEM 表面的架设高度。 |
| `-tz` | 目标相对 DEM 表面的高度。 |
| `-md` | 最大计算距离，单位跟投影坐标一致，UTM 下为米。 |
| `-cc` | 曲率/折射修正系数。 |
| `-om NORMAL` | 输出普通可视/不可视栅格。 |

第一版输出解释：

```text
255 = 通视
0   = 不通视或超出有效通视范围
```

### 5.4 全向和扇区裁剪

全向模式：

```text
理论扫描范围 = 以雷达点为圆心、max_range_m 为半径的圆
实际可探测区 = viewshed_visible ∩ 理论扫描范围
遮挡区 = 理论扫描范围 - 实际可探测区
```

扇区模式：

```text
理论扫描范围 = 以雷达点为圆心、azimuth_deg 为中心方向、beam_width_deg 为角宽、max_range_m 为半径的扇区
实际可探测区 = viewshed_visible ∩ 理论扫描范围
遮挡区 = 理论扫描范围 - 实际可探测区
```

方位角约定建议：

```text
0° = 正北
90° = 正东
180° = 正南
270° = 正西
顺时针增加
```

内部几何计算需要把该约定转换为平面坐标角度：

```text
math_angle_deg = 90 - azimuth_deg
```

## 6. 数据模型与 API 设计

### 6.1 DEM 上传

```http
POST /api/dem/upload
Content-Type: multipart/form-data
```

响应：

```json
{
  "dem_id": "dem_20260628_001",
  "filename": "sample_dem.tif",
  "crs": "EPSG:4326",
  "bounds": [104.5, 34.8, 105.8, 35.6],
  "resolution": [30.0, 30.0],
  "width": 4096,
  "height": 4096,
  "nodata": -32768
}
```

### 6.2 创建覆盖计算任务

```http
POST /api/radar/coverage
Content-Type: application/json
```

请求：

```json
{
  "dem_id": "dem_20260628_001",
  "radar": {
    "lon": 105.123456,
    "lat": 35.123456,
    "height_m": 10
  },
  "target": {
    "height_m": 0
  },
  "coverage": {
    "max_range_m": 50000,
    "scan_mode": "sector",
    "azimuth_deg": 90,
    "beam_width_deg": 120
  },
  "advanced": {
    "use_curvature": true,
    "curvature_coeff": 0.75,
    "output_simplify_tolerance_m": 30
  },
  "reserved_radar_params": {
    "frequency_hz": null,
    "transmit_power_w": null,
    "antenna_gain_db": null,
    "receiver_sensitivity_dbm": null,
    "target_rcs_m2": null,
    "pulse_width_s": null,
    "prf_hz": null,
    "noise_figure_db": null,
    "detection_probability": null,
    "false_alarm_probability": null
  }
}
```

响应：

```json
{
  "task_id": "task_20260628_001",
  "status": "running"
}
```

### 6.3 查询任务状态

```http
GET /api/radar/coverage/{task_id}
```

响应：

```json
{
  "task_id": "task_20260628_001",
  "status": "finished",
  "progress": 100,
  "message": "finished",
  "metrics": {
    "theoretical_area_m2": 1570796326.79,
    "visible_area_m2": 982000000.0,
    "blocked_area_m2": 588796326.79,
    "blocked_ratio": 0.375
  },
  "outputs": {
    "viewshed_tif": "/outputs/task_20260628_001/viewshed.tif",
    "visible_geojson": "/outputs/task_20260628_001/visible.geojson",
    "blocked_geojson": "/outputs/task_20260628_001/blocked.geojson",
    "range_geojson": "/outputs/task_20260628_001/radar_range.geojson"
  }
}
```

### 6.4 错误响应

```json
{
  "detail": {
    "code": "RADAR_OUTSIDE_DEM",
    "message": "Radar point is outside DEM bounds."
  }
}
```

建议错误码：

| 错误码 | 含义 |
| --- | --- |
| `INVALID_DEM` | DEM 文件无法读取或格式不支持。 |
| `DEM_WITHOUT_CRS` | DEM 缺少坐标系。 |
| `RADAR_OUTSIDE_DEM` | 雷达点不在 DEM 范围内。 |
| `RANGE_OUTSIDE_DEM` | 探测范围超出 DEM 覆盖范围过多。 |
| `GDAL_VIEWSHED_FAILED` | `gdal_viewshed` 执行失败。 |
| `VECTORIZE_FAILED` | 栅格矢量化失败。 |

## 7. 建议目录结构

```text
PyGeoModel/
  backend/
    app/
      main.py
      api/
        dem.py
        radar.py
      core/
        config.py
        errors.py
      schemas/
        dem.py
        radar.py
      services/
        dem_store.py
        projection.py
        viewshed.py
        geometry.py
        vectorize.py
        task_store.py
      workers/
        coverage_task.py
    requirements.txt
    Dockerfile
  frontend/
    src/
      api/
      components/
      map/
      pages/
      styles/
    package.json
  data/
    dem/
    tasks/
    outputs/
  docs/
    radar_terrain_coverage_technical_plan.md
  docker-compose.yml
```

## 8. 前端界面方案

### 8.1 主界面布局

```text
左侧：参数面板
右侧：MapLibre 三维地图
底部或右下角：结果统计与下载
```

### 8.2 参数面板

字段：

1. DEM 上传/选择。
2. 雷达经度。
3. 雷达纬度。
4. 雷达架设高度。
5. 目标高度。
6. 最大探测半径。
7. 扫描模式：全向/扇区。
8. 方位角。
9. 水平波束宽度。
10. 是否考虑曲率/折射。
11. 曲率系数。
12. 开始计算按钮。

### 8.3 地图图层

| 图层 | 类型 | 样式建议 |
| --- | --- | --- |
| 三维地形 | raster-dem terrain | 1.2-1.5 exaggeration，便于演示。 |
| 雷达点 | circle/symbol | 高对比色，带外圈。 |
| 理论覆盖范围 | line/fill | 蓝色边框，低透明填充。 |
| 可探测区 | fill | 绿色，透明度 0.35-0.5。 |
| 遮挡区 | fill | 红色或橙色，透明度 0.25-0.4。 |

第一版不强制 Three.js 波束体。若要演示效果，可先用扇区面 + 雷达点高度标注替代；增强版再接 MapLibre Custom Layer。

## 9. 性能与数据量控制

### 9.1 第一版建议约束

| 项目 | 建议限制 |
| --- | --- |
| 单个 DEM 文件 | 500 MB 以内 |
| 最大探测半径 | 默认 50 km，建议不超过 100 km |
| DEM 分辨率 | 10-90 m 均可，演示推荐 30 m |
| 输出 GeoJSON | 尽量控制在 20 MB 以内 |
| 单任务耗时 | 演示场景目标 10 秒到 2 分钟 |

### 9.2 优化策略

1. 先裁剪 DEM，再重投影和 viewshed。
2. 对输出多边形做 simplify，容差默认等于 DEM 分辨率。
3. 避免把完整 viewshed 栅格全部转成高精度多边形。
4. 对大结果保留 GeoTIFF 下载，前端展示可使用简化版 GeoJSON。
5. 后续生产版改为 COG + MVT/PMTiles，而不是直接加载超大 GeoJSON。

## 10. 主要风险与应对

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| GDAL 安装复杂 | 开发环境不一致，部署失败 | 使用 Docker 固定 GDAL/PROJ 版本。 |
| DEM 坐标系缺失或错误 | 计算结果偏移 | 上传后强校验 CRS，缺失 CRS 时拒绝计算。 |
| 经纬度 DEM 直接计算 viewshed | 距离单位错误，结果无意义 | 强制重投影到米制坐标系后再计算。 |
| 探测范围超出 DEM 范围 | 边界区域误判 | 任务提交时提示或拒绝，允许用户确认降级计算。 |
| GeoJSON 过大 | 前端卡顿 | 输出简化 GeoJSON，同时保留 GeoTIFF。 |
| 三维地形与计算 DEM 不一致 | 演示解释成本增加 | 第一版界面明确“地形底图用于展示，上传 DEM 用于计算”；增强版再做 DEM 地形瓦片闭环。 |
| 曲率/折射参数被误解 | 用户以为是完整雷达传播模型 | 文档和界面注明这是地球曲率/折射近似，不等于雷达方程。 |

## 11. 开发排期

### 第 1 周：基础框架与 DEM 管理

交付目标：

1. FastAPI 服务可启动。
2. 前端 MapLibre 页面可打开。
3. DEM 可上传并读取元数据。
4. 雷达点是否位于 DEM 范围内可校验。

主要任务：

```text
搭建后端工程
搭建前端工程
实现 /api/dem/upload
实现 DEM 元数据读取
实现 DEM 文件本地存储
实现基础地图页面
```

### 第 2 周：通视计算闭环

交付目标：

1. 能从 DEM + 雷达参数生成 `viewshed.tif`。
2. 能生成 `visible.geojson`、`blocked.geojson`、`radar_range.geojson`。

主要任务：

```text
实现 UTM 自动选择
实现 DEM 裁剪和重投影
封装 gdal_viewshed 调用
实现圆/扇区生成
实现栅格矢量化
实现面积统计
```

### 第 3 周：地图展示与任务接口

交付目标：

1. 前端可提交任务并轮询状态。
2. MapLibre 可加载计算结果。
3. 结果图层位置正确，不明显偏移。

主要任务：

```text
实现 /api/radar/coverage
实现 /api/radar/coverage/{task_id}
实现结果文件静态服务
实现 GeoJSON 图层加载
实现图例和透明度控制
```

### 第 4 周：演示打磨与部署

交付目标：

1. MVP 可完整演示。
2. Docker Compose 可一键启动。
3. 有样例 DEM 和样例参数。
4. 有验收说明和已知限制。

主要任务：

```text
完善错误提示
完善结果下载
整理 Dockerfile 和 docker-compose.yml
补充 README
准备演示数据
完成基础测试
```

## 12. 验收标准

### 12.1 功能验收

1. 可以上传 GeoTIFF DEM。
2. 可以读取 DEM 坐标系、范围、分辨率、NoData。
3. 可以输入雷达经纬度、雷达高度、目标高度和最大探测半径。
4. 可以选择全向和扇区模式。
5. 可以生成可探测区、遮挡区和理论覆盖范围。
6. 可以在 MapLibre 三维地图上叠加显示结果。
7. 可以查看面积统计和遮挡比例。
8. 可以下载 GeoJSON 和 GeoTIFF 结果。

### 12.2 技术验收

1. 后端可通过 Docker 启动。
2. 前端可通过 npm/Vite 启动。
3. `gdal_viewshed` 可在容器内正常执行。
4. 输出结果坐标能正确叠加到 MapLibre。
5. 雷达点、理论覆盖范围、可探测区位置无明显偏移。
6. 对 DEM 坐标系缺失、雷达点越界、GDAL 执行失败有明确错误响应。

### 12.3 效果验收

1. 山区 DEM 下可以看到由山体遮挡形成的盲区。
2. 平坦 DEM 下可探测区接近理论覆盖圆或扇区。
3. 扇区模式下结果能按方位角和波束宽度正确裁剪。
4. 调整目标高度后，可探测区变化方向符合预期。

## 13. 后续扩展路线

### 第二版：简化雷达方程

加入频率、发射功率、天线增益、接收灵敏度、目标 RCS 等参数，计算理想探测距离或距离衰减，再与地形通视结果叠加。

### 第三版：准三维探测体

加入俯仰角、垂直波束宽度、多个目标高度切片，形成低空目标探测体的近似表达。

### 第四版：多雷达融合

支持多个雷达站点，计算覆盖并集、重叠覆盖、冗余度和盲区。

### 第五版：生产级地理发布

引入 PostGIS、COG、MVT、PMTiles、MinIO 或对象存储，支持大范围、多任务、多用户访问。

## 14. 推荐实施决策

第一版建议采用以下实施决策：

1. 后端优先打通 `gdal_viewshed` 计算闭环。
2. DEM 三维展示先使用现成 MapLibre terrain 瓦片，用户 DEM 仅用于计算。
3. API 一开始按任务式设计，即使内部先用 FastAPI BackgroundTasks。
4. 输出同时保留 GeoTIFF 和简化 GeoJSON。
5. 所有计算都在米制投影坐标系下完成，结果再转回 EPSG:4326 给前端显示。
6. 雷达物理参数只作为保留字段，不参与第一版计算。

一句话概括：

> 第一版先做“地形遮挡意义下的雷达覆盖分析工具”，用成熟 GIS 工具链保证结果可解释、可演示、可扩展；不要在 MVP 阶段进入完整雷达物理仿真。
