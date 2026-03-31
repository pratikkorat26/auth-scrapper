from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

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
    enable_safe_identity_typing: bool = True
    enable_ai_fallback: bool = False
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.5-flash"
    ai_low_confidence_threshold: float = 0.65
    ai_max_input_chars: int = 15000
    enable_ai_screenshot_context: bool = True

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
