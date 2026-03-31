from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup

from .auth_shared import BLOCKED_MESSAGE, BLOCKED_TEXT_RE, COMPONENT_PRIORITY, STATUS_PRIORITY, default_message_for_status
from .browser import BrowserMarkupSnapshot, render_html
from .detector import DetectionResult, choose_primary_component, detect_auth_component
from .fetcher import FetchError, InvalidContentTypeError, UpstreamTimeoutError, fetch_html, is_forbidden_fetch_error

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    detection: DetectionResult
    analysis_mode: str
    fallback_used: bool
    interaction_used: bool


async def analyze_url(url: str) -> AnalysisResult:
    analysis_mode = "browser_primary"
    fallback_used = False
    interaction_used = False

    try:
        browser_result = await render_html(url)
        interaction_used = browser_result.interaction_used or browser_result.typing_used
        detection = _select_best_detection(browser_result.snapshots or [_final_snapshot(browser_result.html)])
        logger.info(
            "analysis path evaluated",
            extra={"url": url, "path": "browser_primary", "status": detection.status, "confidence": detection.confidence},
        )
    except (FetchError, UpstreamTimeoutError) as browser_exc:
        fallback_used = True
        logger.info("analysis path evaluated", extra={"url": url, "path": "browser_failed", "error": str(browser_exc)})
        try:
            html = await fetch_html(url)
            detection = detect_auth_component(html)
            analysis_mode = "static_html"
            logger.info(
                "analysis path evaluated",
                extra={"url": url, "path": "static_fallback", "status": detection.status, "confidence": detection.confidence},
            )
        except InvalidContentTypeError:
            raise
        except (FetchError, UpstreamTimeoutError) as fetch_exc:
            blocked_message = BLOCKED_MESSAGE if is_forbidden_fetch_error(fetch_exc) else str(fetch_exc)
            detection = DetectionResult(
                found=False,
                confidence=0.0,
                signals=[],
                snippet=None,
                message=blocked_message,
                status="blocked_or_inconclusive",
                components=[],
            )
            logger.info("analysis path evaluated", extra={"url": url, "path": "static_failed", "error": str(fetch_exc)})

    return AnalysisResult(
        detection=detection,
        analysis_mode=analysis_mode,
        fallback_used=fallback_used,
        interaction_used=interaction_used,
    )


def _final_snapshot(html: str) -> BrowserMarkupSnapshot:
    return BrowserMarkupSnapshot(stage="final", html=html, interaction_used=False, typing_used=False)


def _select_best_detection(snapshots: list[BrowserMarkupSnapshot]) -> DetectionResult:
    evaluated: list[DetectionResult] = []
    best_detection: Optional[DetectionResult] = None
    best_rank: Optional[tuple[int, int, int, float, int]] = None
    best_stage: Optional[str] = None

    for snapshot in snapshots:
        detection = detect_auth_component(snapshot.html)
        evaluated.append(detection)
        rank = _detection_rank(detection)
        logger.info(
            "snapshot evaluated",
            extra={
                "stage": snapshot.stage,
                "status": detection.status,
                "confidence": detection.confidence,
                "rank": rank,
            },
        )
        if best_rank is None or rank > best_rank:
            best_detection = detection
            best_rank = rank
            best_stage = snapshot.stage

    if best_detection is None:
        return DetectionResult(
            found=False,
            confidence=0.0,
            signals=[],
            snippet=None,
            message=default_message_for_status("not_found"),
            status="not_found",
            components=[],
        )

    logger.info(
        "snapshot selection complete",
        extra={
            "winner_stage": best_stage,
            "winner_status": best_detection.status,
            "winner_confidence": best_detection.confidence,
            "winner_primary": choose_primary_component(best_detection.components).type if best_detection.components else None,
        },
    )
    return _merge_detection_components(best_detection, evaluated)


def _merge_detection_components(primary_detection: DetectionResult, detections: list[DetectionResult]) -> DetectionResult:
    merged_components = list(primary_detection.components)
    seen_keys = {_component_key(component) for component in merged_components}

    for detection in detections:
        if detection is primary_detection:
            continue
        for component in detection.components:
            key = _component_key(component)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            merged_components.append(component)

    return DetectionResult(
        found=primary_detection.found,
        confidence=primary_detection.confidence,
        signals=primary_detection.signals,
        snippet=primary_detection.snippet,
        message=_final_detection_message(primary_detection),
        status=primary_detection.status,
        surface_type=primary_detection.surface_type,
        fields=primary_detection.fields,
        actions=primary_detection.actions,
        providers=primary_detection.providers,
        components=merged_components,
        partial_html_markup=primary_detection.partial_html_markup,
    )


def _final_detection_message(detection: DetectionResult) -> str:
    if detection.status == "blocked_or_inconclusive" and (
        "challenge" in " ".join(detection.signals).lower()
        or is_blocked_or_challenged_html(detection.snippet or detection.partial_html_markup or "")
    ):
        return BLOCKED_MESSAGE
    return detection.message


def _component_key(component) -> tuple[str, tuple[str, ...], Optional[str]]:
    return (component.type, tuple(component.providers), component.snippet)


def _detection_rank(detection: DetectionResult) -> tuple[int, int, int, float, int]:
    primary = choose_primary_component(detection.components)
    component_priority = COMPONENT_PRIORITY.get(primary.type, 0) if primary else 0
    auth_control_score = _auth_control_score(detection)
    snippet_length = -(len(detection.snippet or "") or 10_000)
    return (
        STATUS_PRIORITY.get(detection.status, 0),
        component_priority,
        auth_control_score,
        detection.confidence,
        snippet_length,
    )


def _auth_control_score(detection: DetectionResult) -> int:
    field_score = sum(3 for field in detection.fields if field.type == "password")
    field_score += sum(2 for field in detection.fields if field.type in {"email", "username", "phone"})
    action_score = sum(2 for action in detection.actions if action.type == "submit")
    action_score += sum(2 for action in detection.actions if action.type == "provider")
    action_score += sum(1 for action in detection.actions if action.type == "continue")
    signal_score = sum(
        1
        for signal in detection.signals
        if signal in {"password_input", "username_or_email_input", "submit_button", "continue_action", "sso_provider"}
    )
    return field_score + action_score + signal_score


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
    return bool(BLOCKED_TEXT_RE.search(text))
