from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "TIF Normas Assistant API"
    app_env: str = "dev"
    app_version: str = "1.0.0"
    app_log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"

    database_url: str = "postgresql+psycopg://tif:tif_password@db:5432/tif_normas"
    db_echo: bool = False
    legacy_sqlite_path: str = "data/normas.db"

    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    openai_timeout_seconds: float = 60.0

    retrieval_top_k_default: int = 8
    retrieval_top_k_max: int = 20
    retrieval_candidate_pool: int = 200
    retrieval_snippet_chars: int = 2000

    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(origin).strip() for origin in value if str(origin).strip()]

        if isinstance(value, str):
            parts = [item.strip() for item in value.split(",")]
            return [item for item in parts if item]

        return []


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
