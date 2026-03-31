from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup

from ..core.config import get_settings
from .browser import render_html
from .detector import DetectionResult, detect_auth_component
from .fetcher import FetchError, InvalidContentTypeError, UpstreamTimeoutError, fetch_html
from .gemini import ai_fallback_available, refine_detection_with_ai, should_use_ai_fallback

AUTH_INTENT_HINTS = ("login", "log in", "sign in", "signin", "account", "authenticate")
STRONG_DETECTION_CONFIDENCE = 0.8
logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    detection: DetectionResult
    analysis_mode: str
    fallback_used: bool
    interaction_used: bool
    ai_used: bool
    ai_refined: bool
    ai_provider: Optional[str]
    ai_model: Optional[str]


async def analyze_url(url: str) -> AnalysisResult:
    analysis_mode = "static"
    fallback_used = False
    interaction_used = False
    screenshot_base64: Optional[str] = None
    analysis_html = ""
    browser_url: Optional[str] = None
    fetch_error: Optional[Exception] = None

    try:
        html = await fetch_html(url)
        analysis_html = html
        detection = detect_auth_component(html)
        logger.info(
            "analysis path evaluated",
            extra={"url": url, "path": "static", "status": detection.status, "confidence": detection.confidence},
        )
    except InvalidContentTypeError:
        raise
    except (FetchError, UpstreamTimeoutError) as exc:
        fetch_error = exc
        detection = DetectionResult(
            found=False,
            confidence=0.0,
            signals=[],
            snippet=None,
            message=str(exc),
            status="blocked_or_inconclusive",
            components=[],
        )
        logger.info("analysis path evaluated", extra={"url": url, "path": "static_failed", "error": str(exc)})

    should_try_browser = fetch_error is not None or _should_use_browser_fallback(url, analysis_html, detection)
    if should_try_browser:
        settings = get_settings()
        if settings.enable_browser_fallback:
            detection, analysis_html, screenshot_base64, interaction_used = await _attempt_browser_detection(url)
            analysis_mode = "browser_fallback"
            fallback_used = True
            browser_url = url

    ai_used = False
    ai_refined = False
    ai_provider = None
    ai_model = None
    if ai_fallback_available() and should_use_ai_fallback(detection, browser_used=fallback_used):
        ai_used = True
        ai_result = await refine_detection_with_ai(
            url=url,
            html=analysis_html,
            detection=detection,
            screenshot_base64=screenshot_base64,
            browser_url=browser_url,
        )
        if ai_result is not None:
            detection = ai_result.detection
            ai_refined = ai_result.refined
            ai_provider = ai_result.provider
            ai_model = ai_result.model

    return AnalysisResult(
        detection=detection,
        analysis_mode=analysis_mode,
        fallback_used=fallback_used,
        interaction_used=interaction_used,
        ai_used=ai_used,
        ai_refined=ai_refined,
        ai_provider=ai_provider,
        ai_model=ai_model,
    )


def _should_use_browser_fallback(url: str, html: str, detection: DetectionResult) -> bool:
    if _is_strong_detection(detection):
        return False

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

    if detection.status == "found":
        return True
    if detection.status == "partial_auth_surface" and detection.confidence < 0.75:
        return True

    if form_count == 0 and input_count == 0 and button_count == 0:
        return bool(app_shell or (script_count >= 2 and has_auth_intent) or custom_element_count >= 3)

    return detection.status == "not_found" and has_auth_intent and script_count >= 4


def _is_strong_detection(detection: DetectionResult) -> bool:
    return detection.status == "found" and detection.confidence >= STRONG_DETECTION_CONFIDENCE


async def _attempt_browser_detection(url: str) -> tuple[DetectionResult, str, Optional[str], bool]:
    try:
        browser_result = await render_html(url)
        interaction_used = browser_result.interaction_used or browser_result.typing_used
        if is_blocked_or_challenged_html(browser_result.html):
            detection = DetectionResult(
                found=False,
                confidence=0.0,
                signals=[],
                snippet=None,
                message="The site presented an anti-bot or access challenge instead of a login surface.",
                status="blocked_or_inconclusive",
                components=[],
            )
            logger.info("analysis path evaluated", extra={"url": url, "path": "browser_failed", "reason": "challenge"})
            return detection, browser_result.html, browser_result.screenshot_base64, interaction_used

        detection = detect_auth_component(browser_result.html)
        if detection.status == "not_found":
            detection.status = "blocked_or_inconclusive"
            detection.message = "Unable to confirm a login surface after browser rendering."
        logger.info(
            "analysis path evaluated",
            extra={"url": url, "path": "browser_fallback", "status": detection.status, "confidence": detection.confidence},
        )
        return detection, browser_result.html, browser_result.screenshot_base64, interaction_used
    except (FetchError, UpstreamTimeoutError) as exc:
        detection = DetectionResult(
            found=False,
            confidence=0.0,
            signals=[],
            snippet=None,
            message=str(exc),
            status="blocked_or_inconclusive",
            components=[],
        )
        logger.info("analysis path evaluated", extra={"url": url, "path": "browser_failed", "error": str(exc)})
        return detection, "", None, False


def is_blocked_or_challenged_html(html: str) -> bool:
    soup = BeautifulSoup(html, "lxml")
    text = " ".join(
        filter(
            None,
            [
                soup.title.get_text(" ", strip=True) if soup.title else "",
                soup.body.get_text(" ", strip=True) if soup.body else "",
            ],
        )
    ).lower()
    return bool(
        re.search(
            r"blocked by network security|access denied|captcha|unusual activity|verify you are human|request blocked",
            text,
        )
    )
