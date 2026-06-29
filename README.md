# PyGeoModel

PyGeoModel is an MVP-stage web tool for DEM-based radar terrain blockage and coverage visualization.

The first version focuses on a practical GIS calculation chain:

```text
detectable area = max radar range ∩ scan sector ∩ DEM viewshed
```

It intentionally does not implement the full radar equation, RCS modeling, weather attenuation, multi-radar fusion, or production tile publishing yet.

## Current Skeleton

- `backend/`: FastAPI service for DEM upload, task creation, GDAL viewshed execution, vector outputs, and result serving.
- `frontend/`: Vue + MapLibre GL JS single-page tool with upload form, radar parameters, task polling, and map layers.
- `data/`: local runtime storage for uploaded DEMs, task JSON, and outputs.
- `docs/`: technical plan and feasibility notes.

## Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The backend expects `gdal_viewshed` to be available on `PATH`. `gdal_translate` is used when present for COG generation; local Python environments without that command fall back to Rasterio's COG writer. The Docker setup installs GDAL inside the backend container.

Health check:

```bash
curl http://localhost:8000/api/health
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

The Vite dev server proxies `/api` and `/outputs` to the backend. For local development it defaults to `http://localhost:8000`; Docker Compose sets `VITE_PROXY_TARGET=http://backend:8000`.

## Docker Compose

```bash
docker compose up --build
```

Services:

- Backend API: `http://localhost:8000`
- Frontend: `http://localhost:5173`

The compose build passes Tencent Cloud mirrors for Debian apt, pip, and npm package downloads. To speed up Docker Hub base image pulls on Tencent Cloud hosts, configure the Docker daemon registry mirror:

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

## MVP Workflow

1. Upload a GeoTIFF DEM.
2. Enter radar location, radar height, target height, max range, and scan mode.
3. Submit a coverage task.
4. Backend reprojects the DEM, runs `gdal_viewshed`, vectorizes visible and blocked regions, and writes outputs.
5. Frontend loads `visible.geojson`, `blocked.geojson`, and `radar_range.geojson` in MapLibre.

## Model Layer Progress

The backend model layer now includes:

- UTM zone selection from radar longitude/latitude.
- Radar point validation against the source DEM bounds.
- DEM crop around the requested max range before reprojection.
- Reprojection to a meter-based CRS for viewshed calculation.
- Scan range geometry for omni and sector modes.
- Viewshed raster vectorization into visible geometry.
- Visible/blocked/theoretical area metrics in square meters.

Model tests:

```bash
cd backend
source .venv/bin/activate
python -m pytest -q
```

Frontend build check:

```bash
cd frontend
npm run build
```

## Important Limits

- Use projected meter-based coordinates for calculation; the backend selects UTM from radar longitude/latitude.
- Recommended max range for the first version is 50-100 km.
- Large DEMs and huge GeoJSON outputs still need optimization.
- Uploaded DEMs are served as raster and Terrarium terrain tiles for MapLibre display, while the same source DEM is used for calculation.

## Remote Repository

Target remote:

```bash
git remote add origin git@github.com:Tang-jinkun/PyGeoModel.git
```
