from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from dataclasses import dataclass
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError, model_validator

from ..core.config import get_settings
from .browser import enrich_components_with_browser
from .detector import (
    AuthComponent,
    DetectionResult,
    choose_primary_component,
    detect_auth_component,
)

logger = logging.getLogger(__name__)

try:
    from google import genai
    from google.genai import types
except ImportError:  # pragma: no cover
    genai = None
    types = None


class GeminiComponentDecision(BaseModel):
    type: Literal["traditional", "oauth", "passwordless", "multi_step", "challenge", "unknown_auth_surface"]
    surface_type: Optional[str] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    selector_hint: Optional[str] = None
    providers: list[str] = Field(default_factory=list)
    summary: str
    snippet: Optional[str] = None


class GeminiDecision(BaseModel):
    status: Literal["found", "partial_auth_surface", "not_found", "blocked_or_inconclusive"]
    message: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    components: list[GeminiComponentDecision] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_components_for_auth_outcomes(self) -> "GeminiDecision":
        if self.status in {"found", "partial_auth_surface"} and not self.components:
            raise ValueError("components are required for auth outcomes")
        return self


@dataclass
class AIFallbackResult:
    detection: DetectionResult
    ai_confidence: float
    refined: bool
    provider: str
    model: str


EXTRACTION_PATTERNS = (
    re.compile(r"<form[^>]*>[\s\S]{0,2000}?<input[^>]*type=[\"']password[\"'][^>]*>[\s\S]{0,2000}?<\/form>", re.IGNORECASE),
    re.compile(r"<form[^>]*(?:login|signin|sign-in|signup|sign-up|auth|register)[^>]*>[\s\S]{0,1500}?<\/form>", re.IGNORECASE),
    re.compile(r"<(?:nav|header|div|section)[^>]{0,300}>[\s\S]{0,3000}?(?:sign|login|register|auth|log in|sign up|join|get started)[\s\S]{0,3000}?<\/(?:nav|header|div|section)>", re.IGNORECASE),
    re.compile(r"<(?:button|a)[^>]*>[\s\S]{0,500}?<\/(?:button|a)>", re.IGNORECASE),
    re.compile(r"<div[^>]*(?:class|id)=[\"'][^\"']*(?:login|signin|sign-in|auth|authentication|oauth|social)[^\"']*[\"'][^>]*>[\s\S]{0,1500}?<\/div>", re.IGNORECASE),
    re.compile(r"<(?:webauthn-subtle|dialog)[^>]*>[\s\S]{0,1000}?<\/(?:webauthn-subtle|dialog)>", re.IGNORECASE),
)


def ai_fallback_available() -> bool:
    settings = get_settings()
    return settings.enable_ai_fallback and bool(settings.gemini_api_key) and genai is not None and types is not None


def should_use_ai_fallback(detection: DetectionResult, browser_used: bool = False) -> bool:
    settings = get_settings()
    return (
        detection.status in {"partial_auth_surface", "blocked_or_inconclusive"}
        or (detection.found and detection.confidence < settings.ai_low_confidence_threshold)
        or (browser_used and len(detection.components) > 1)
    )


async def refine_detection_with_ai(
    url: str,
    html: str,
    detection: DetectionResult,
    screenshot_base64: Optional[str] = None,
    browser_url: Optional[str] = None,
) -> Optional[AIFallbackResult]:
    settings = get_settings()
    if not settings.enable_ai_fallback or not settings.gemini_api_key or genai is None or types is None:
        return None

    extracted_html = extract_relevant_sections(html)
    heuristic_summary = {
        "status": detection.status,
        "confidence": detection.confidence,
        "signals": detection.signals,
        "message": detection.message,
        "components": [
            {
                "type": component.type,
                "surface_type": component.surface_type,
                "confidence": component.confidence,
                "selector_hint": component.selector_hint,
                "providers": component.providers,
                "summary": component.summary,
            }
            for component in detection.components
        ],
    }

    def _call_gemini() -> GeminiDecision:
        client = genai.Client(api_key=settings.gemini_api_key)
        prompt = _build_prompt(url, extracted_html, heuristic_summary, include_screenshot=bool(screenshot_base64))
        parts = [prompt]
        if screenshot_base64 and settings.enable_ai_screenshot_context:
            parts.append(types.Part.from_bytes(data=base64.b64decode(screenshot_base64), mime_type="image/jpeg"))

        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=parts,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0,
            ),
        )
        return GeminiDecision.model_validate(json.loads(response.text))

    try:
        decision = await asyncio.to_thread(_call_gemini)
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("gemini fallback parse failed", extra={"url": url, "error": str(exc)})
        return None
    except Exception as exc:  # pragma: no cover
        logger.warning("gemini fallback failed", extra={"url": url, "error": str(exc)})
        return None

    components = [_component_from_ai_decision(item) for item in decision.components]
    if browser_url and components:
        components = await enrich_components_with_browser(browser_url, components)

    components = [_normalize_component(component) for component in components]
    primary = choose_primary_component(components)
    detection_from_ai = _build_detection_from_ai(decision, components, primary, detection)
    return AIFallbackResult(
        detection=detection_from_ai,
        ai_confidence=decision.confidence,
        refined=_is_refined(decision, components, detection),
        provider="gemini",
        model=settings.gemini_model,
    )


def extract_relevant_sections(html: str) -> str:
    settings = get_settings()
    sections: list[str] = []
    for pattern in EXTRACTION_PATTERNS:
        sections.extend(pattern.findall(html))

    unique_sections = list(dict.fromkeys(section for section in sections if section.strip()))
    excerpt = "\n\n".join(unique_sections)
    if not excerpt:
        body_match = re.search(r"<body[^>]*>([\s\S]*)<\/body>", html, re.IGNORECASE)
        excerpt = body_match.group(1) if body_match else html

    return excerpt[: settings.ai_max_input_chars]


def _build_prompt(url: str, html: str, heuristic_summary: dict, include_screenshot: bool) -> str:
    screenshot_line = "A screenshot of the rendered page is also provided for visual context.\n" if include_screenshot else ""
    return (
        "You identify authentication surfaces on websites.\n"
        "Return JSON only.\n"
        "Classify the page as found, partial_auth_surface, not_found, or blocked_or_inconclusive.\n"
        "Return every meaningful auth component you can identify.\n"
        "Component types must be one of: traditional, oauth, passwordless, multi_step, challenge, unknown_auth_surface.\n"
        "Use selector_hint when you can infer a likely Playwright/CSS selector.\n"
        "Prefer full form markup in snippet when a form exists. Otherwise return the smallest meaningful auth-related container.\n"
        "Challenge pages such as CAPTCHA or access denied should use type=challenge.\n\n"
        f"URL:\n{url}\n\n"
        f"{screenshot_line}"
        f"Heuristic summary:\n{json.dumps(heuristic_summary, ensure_ascii=True)}\n\n"
        f"Rendered HTML excerpt:\n{html}"
    )


def _component_from_ai_decision(component: GeminiComponentDecision) -> AuthComponent:
    snippet_detection = detect_auth_component(component.snippet) if component.snippet else None
    snippet_primary = choose_primary_component(snippet_detection.components) if snippet_detection else None
    return AuthComponent(
        type=component.type,
        surface_type=component.surface_type or (snippet_primary.surface_type if snippet_primary else None),
        confidence=component.confidence,
        selector_hint=component.selector_hint,
        signals=snippet_primary.signals if snippet_primary else [],
        providers=component.providers or (snippet_primary.providers if snippet_primary else []),
        fields=snippet_primary.fields if snippet_primary else [],
        snippet=component.snippet,
        summary=component.summary,
    )


def _normalize_component(component: AuthComponent) -> AuthComponent:
    snippet_detection = detect_auth_component(component.snippet) if component.snippet else None
    primary = choose_primary_component(snippet_detection.components) if snippet_detection else None
    return AuthComponent(
        type=component.type,
        surface_type=component.surface_type or (primary.surface_type if primary else None),
        confidence=component.confidence,
        selector_hint=component.selector_hint or (primary.selector_hint if primary else None),
        signals=primary.signals if primary and primary.signals else component.signals,
        providers=component.providers or (primary.providers if primary else []),
        fields=primary.fields if primary and primary.fields else component.fields,
        snippet=primary.snippet if primary and primary.snippet else component.snippet,
        summary=component.summary,
    )


def _build_detection_from_ai(
    decision: GeminiDecision,
    components: list[AuthComponent],
    primary: Optional[AuthComponent],
    baseline: DetectionResult,
) -> DetectionResult:
    signals = primary.signals if primary else baseline.signals
    if "ai_gemini" not in signals:
        signals = sorted(set(signals + ["ai_gemini"]))

    found = any(component.type != "challenge" for component in components) and decision.status in {"found", "partial_auth_surface"}

    return DetectionResult(
        found=found,
        confidence=primary.confidence if primary else decision.confidence,
        signals=signals,
        snippet=primary.snippet if primary else baseline.snippet,
        message=decision.message,
        status=decision.status,
        surface_type=primary.surface_type if primary else baseline.surface_type,
        fields=primary.fields if primary else baseline.fields,
        actions=[],
        providers=primary.providers if primary else baseline.providers,
        components=components or baseline.components,
    )


def _is_refined(decision: GeminiDecision, components: list[AuthComponent], baseline: DetectionResult) -> bool:
    primary = choose_primary_component(components)
    return any(
        [
            decision.status != baseline.status,
            abs(decision.confidence - baseline.confidence) >= 0.05,
            bool(primary and primary.snippet != baseline.snippet),
            decision.message != baseline.message,
            len(components) != len(baseline.components),
        ]
    )
