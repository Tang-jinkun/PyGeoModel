from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PYGEOMODEL_", env_file=".env", extra="ignore")

    project_root: Path = Path(__file__).resolve().parents[3]
    data_dir: Path | None = None
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    max_upload_mb: int = 500

    @property
    def resolved_data_dir(self) -> Path:
        return self.data_dir or self.project_root / "data"

    @property
    def dem_dir(self) -> Path:
        return self.resolved_data_dir / "dem"

    @property
    def tasks_dir(self) -> Path:
        return self.resolved_data_dir / "tasks"

    @property
    def outputs_dir(self) -> Path:
        return self.resolved_data_dir / "outputs"

    def ensure_directories(self) -> None:
        for path in (self.dem_dir, self.tasks_dir, self.outputs_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings


settings = get_settings()
