from __future__ import annotations

from dataclasses import dataclass

from bs4 import BeautifulSoup

from ..core.config import get_settings
from .browser import BrowserRenderResult, render_html
from .detector import DetectionResult, detect_auth_component
from .fetcher import FetchError, UpstreamTimeoutError, fetch_html

AUTH_INTENT_HINTS = ("login", "log in", "sign in", "signin", "account", "authenticate")


@dataclass
class AnalysisResult:
    detection: DetectionResult
    analysis_mode: str
    fallback_used: bool
    interaction_used: bool


async def analyze_url(url: str) -> AnalysisResult:
    html = await fetch_html(url)
    detection = detect_auth_component(html)

    if detection.status == "found":
        return AnalysisResult(
            detection=detection,
            analysis_mode="static",
            fallback_used=False,
            interaction_used=False,
        )

    if not _should_use_browser_fallback(url, html, detection):
        return AnalysisResult(
            detection=detection,
            analysis_mode="static",
            fallback_used=False,
            interaction_used=False,
        )

    settings = get_settings()
    if not settings.enable_browser_fallback:
        return AnalysisResult(
            detection=detection,
            analysis_mode="static",
            fallback_used=False,
            interaction_used=False,
        )

    try:
        browser_result = await render_html(url)
        browser_detection = detect_auth_component(browser_result.html)
        if browser_detection.status == "not_found":
            browser_detection.status = "blocked_or_inconclusive"
            browser_detection.message = "Unable to confirm a login surface after browser rendering."
        return AnalysisResult(
            detection=browser_detection,
            analysis_mode="browser_fallback",
            fallback_used=True,
            interaction_used=browser_result.interaction_used,
        )
    except (FetchError, UpstreamTimeoutError) as exc:
        return AnalysisResult(
            detection=DetectionResult(
                found=False,
                confidence=0.0,
                signals=[],
                snippet=None,
                message=str(exc),
                status="blocked_or_inconclusive",
            ),
            analysis_mode="browser_fallback",
            fallback_used=True,
            interaction_used=False,
        )


def _should_use_browser_fallback(url: str, html: str, detection: DetectionResult) -> bool:
    if detection.status == "blocked_or_inconclusive":
        return True

    soup = BeautifulSoup(html, "lxml")
    form_count = len(soup.find_all("form"))
    input_count = len(soup.find_all("input"))
    button_count = len(soup.find_all("button"))
    script_count = len(soup.find_all("script"))
    custom_element_count = len(soup.find_all(lambda tag: "-" in tag.name))
    body_text = soup.body.get_text(" ", strip=True) if soup.body else ""

    app_shell = soup.find(id="root") or soup.find(id="app")
    title_text = soup.title.get_text(" ", strip=True).lower() if soup.title else ""
    meta_description = ""
    description_tag = soup.find("meta", attrs={"name": "description"})
    if description_tag and description_tag.get("content"):
        meta_description = description_tag["content"].lower()

    auth_intent = " ".join([url.lower(), title_text, meta_description, body_text.lower()])
    has_auth_intent = any(hint in auth_intent for hint in AUTH_INTENT_HINTS)

    if detection.status == "partial_auth_surface":
        return True

    if form_count == 0 and input_count == 0 and button_count == 0:
        return bool(app_shell or (script_count >= 2 and has_auth_intent) or custom_element_count >= 3)

    return detection.status == "not_found" and has_auth_intent and script_count >= 4
