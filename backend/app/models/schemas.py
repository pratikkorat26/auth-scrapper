from typing import Optional

from pydantic import BaseModel, Field, field_validator


class AnalyzeRequest(BaseModel):
    url: str = Field(..., examples=["https://example.com"])

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("URL is required.")
        if not (normalized.startswith("http://") or normalized.startswith("https://")):
            raise ValueError("URL must start with http:// or https://")
        return normalized


class AnalyzeResponse(BaseModel):
    url: str
    found: bool
    confidence: float = Field(..., ge=0.0, le=1.0)
    signals: list[str]
    snippet: Optional[str] = None
    message: str


class HealthResponse(BaseModel):
    status: str
