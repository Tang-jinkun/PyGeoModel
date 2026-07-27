# Deployment

The frontend image reads `PYGEOMODEL_API_BASE_URL` when its container starts. The value excludes `/api`. Changing this value, CORS origins, the TianDiTu token, or the bind addresses requires container recreation but not an image rebuild. Changing `VITE_MAP_ENGINE` or the Mapbox token requires rebuilding the frontend image.

The Compose default is local direct-port mode: the frontend at `http://127.0.0.1:5173/` calls the backend at `http://127.0.0.1:8000`. Subpath and public direct-port deployments must set the API base explicitly as shown below.

Keep real tokens in the untracked root `.env` file or another protected environment source. Do not place them in Compose YAML or frontend variables.

## Nginx subpath

```bash
PYGEOMODEL_API_BASE_URL=/PyGeoModel docker compose up -d --build
sudo install -m 0644 deploy/nginx/pygeomodel.conf.example /etc/nginx/sites-available/gsms
sudo nginx -t && sudo systemctl reload nginx
```

The public application is `http://124.221.208.30/PyGeoModel/`. Nginx owns only generic frontend and API routing; artifact downloads and TianDiTu forwarding remain backend API behavior.

## Direct ports

```bash
PYGEOMODEL_API_BASE_URL=http://124.221.208.30:8000 \
PYGEOMODEL_CORS_ORIGINS='["http://124.221.208.30:5173"]' \
PYGEOMODEL_BACKEND_BIND=0.0.0.0 PYGEOMODEL_FRONTEND_BIND=0.0.0.0 \
docker compose up -d --build
```

Open `http://124.221.208.30:5173/`. Firewall rules must allow TCP 5173 and 8000 for this mode.

## Same-origin root proxy

```bash
PYGEOMODEL_API_BASE_URL= docker compose up -d --build
```

Configure the edge proxy to send `/api/` to port 8000 and other root traffic to port 5173.

## Verification

```bash
PYTHONPATH=backend python scripts/verify_deployment.py \
  --frontend-url http://124.221.208.30/PyGeoModel/ \
  --api-base-url http://124.221.208.30/PyGeoModel
```

Add `--task-id TASK_ID` to verify one ready radar descriptor and download. The verifier never prints tile query strings or credential values.
