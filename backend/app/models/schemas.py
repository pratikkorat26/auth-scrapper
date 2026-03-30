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
    status: str
    signals: list[str]
    snippet: Optional[str] = None
    message: str
    analysis_mode: str
    fallback_used: bool
    interaction_used: bool
    surface_type: Optional[str] = None
    fields: list[dict] = Field(default_factory=list)
    actions: list[dict] = Field(default_factory=list)
    providers: list[str] = Field(default_factory=list)
    alternate_candidates: list[dict] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
