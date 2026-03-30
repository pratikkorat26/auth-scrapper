from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "INFO"
    request_timeout_seconds: float = 10.0
    max_snippet_length: int = 800
    frontend_origin: str = "http://localhost:5173"
    enable_browser_fallback: bool = True
    browser_timeout_seconds: float = 15.0
    browser_headless: bool = True
    enable_limited_auth_reveal: bool = True

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
