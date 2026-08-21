# 雷达地形遮挡红色体积设计

## 目标

在不增加雷达 API 参数、不改变任务创建/查询/产物下载接口的前提下，为现有单雷达和多雷达三维 GLB 增加独立的红色地形遮挡体。绿色只表示可见体积，红色只表示理论探测域内且确定被地形遮挡的体积；DEM NoData、DEM 外部和无法判定区域保持未知。

## 设计

单雷达继续使用现有 DEM 窗口、投影和高度场采样。对每个水平采样点计算理论下边界、绿色下边界和球面/最大仰角上边界。绿色 mesh 使用 `[visible_lower, nominal_upper]`，红色 mesh 使用 `[nominal_lower, min(visible_lower, nominal_upper)]`；只在边界严格有序时生成，并保留极小间隙以避免共享透明面闪烁。DEM、阈值、分析域、范围、扇区和仰角掩膜共同限制两种体积。

`RadarVisibilityVolume` 同时携带绿色和红色高度场 mesh 及其统计。单雷达 GLB 在 `radar_result/detectable_shell` 下保留绿色节点，在 `radar_result/blocked_volume` 下新增红色节点，并写入 `visibility_semantics: terrain_occluded`。如果绿色不存在但红色存在，只导出红色；如果高度场没有可用单元，保留现有 visual dome fallback，未知区域不标红。

多雷达 aggregate 在既有固定高度融合网格上同时聚合成功站点的可见掩膜和理论覆盖掩膜。只有所有请求站点都成功时才生成 `theoretical_union && visible_count == 0` 的确定性红色体积；partial 任务只生成成功站点的绿色 union，不生成联合红色，并把不可用原因放进任务消息。`fusion_scene.glb` 新增 `multi_radar_fusion/blocked_volume`，保留 union/overlap/triple_overlap 语义。cooperative_3d 继续为成功站点生成各自完整单站 scene_glb；交会 GLB 仍只使用共同绿色 envelope，不合并单站红色。

前端保持原有 GLB 下载和加载路径。红色节点由 GLB 默认可见；透明体积统一关闭 depthWrite，并按语义设置稳定 renderOrder。场景颜色调整只修改可配色材质，具有 `visibility_semantics: terrain_occluded` 的红色材质保持原始红色。没有新节点的历史 GLB 继续按现有逻辑加载。

## 验证

覆盖平坦 DEM、山脊/阈值遮挡、范围/扇区/仰角边界、NoData、红色-only 单雷达、aggregate 联合可见/联合遮挡、partial 任务、cooperative 交会和前端历史 GLB 兼容；运行现有后端 38 个相关测试、前端 340 个测试及新增针对性测试。
