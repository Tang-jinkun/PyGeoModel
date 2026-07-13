# DEM 边界裁剪理论波束设计

## 1. 背景

当前雷达覆盖流程存在两处不一致：

- 后端理论掩膜只应用扫描方位、有效距离和俯仰条件，没有与 DEM 有效数据掩膜相交。
- 前端 Three.js 理论波束只根据雷达位置和最大半径生成完整圆或扇区，没有接收 DEM 分析边界。

因此，DEM 边界外的区域可能进入理论范围、遮挡面积或三维实心波束。该区域没有地形数据，既不能判定为可见，也不能判定为遮挡。

## 2. 目标

1. 将 DEM 边界外区域统一定义为“未知/未分析区域”。
2. 二维理论范围、三维理论波束、可见区、遮挡区和面积指标使用同一分析域。
3. DEM 的有效范围依据有效像元，而不只依据栅格外接矩形。
4. 默认不渲染未知区域的实心波束，同时保留可选的完整请求边界作为参考。
5. 保持现有任务 API 和输出字段可用，并为完整请求面积和未知面积增加明确字段。

## 3. 非目标

- 不对 DEM 外地形进行补零、插值或外推。
- 不把 DEM 外区域推断为地形遮挡。
- 不改变雷达方程、GDAL viewshed 或俯仰角模型本身。
- 不在本次改动中引入新的地形数据源自动补全 DEM。

## 4. 领域语义

定义：

```text
B = 应用扫描模式、有效距离、俯仰角和雷达方程后的完整理论波束
D = 从雷达点沿径向连续有效的 DEM 分析域
T = B ∩ D                    可分析理论范围
U = B - D                    未知/未分析区域
V = T ∩ terrain_visible      可见区域
K = T - V                    遮挡区域
```

必须满足：

```text
B = T ∪ U
T = V ∪ K
T ∩ U = ∅
V ∩ K = ∅
```

未知区域 `U` 不参与遮挡率计算，也不能显示为红色遮挡区。

## 5. 推荐架构

### 5.1 统一覆盖画布

后端以完整请求波束的外接范围建立米制投影覆盖画布。DEM 重投影到该画布，DEM 外像元填充 NoData，并同时生成与画布严格对齐的布尔有效像元掩膜。

有效掩膜必须来自 Rasterio/GDAL 的 mask 或 NoData 语义，不能继续使用 `data >= 0` 判断。负海拔是合法地形值，不应被当作无效数据。

在有效像元掩膜基础上，从雷达点按方位向外扫描；某条射线遇到第一个无效像元后，该方向更远的像元全部归入未知区域。由此得到径向连续分析域 `D`。这条保守规则避免跨越 NoData 缺口继续给出地形结论，并保证 `D` 可由每个方位的一条最大半径准确表达。

覆盖画布让后端能够在同一像元网格上计算 `B`、`D`、`T`、`U`、`V` 和 `K`，避免通过不同几何近似计算面积后产生口径差异。

### 5.2 后端掩膜计算

`_coverage_masks` 拆分并返回以下掩膜：

- `raw_theoretical`: 完整理论波束 `B`，不含 DEM 限制。
- `dem_valid_pixels`: DEM 原始有效像元掩膜。
- `analysis_domain`: 从雷达向外径向连续有效的分析域 `D`。
- `theoretical`: `raw_theoretical & analysis_domain`，即 `T`。
- `unknown`: `raw_theoretical & ~analysis_domain`，即 `U`。
- `visible`: `theoretical & terrain_visible`，即 `V`。
- `blocked`: `theoretical & ~visible`，即 `K`。

高度层、二维矢量结果、体素和地形裁切波束均复用这些基础掩膜，不各自实现一套 DEM 边界判断。

雷达点如果位于栅格 bounds 内但落在 NoData 像元上，任务应以 `RADAR_ON_DEM_NODATA` 拒绝。完整波束与有效 DEM 没有交集时，继续使用 `RANGE_OUTSIDE_DEM`。

### 5.3 输出几何

现有 `radar_range.geojson` 改为输出 `T`，即裁剪后的可分析理论范围。`visible.geojson` 和 `blocked.geojson` 继续分别输出 `V` 和 `K`。

完整请求边界不需要新增大型栅格输出。后端任务模型已经包含扫描参数和 `effective_max_range_m`，前端可据此绘制一条低成本参考轮廓。

为了裁剪三维波束，后端在任务模型中增加紧凑的水平裁剪剖面：

```json
{
  "beam_clip_profile": {
    "azimuth_step_deg": 2,
    "radius_m": [50000, 49820, 49110]
  }
}
```

每个方位的半径表示从雷达点沿该方向连续落在 DEM 有效分析域内的最大距离，并受有效最大探测距离限制。遇到 NoData 缺口时在第一个缺口处截断，不跨越未知区域恢复波束。

2 度采样时全向波束只有 180 个数值，API 体积可控；扇区只需覆盖扇区方位并包含两侧边界。

### 5.4 三维波束

前端 `radarVolumeLayer` 接收可选的 `beam_clip_profile`，将当前单一 `radius` 改为按方位查询半径。主体网格、顶部网格、扫描面、射线、边界线和辅助瓣必须调用同一个半径函数，避免只有填充面被裁剪而线框仍越界。

展示规则：

- “可分析理论波束”：使用裁剪剖面生成实心三维体，默认显示。
- “完整请求边界”：使用完整有效半径绘制低透明度灰色轮廓，默认关闭。
- DEM 外未知区域：不绘制实心填充，不使用遮挡区红色。

任务运行前的即时预览尚无精确有效像元剖面，先使用已选 DEM 的经纬度 bounds 做矩形裁剪。任务完成后切换到后端返回的有效像元剖面。旧任务缺少剖面时也使用 DEM bounds 回退；要获得 NoData 精确裁剪需要重新运行任务。

### 5.5 指标兼容

保留现有字段，但明确其口径：

- `theoretical_area_m2 = area(T)`，DEM 内可分析的理论面积。
- `visible_area_m2 = area(V)`。
- `blocked_area_m2 = area(K)`。
- `blocked_ratio = area(K) / area(T)`。

新增字段：

- `requested_theoretical_area_m2 = area(B)`。
- `unknown_area_m2 = area(U)`。
- `dem_coverage_ratio = area(T) / area(B)`。

所有面积直接由同一投影网格的像元数乘像元面积得到。允许的数值误差不超过一个边界像元带来的面积误差，并保证：

```text
requested_theoretical_area_m2 ≈ theoretical_area_m2 + unknown_area_m2
theoretical_area_m2 ≈ visible_area_m2 + blocked_area_m2
```

任务列表、任务详情、指标接口、`model_metadata.json` 和 `output_manifest.json` 使用相同字段定义。融合分析继续只使用裁剪后的 `range_geojson`，因此 DEM 外区域不会被计入融合盲区。

## 6. 数据流

```text
上传 DEM
  -> 读取 bounds、NoData 和有效像元 mask
  -> 创建完整请求范围的投影覆盖画布
  -> 重投影 DEM 与有效 mask
  -> 生成 raw_theoretical / dem_valid_pixels / analysis_domain
  -> 运行 viewshed 并生成 terrain_visible
  -> 计算 theoretical / unknown / visible / blocked
  -> 输出 GeoJSON、指标和 beam_clip_profile
  -> 前端绘制裁剪后的二维范围和三维波束
  -> 可选叠加完整请求边界
```

## 7. 错误处理和边界条件

- 雷达位于 DEM bounds 外：`RADAR_OUTSIDE_DEM`。
- 雷达位于 bounds 内但为 NoData：`RADAR_ON_DEM_NODATA`。
- DEM 与理论波束无有效交集：`RANGE_OUTSIDE_DEM`。
- DEM 仅覆盖部分波束但达到当前最低覆盖阈值：任务继续，未知面积和覆盖率写入结果，并给出 warning。
- 精确有效覆盖率低于最低阈值：任务失败，错误信息同时返回实际覆盖率和最低要求。
- DEM 没有显式 NoData：使用数据集 mask；如果 mask 全有效，则从雷达沿径向到栅格 bounds 的区域都属于分析域。
- 旧任务没有 `beam_clip_profile`：前端按 DEM bounds 回退，不阻断历史结果加载。

## 8. 测试方案

### 8.1 后端单元测试

1. 构造波束超出 DEM 的小栅格，验证 `raw_theoretical = theoretical ∪ unknown`。
2. 验证未知像元不会进入 `blocked`。
3. 构造包含 NoData 缺口的 DEM，验证裁剪剖面在第一个缺口处停止。
4. 构造负海拔 DEM，验证负值仍属于有效分析域。
5. 验证雷达落在 NoData 像元时返回 `RADAR_ON_DEM_NODATA`。
6. 分别覆盖全向、扇区、雷达方程限距和俯仰角限距。
7. 验证两组面积恒等式在像元误差容限内成立。

### 8.2 API 和输出测试

1. `radar_range.geojson` 的所有坐标都落在 DEM 有效范围内。
2. 指标接口和任务详情返回新增面积字段与裁剪剖面。
3. 旧任务 JSON 缺少新增字段时仍能被正常反序列化。
4. 融合盲区不包含任一任务的 DEM 外未知区域。

### 8.3 前端测试

1. 方位半径插值在 0/360 度处连续。
2. 主体、顶部、线框、扫描面和辅助瓣使用同一裁剪半径。
3. 裁剪剖面缺失时按 DEM bounds 回退。
4. 完整请求边界默认关闭，未知区域不出现红色填充。
5. 运行 TypeScript 类型检查和生产构建。

### 8.4 端到端验收

使用一个明显小于理论圆范围且含 NoData 边缘的合成 DEM：

- 公网页面中的二维理论范围不得越过有效 DEM 边界。
- 三维实心波束不得越过有效 DEM 边界。
- 可选完整边界仍能显示原始圆/扇区。
- DEM 外区域不进入可见面积、遮挡面积或融合盲区。
- 页面、静态资源和雷达 API 保持可用。

## 9. 实施范围

预计涉及：

- `backend/app/services/coverage_model.py`
- `backend/app/workers/coverage_task.py`
- `backend/app/schemas/radar.py`
- `backend/app/services/fusion_analysis.py`（仅验证或调整范围语义）
- 后端覆盖模型、任务输出、API 和融合测试
- `frontend/src/api/client.ts`
- `frontend/src/App.vue`
- `frontend/src/map/radarVolumeLayer.ts`
- 前端图层控制文案和构建验证
- `docs/radar_coverage_metrics_api.md`

不包含数据库迁移；历史任务通过可选字段和 bounds 回退保持兼容。
