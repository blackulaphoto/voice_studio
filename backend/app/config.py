from __future__ import annotations

from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STORAGE_ROOT = PROJECT_ROOT / "storage"


class Settings(BaseSettings):
    """Runtime settings for the self-hosted voice studio."""

    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    app_name: str = "Athena Voice Studio"
    api_prefix: str = "/api"
    storage_root: Path = DEFAULT_STORAGE_ROOT
    qwen_model_id: str = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
    force_device: str | None = None
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    max_upload_mb: int = 250

    def model_post_init(self, __context: object) -> None:
        root = self.storage_root.expanduser()
        if not root.is_absolute():
            root = PROJECT_ROOT / root
        self.storage_root = root.resolve()

    @property
    def voices_dir(self) -> Path:
        return self.storage_root / "voices"

    @property
    def samples_dir(self) -> Path:
        return self.storage_root / "samples"

    @property
    def generations_dir(self) -> Path:
        return self.storage_root / "generations"

    @property
    def db_path(self) -> Path:
        return self.storage_root / "athena_voice.db"

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def ensure_directories(self) -> None:
        for directory in (self.storage_root, self.voices_dir, self.samples_dir, self.generations_dir):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
