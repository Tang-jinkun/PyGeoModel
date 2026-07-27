from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PYGEOMODEL_", env_file=".env", extra="ignore")

    project_root: Path = Path(__file__).resolve().parents[3]
    data_dir: Path | None = None
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    max_upload_mb: int = 500
    tianditu_token: SecretStr | None = None
    tianditu_referer: str | None = None

    @field_validator("tianditu_referer")
    @classmethod
    def validate_tianditu_referer(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        parsed = urlsplit(value.strip())
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("TianDiTu referer must be an HTTP(S) origin")
        return f"{parsed.scheme}://{parsed.netloc}"

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
