# Centralised application settings, loaded from environment variables
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Runtime configuration. Every value can be overridden via the environment

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Employee Leave Q&A Assistant"
    app_env: str = "development"
    log_level: str = "INFO"
    workbook_path: Path = Path("../data/AI_Engineer_Leave_Management_Dataset.xlsx")
    workbook_auto_refresh: bool = True
    upload_dir: Path = Path("../data/uploads")
    max_upload_mb: float = 10.0
    max_upload_rows: int = 20000
    max_upload_columns: int = 100
    max_retrieved_chunks: int = 5
    min_relevance_score: float = 0.0
    groq_api_key: str | None = None
    groq_circuit_failure_threshold: int = 3
    groq_circuit_cooldown_seconds: float = 30.0
    frontend_origin: str = "http://localhost:5173"
    # local_only: bool = False

    @field_validator("workbook_path")
    @classmethod
    def _resolve_workbook_path(cls, value: Path) -> Path:
        return value if value.is_absolute() else (BACKEND_DIR / value).resolve()

    @field_validator("upload_dir")
    @classmethod
    def _resolve_upload_dir(cls, value: Path) -> Path:
        return value if value.is_absolute() else (BACKEND_DIR / value).resolve()

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.frontend_origin.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
