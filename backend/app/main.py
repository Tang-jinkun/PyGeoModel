from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import air_corridor, artillery, dem, mobility, radar, recon_vehicle, uav, watchpost
from app.core.config import settings
from app.services.air_corridor_task_store import recover_interrupted_air_corridor_tasks
from app.services.artillery_task_store import recover_interrupted_artillery_tasks
from app.services.mobility_task_store import recover_interrupted_mobility_tasks
from app.services.recon_vehicle_task_store import recover_interrupted_recon_vehicle_tasks
from app.services.task_store import recover_interrupted_tasks
from app.services.uav_task_store import recover_interrupted_uav_tasks
from app.services.watchpost_task_store import recover_interrupted_watchpost_tasks


def create_app() -> FastAPI:
    app = FastAPI(
        title="PyGeoModel API",
        description="DEM-based radar terrain coverage analysis service.",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    settings.ensure_directories()
    recover_interrupted_tasks()
    recover_interrupted_uav_tasks()
    recover_interrupted_watchpost_tasks()
    recover_interrupted_artillery_tasks()
    recover_interrupted_recon_vehicle_tasks()
    recover_interrupted_mobility_tasks()
    recover_interrupted_air_corridor_tasks()
    app.mount("/outputs", StaticFiles(directory=settings.outputs_dir), name="outputs")
    app.include_router(dem.router, prefix="/api/dem", tags=["DEM"])
    app.include_router(radar.router, prefix="/api/radar", tags=["Radar"])
    app.include_router(uav.router, prefix="/api/uav", tags=["UAV"])
    app.include_router(watchpost.router, prefix="/api/watchpost", tags=["Watchpost"])
    app.include_router(artillery.router, prefix="/api/artillery", tags=["Artillery"])
    app.include_router(recon_vehicle.router, prefix="/api/recon-vehicle", tags=["Recon Vehicle"])
    app.include_router(mobility.router, prefix="/api/mobility", tags=["Mobility"])
    app.include_router(air_corridor.router, prefix="/api/air-corridor", tags=["Air Corridor"])

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
