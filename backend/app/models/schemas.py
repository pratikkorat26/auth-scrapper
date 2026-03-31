from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from ..services.auth_shared import analysis_mode_label_for, is_protected_page, status_label_for

if TYPE_CHECKING:
    from ..services.analysis import AnalysisResult


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
    status_label: str
    signals: list[str]
    snippet: Optional[str] = None
    partial_html_markup: Optional[str] = None
    message: str
    analysis_mode: str
    analysis_mode_label: str
    protected_page: bool
    fallback_used: bool
    interaction_used: bool
    components: list[AuthComponentResponse] = Field(default_factory=list)

    @classmethod
    def from_analysis_result(cls, url: str, result: "AnalysisResult") -> "AnalyzeResponse":
        detection = result.detection
        return cls(
            url=url,
            found=detection.found,
            confidence=detection.confidence,
            status=detection.status,
            status_label=status_label_for(detection.status),
            signals=detection.signals,
            snippet=detection.snippet,
            partial_html_markup=detection.partial_html_markup,
            message=detection.message,
            analysis_mode=result.analysis_mode,
            analysis_mode_label=analysis_mode_label_for(result.analysis_mode),
            protected_page=is_protected_page(detection.status, detection.message),
            fallback_used=result.fallback_used,
            interaction_used=result.interaction_used,
            components=[
                AuthComponentResponse(
                    type=component.type,
                    surface_type=component.surface_type,
                    confidence=component.confidence,
                    selector_hint=component.selector_hint,
                    signals=component.signals,
                    providers=component.providers,
                    fields=[
                        field if isinstance(field, dict) else field.__dict__
                        for field in component.fields
                    ],
                    snippet=component.snippet,
                    summary=component.summary,
                )
                for component in detection.components
            ],
        )


class HealthResponse(BaseModel):
    status: str
