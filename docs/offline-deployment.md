# PyGeoModel 离线交付与部署说明

本交付物包含后端、前端、前端依赖快照、演示 DEM、四个 Docker 镜像归档和启动脚本。接收方不需要联网拉取镜像、安装 Python/npm 依赖或重新构建镜像即可启动。

## 1. 目标平台

| 交付镜像 | 使用环境 |
| --- | --- |
| `linux/amd64` | Windows x64 + Docker Desktop，且 Docker Desktop 使用 Linux containers |
| `linux/arm64` | ARM64 Linux 服务器 + Docker Engine/Compose v2 |

Windows 版本不是 Windows 原生容器，而是 Docker Desktop Linux 容器。启动脚本会根据主机架构自动选择对应镜像归档。

## 2. 交付目录

```text
PyGeoModel-offline/
├─ backend/                         后端源码与 Dockerfile
├─ frontend/                        前端源码、package-lock.json、node_modules
├─ data/                            演示 DEM、DEM COG、场景及运行时数据目录
├─ deploy/offline/
│  ├─ docker-compose.yml            仅引用本地镜像，不含 build/pull
│  ├─ start-offline.ps1             Windows 启动脚本
│  └─ start-offline.sh              Linux 启动脚本
├─ images/                          四个 Docker-loadable 镜像归档
├─ docs/offline-deployment.md
├─ MANIFEST.txt
└─ SHA256SUMS
```

源码中的 `frontend/node_modules` 是交付快照，便于完全离线查看、测试和二次开发；实际运行使用已经封装在镜像中的依赖。

## 3. 前置条件

- Windows：Docker Desktop，并确认切换到 Linux containers；
- ARM Linux：Docker Engine 和 Docker Compose v2 插件；
- 至少约 2 GB 的交付物、镜像与程序空间，另需运行结果增长所需的数据空间。

不需要安装 Python、Node.js、npm、GDAL 或联网代理。

## 4. 校验交付物

在交付物根目录执行：

Windows PowerShell：

```powershell
Get-Content .\SHA256SUMS | ForEach-Object {
  if ($_ -match '^([0-9a-fA-F]{64})\s{2}(.+)$') {
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Matches[2]).Hash.ToLower()
    if ($actual -ne $Matches[1].ToLower()) { throw "Checksum mismatch: $($Matches[2])" }
  }
}
```

ARM Linux：

```bash
sha256sum -c SHA256SUMS
```

## 5. 启动

### Windows x64 / Docker Desktop

在交付物根目录打开 PowerShell：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\deploy\offline\start-offline.ps1
```

脚本会加载 `linux/amd64` 的两个镜像，并以 `--no-build` 启动 Compose。

### ARM Linux

在交付物根目录执行：

```bash
chmod +x deploy/offline/start-offline.sh
./deploy/offline/start-offline.sh
```

脚本会加载 `linux/arm64` 的两个镜像，并以 `--no-build` 启动 Compose。

浏览器访问 `http://127.0.0.1:5173/`；后端健康检查地址为 `http://127.0.0.1:8000/api/health`。

## 6. 端口与数据

默认只绑定本机：前端 `5173`，后端 `8000`。启动前可通过环境变量修改端口或绑定地址：

```powershell
$env:PYGEOMODEL_FRONTEND_PORT = "8517"
$env:PYGEOMODEL_BACKEND_PORT = "8800"
.\deploy\offline\start-offline.ps1
```

Linux 示例：

```bash
PYGEOMODEL_FRONTEND_PORT=8517 PYGEOMODEL_BACKEND_PORT=8800 ./deploy/offline/start-offline.sh
```

数据持久化在交付物的 `data/`：上传的 DEM、任务、结果不会写入镜像。不要删除 `data/dem/` 中的演示 DEM；`data/tasks/`、`data/outputs/` 和 `data/uploads/` 可继续写入运行数据。

全国 DEM 建议通过服务器本地导入，不通过浏览器上传。将原始 GeoTIFF 放到 `data/import/` 后，在服务运行时执行：

```bash
docker compose -f deploy/offline/docker-compose.yml exec backend \
  python /app/scripts/import_dem.py \
  --source /workspace/import/national.tif \
  --dem-id national-dem
```

导入会校验 CRS、单波段和范围，在 `data/dem/national-dem/` 中生成带 256×256 内部瓦片、DEFLATE 压缩和 overviews 的 `dem.cog.tif`，并在最后写入 `metadata.json`。原始全国 TIFF 不会复制到应用数据目录；后续雷达、炮兵、无人机、岗哨、机动性和走廊任务都从 COG 按任务范围读取窗口。导入完成后可以从 `data/import/` 移走原始文件以释放空间。

`--dem-id` 可以使用字母、数字、下划线和连字符；同一个 ID 已存在时导入会拒绝覆盖。普通小文件上传接口仍保持不变，历史 DEM 没有 COG 时会在首次计算或渲染时按需生成。

查看状态：

```bash
docker compose -f deploy/offline/docker-compose.yml ps
```

停止并保留数据：

```bash
docker compose -f deploy/offline/docker-compose.yml down
```

## 7. 离线行为说明

Compose 不执行 `docker pull`，启动脚本也不执行 `docker build`。前端通过 `PYGEOMODEL_OFFLINE=1` 使用无外部数据源的本地样式，不请求天地图或其他在线底图。

DEM 三维地形仍然可用：后端从本地 DEM 生成 Terrarium 高程瓦片，前端通过 `raster-dem` 和 `setTerrain()` 生成地形几何。由于完全离线不包含在线底图，三维表面不会显示天地图纹理，但本地 DEM 地形和分析结果图层仍可渲染。

## 8. 重新构建镜像（仅交付制作方）

重新制作交付物的机器需要联网访问 Debian/PyPI/npm 镜像，并运行 Docker Desktop 或 Docker Engine：

```powershell
.\deploy\offline\build-images.ps1
.\deploy\offline\package-source.ps1
```

构建脚本分别导出 `linux/amd64` 与 `linux/arm64` 的 Docker-loadable tar。接收方不需要执行这一步。
