# PyGeoModel

PyGeoModel is a map-first GIS workbench for running and visualizing seven DEM-backed analysis models:

- radar coverage;
- UAV reconnaissance;
- watchpost detection;
- artillery coverage;
- reconnaissance vehicle coverage;
- wheeled/tracked mobility comparison;
- air corridor planning.

The frontend keeps one MapLibre map while preserving independent model drafts, concurrent task polling, task history, metrics, output files, and result layers. Radar also includes profile analysis, multi-task fusion, height layers, theoretical volume, voxel, and terrain-clipped volume rendering.

## Current Skeleton

- `backend/`: FastAPI service for DEM upload, seven task APIs, GDAL-backed viewshed execution, vector outputs, and result serving.
- `frontend/`: Vue, MapLibre GL, and Three.js single-page GIS workbench.
- `data/`: local runtime storage for uploaded DEMs, task JSON, and outputs.
- `docs/`: technical plan and feasibility notes.

## Local Development Without Docker

Docker is optional. The normal local workflow uses a Python virtual environment and Vite directly.

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Windows PowerShell with an existing environment:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The radar and other viewshed-based models require `gdal_viewshed` on `PATH`. A missing GDAL executable is reported as a real task failure; the service does not generate placeholder outputs. `gdal_translate` is used when available for COG generation, with Rasterio as the local COG writer fallback.

Health check:

```bash
curl http://localhost:8000/api/health
```

### Frontend

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1
```

Open:

```text
http://localhost:5173
```

The Vite dev server proxies `/api` and `/outputs` to `http://localhost:8000` by default. Override the backend or deployment base path when needed:

```powershell
$env:VITE_PROXY_TARGET = "http://127.0.0.1:8000"
$env:VITE_BASE_PATH = "/"
npm run dev -- --host 127.0.0.1
```

`VITE_API_BASE` can point a production build directly at an API origin. `VITE_BASE_PATH` controls the Vite asset base and defaults to `/`.

## Optional Docker Compose

```bash
docker compose up --build
```

Services:

- Backend API: `http://localhost:8000`
- Frontend: `http://localhost:5173`

The compose build uses Tencent Cloud mirrors for Debian apt and npm package downloads, and official PyPI for Python packages. To speed up Docker Hub base image pulls on Tencent Cloud hosts, configure the Docker daemon registry mirror:

```json
{
  "registry-mirrors": ["https://mirror.ccs.tencentyun.com"]
}
```

Then restart Docker and rebuild:

```bash
sudo systemctl restart docker
docker compose build --pull
```

## Workbench Workflow

1. Upload a GeoTIFF DEM.
2. Select one of the seven analysis models.
3. Configure point, route, start/end, or threat inputs in the form or on the map.
4. Submit the task and continue working while it polls in the background.
5. Inspect task status, metrics, map layers, and downloadable files.
6. Restore a historical request without resubmitting it, or delete disposable tasks explicitly.

## Radar Calculation Chain

```text
detectable area = max radar range ∩ scan sector ∩ DEM viewshed
```

The radar layer supports projected analysis, DEM-bounded allocation, conservative NoData handling, beam clipping, optional radar-equation range constraints, profile analysis, and compatible-task fusion.

## Verification

The backend model layer now includes:

- UTM zone selection from radar longitude/latitude.
- Radar point validation against the source DEM bounds.
- DEM crop around the requested max range before reprojection.
- Reprojection to a meter-based CRS for viewshed calculation.
- Scan range geometry for omni and sector modes.
- Viewshed raster vectorization into visible geometry.
- Visible/blocked/theoretical area metrics in square meters.
- Finished task fusion API for visible union, redundant overlap, and blind-area analysis across multiple radar coverage results.

Model tests:

```bash
cd backend
source .venv/bin/activate
python -m pytest -q
```

Frontend tests and build:

```bash
cd frontend
npm test
npm run build
```

## Synthetic Demo Scenarios

With Docker services running, generate and execute the six non-radar demo scenarios against the local DEM:

```powershell
docker compose up -d --build
docker compose exec -T backend python /app/scripts/generate_demo_scenarios.py --data-dir /workspace/data --dem-id dem_20260713_080113_884937cf
docker compose exec -T backend python /app/scripts/run_demo_scenarios.py --data-dir /workspace/data --dem-id dem_20260713_080113_884937cf --api-base-url http://127.0.0.1:8000
```

Generated scenario files and `scenario-index.json` are stored under `data/demo-scenarios/<dem-id>/`. They are synthetic runtime data and are not committed to Git.

## Important Limits

- Use projected meter-based coordinates for calculation; the backend selects UTM from radar longitude/latitude.
- Recommended radar max range is 50-100 km unless the available DEM and machine capacity justify more.
- Large DEMs and huge GeoJSON outputs still need optimization.
- Uploaded DEMs are served as raster and Terrarium terrain tiles for MapLibre display, while the same source DEM is used for calculation.
- The production frontend bundle currently emits Vite's large-chunk warning; functional tests and type checking still pass.

## Remote Repository

Target remote:

```bash
git remote add origin git@github.com:Tang-jinkun/PyGeoModel.git
```
