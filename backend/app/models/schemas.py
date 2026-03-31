from typing import Literal, Optional

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


class AuthComponentResponse(BaseModel):
    type: Literal["traditional", "oauth", "passwordless", "multi_step", "challenge", "unknown_auth_surface"]
    surface_type: Optional[str] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    selector_hint: Optional[str] = None
    signals: list[str] = Field(default_factory=list)
    providers: list[str] = Field(default_factory=list)
    fields: list[dict] = Field(default_factory=list)
    snippet: Optional[str] = None
    summary: str


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
    ai_used: bool
    ai_refined: bool
    ai_provider: Optional[str] = None
    ai_model: Optional[str] = None
    components: list[AuthComponentResponse] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
