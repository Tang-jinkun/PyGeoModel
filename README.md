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
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The backend expects `gdal_viewshed` to be available on `PATH`. The Docker setup installs GDAL inside the backend container.

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

## Docker Compose

```bash
docker compose up --build
```

Services:

- Backend API: `http://localhost:8000`
- Frontend: `http://localhost:5173`

## MVP Workflow

1. Upload a GeoTIFF DEM.
2. Enter radar location, radar height, target height, max range, and scan mode.
3. Submit a coverage task.
4. Backend reprojects the DEM, runs `gdal_viewshed`, vectorizes visible and blocked regions, and writes outputs.
5. Frontend loads `visible.geojson`, `blocked.geojson`, and `radar_range.geojson` in MapLibre.

## Important Limits

- Use projected meter-based coordinates for calculation; the backend selects UTM from radar longitude/latitude.
- Recommended max range for the first version is 50-100 km.
- Large DEMs and huge GeoJSON outputs still need optimization.
- The MapLibre terrain base layer currently uses public demo terrain tiles; uploaded DEMs are used for calculation, not yet for 3D terrain tile rendering.

## Remote Repository

Target remote:

```bash
git remote add origin git@github.com:Tang-jinkun/PyGeoModel.git
```
