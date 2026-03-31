from __future__ import annotations

import logging
from typing import Optional

from bs4 import BeautifulSoup, Tag

from .auth_shared import (
    AUTH_RE,
    CHALLENGE_RE,
    COMPONENT_PRIORITY,
    PASSWORDLESS_RE,
    PASSWORD_FOLLOWUP_RE,
    PROVIDER_KEYWORDS,
    STATUS_PRIORITY,
    WRAPPER_TOKEN_RE,
    default_message_for_status,
)
from .detection_models import AuthComponent, CandidateAnalysis, CandidateModel, DetectionResult
from .detector_candidate import (
    build_selector_hint,
    build_snippet,
    candidate_descriptor,
    candidate_focus_score,
    candidate_from_tag,
    candidate_size,
    has_auth_bearing_descendant,
    has_visible_passwordless_trigger,
    is_auth_bearing_node,
    is_hidden_element,
    is_noise_container,
    is_smallest_credential_complete_container,
    serialize_partial_markup,
    select_snippet_element,
)

logger = logging.getLogger(__name__)


def detect_auth_component(html: str) -> DetectionResult:
    soup = BeautifulSoup(html, "lxml")
    candidates = _build_candidates(soup)
    logger.info("candidate extraction complete", extra={"candidate_count": len(candidates)})
    if not candidates:
        return _not_found_result()

    analyses = [_analyze_candidate(candidate) for candidate in candidates]
    for analysis in analyses:
        logger.info(
            "candidate analyzed",
            extra={
                "candidate": candidate_descriptor(analysis.candidate),
                "status": analysis.status,
                "score": analysis.score,
                "confidence": analysis.confidence,
                "signals": analysis.signals,
            },
        )

    component_analyses = [analysis for analysis in analyses if analysis.status != "not_found"]
    component_analyses.sort(key=_analysis_sort_key, reverse=True)
    best = component_analyses[0] if component_analyses else sorted(analyses, key=_analysis_sort_key, reverse=True)[0]

    if best.status == "not_found":
        return DetectionResult(
            found=False,
            confidence=0.0,
            signals=best.signals,
            snippet=None,
            message=default_message_for_status("not_found"),
            status="not_found",
            components=[],
        )

    components = _dedupe_components([_component_from_analysis(item) for item in component_analyses[:5]])
    primary = choose_primary_component(components)
    logger.info(
        "candidate selection complete",
        extra={
            "winner": candidate_descriptor(best.candidate),
            "winner_status": best.status,
            "winner_score": best.score,
            "primary_type": primary.type if primary else None,
        },
    )

    partial_html_markup = None
    if best.status == "partial_auth_surface":
        raw = serialize_partial_markup(best.candidate)
        primary_snippet = primary.snippet if primary else best.snippet
        if raw and raw != primary_snippet:
            partial_html_markup = raw

    return DetectionResult(
        found=best.status in {"found", "partial_auth_surface"},
        confidence=primary.confidence if primary else best.confidence,
        signals=primary.signals if primary else best.signals,
        snippet=primary.snippet if primary else best.snippet,
        message=best.message,
        status=best.status,
        surface_type=primary.surface_type if primary else best.surface_type,
        fields=primary.fields if primary else best.candidate.fields,
        actions=best.candidate.actions,
        providers=primary.providers if primary else best.candidate.providers,
        components=components,
        partial_html_markup=partial_html_markup,
    )


def choose_primary_component(components: list[AuthComponent]) -> Optional[AuthComponent]:
    if not components:
        return None
    return sorted(
        components,
        key=lambda component: (COMPONENT_PRIORITY.get(component.type, 0), component.confidence),
        reverse=True,
    )[0]


def _not_found_result() -> DetectionResult:
    return DetectionResult(
        found=False,
        confidence=0.0,
        signals=[],
        snippet=None,
        message=default_message_for_status("not_found"),
        status="not_found",
        components=[],
    )


def _build_candidates(soup: BeautifulSoup) -> list[CandidateModel]:
    seen: set[int] = set()
    candidates: list[CandidateModel] = []
    for element in soup.find_all(["form", "dialog", "section", "div", "aside", "main", "article"]):
        if not isinstance(element, Tag):
            continue
        candidate = candidate_from_tag(element)
        if not _is_candidate_element(candidate):
            continue
        if id(element) in seen:
            continue
        seen.add(id(element))
        candidates.append(candidate)

    for element in soup.find_all(lambda tag: isinstance(tag, Tag) and "-" in tag.name):
        candidate = candidate_from_tag(element)
        if id(element) in seen or not _is_candidate_element(candidate):
            continue
        seen.add(id(element))
        candidates.append(candidate)

    return _dedupe_candidates(candidates)


def _dedupe_candidates(candidates: list[CandidateModel]) -> list[CandidateModel]:
    deduped: list[CandidateModel] = []
    for candidate in sorted(candidates, key=lambda item: (candidate_size(item), 0 if item.element.name == "form" else 1)):
        replaced = False
        for index, kept in enumerate(deduped):
            if _same_surface(candidate, kept):
                if candidate_focus_score(candidate) > candidate_focus_score(kept):
                    deduped[index] = candidate
                replaced = True
                break
        if not replaced:
            deduped.append(candidate)
    return deduped


def _same_surface(first: CandidateModel, second: CandidateModel) -> bool:
    if first.element in second.element.descendants or second.element in first.element.descendants:
        first_form = first.element if first.element.name == "form" else first.element.find("form")
        second_form = second.element if second.element.name == "form" else second.element.find("form")
        if first_form and second_form:
            return first_form.prettify(formatter="minimal") == second_form.prettify(formatter="minimal")
        return select_snippet_element(first).prettify(formatter="minimal") == select_snippet_element(second).prettify(
            formatter="minimal"
        )
    return False


def _is_candidate_element(candidate: CandidateModel) -> bool:
    element = candidate.element
    if is_hidden_element(element) or is_noise_container(element):
        return False
    if element.name == "form":
        return bool(candidate.fields or candidate.actions or AUTH_RE.search(candidate.text_blob) or PASSWORDLESS_RE.search(candidate.text_blob))
    if element.find("input", attrs={"type": "password"}):
        return True
    if element.find("input", attrs={"type": "email"}):
        return True
    if PASSWORDLESS_RE.search(candidate.text_blob) or CHALLENGE_RE.search(candidate.text_blob):
        return True
    if any(provider in candidate.text_blob for provider in PROVIDER_KEYWORDS) and (
        "continue with" in candidate.text_blob or "sign in with" in candidate.text_blob
    ):
        return True
    return bool(AUTH_RE.search(candidate.text_blob) or PASSWORD_FOLLOWUP_RE.search(candidate.text_blob))


def _analyze_candidate(candidate: CandidateModel) -> CandidateAnalysis:
    rejection_reason = _candidate_rejection_reason(candidate)
    if rejection_reason:
        return CandidateAnalysis(
            candidate=candidate,
            status="not_found",
            component_type="unknown_auth_surface",
            surface_type="auth_surface",
            confidence=0.0,
            score=-10,
            signals=[rejection_reason],
            snippet="",
            message=default_message_for_status("not_found"),
            selector_hint=None,
        )

    status, score, matched_signals = _classify_candidate(candidate)
    return CandidateAnalysis(
        candidate=candidate,
        status=status,
        component_type=_component_type_for(candidate, status),
        surface_type=_surface_type_for(candidate),
        confidence=_confidence_for(status, score),
        score=score,
        signals=matched_signals,
        snippet=build_snippet(candidate),
        message=default_message_for_status(status),
        selector_hint=build_selector_hint(candidate),
    )


def _candidate_rejection_reason(candidate: CandidateModel) -> Optional[str]:
    signals = candidate.signals
    strong_controls = signals.has_password or signals.has_identity or signals.providers or signals.has_continue or signals.has_submit
    if is_hidden_element(candidate.element):
        return "hard_rejected_hidden"
    if is_noise_container(candidate.element):
        return "hard_rejected_non_auth"
    if (
        candidate.element.name not in {"form", "dialog"}
        and candidate.element.get("role") != "dialog"
        and has_auth_bearing_descendant(candidate)
        and not is_smallest_credential_complete_container(candidate)
    ):
        return "hard_rejected_non_auth"
    if signals.meaningful_field_types == {"otp"} and not signals.has_passwordless:
        return "hard_rejected_non_auth"
    if signals.has_negative and not strong_controls:
        return "hard_rejected_non_auth"
    if signals.has_secondary and not (signals.has_password or signals.providers or signals.has_password_followup):
        return "hard_rejected_non_auth"
    if candidate.element.name == "form" and not strong_controls and not signals.has_auth_text and not signals.has_challenge:
        return "hard_rejected_non_auth"
    if signals.has_password and signals.has_identity and (signals.has_submit or signals.has_continue):
        return None
    if (
        candidate.element.name != "form"
        and not strong_controls
        and not signals.has_auth_text
        and not signals.has_passwordless
        and not signals.has_challenge
    ):
        return "hard_rejected_non_auth"
    return None


def _classify_candidate(candidate: CandidateModel) -> tuple[str, int, list[str]]:
    signals = candidate.signals
    matched: list[str] = []
    score = 0

    if signals.has_password:
        score += 6
        matched.append("password_input")
    if signals.has_identity:
        score += 3
        matched.append("username_or_email_input")
    if signals.has_submit:
        score += 2
        matched.append("submit_button")
    if signals.has_continue:
        score += 2
        matched.append("continue_action")
    if signals.providers:
        score += 4
        matched.append("sso_provider")
    if signals.has_passwordless:
        score += 3
        matched.append("passwordless_signal")
    if signals.has_password_followup:
        score += 2
        matched.append("password_followup")
    if signals.has_auth_text:
        score += 1
        matched.append("auth_keyword")
    if signals.has_identity and signals.has_auth_text:
        score += 1
        matched.append("identity_auth_pair")
    if signals.has_secondary:
        score -= 2
        matched.append("secondary_auth_surface")
    if signals.has_challenge:
        score -= 3
        matched.append("challenge_surface")
    if signals.has_negative:
        score -= 4
        matched.append("negative_context")

    strong_traditional = (
        signals.has_password
        and (signals.has_identity or signals.has_submit or signals.has_auth_text)
        and not _is_broad_wrapper_with_nested_form(candidate)
    )
    email_first = signals.has_identity and (signals.has_continue or signals.has_password_followup or signals.has_auth_text)
    oauth = bool(signals.providers)
    passwordless = signals.has_passwordless and (
        signals.has_continue or signals.has_auth_text or signals.has_identity or bool(signals.actions)
    )

    if signals.has_challenge and not (strong_traditional or oauth or email_first or passwordless):
        return "blocked_or_inconclusive", max(score, 1), matched
    if strong_traditional:
        return "found", max(score, 4), matched
    if oauth or email_first or passwordless:
        return "partial_auth_surface", max(score, 2), matched
    return "not_found", score, matched


def _component_type_for(candidate: CandidateModel, status: str) -> str:
    signals = candidate.signals
    if status == "blocked_or_inconclusive":
        return "challenge"
    if signals.has_password:
        return "traditional"
    if signals.providers:
        return "oauth"
    if signals.has_passwordless and not signals.has_password_followup:
        return "passwordless"
    if signals.has_identity and (signals.has_continue or signals.has_password_followup):
        return "multi_step"
    return "unknown_auth_surface"


def _surface_type_for(candidate: CandidateModel) -> str:
    element = candidate.element
    classes = " ".join(element.get("class", [])).lower()
    signals = candidate.signals
    if element.name == "dialog" or element.get("role") == "dialog" or element.get("aria-modal") == "true":
        return "dialog"
    if any(token in classes for token in ("drawer", "sheet", "flyout", "sidebar")):
        return "drawer"
    if signals.providers and not signals.has_password and not signals.has_identity:
        return "sso_only"
    if signals.has_identity and not signals.has_password and (signals.has_continue or signals.has_password_followup):
        return "multi_step"
    if signals.has_passwordless:
        return "passwordless"
    if element.name in {"main", "article"} or WRAPPER_TOKEN_RE.search(classes):
        return "auth_shell"
    if element.name == "form":
        return "form"
    return "auth_surface"


def _confidence_for(status: str, score: int) -> float:
    if status == "found":
        return round(min(score / 10.0, 1.0), 2)
    if status == "partial_auth_surface":
        return round(min(score / 8.0, 0.89), 2)
    if status == "blocked_or_inconclusive":
        return 0.35
    return 0.0


def _analysis_sort_key(analysis: CandidateAnalysis) -> tuple[int, int, float, int, int]:
    snippet_size = -(len(analysis.snippet or "") or 10_000)
    return (
        STATUS_PRIORITY.get(analysis.status, 0),
        COMPONENT_PRIORITY.get(analysis.component_type, 0),
        analysis.confidence,
        candidate_focus_score(analysis.candidate),
        snippet_size,
    )


def _component_from_analysis(analysis: CandidateAnalysis) -> AuthComponent:
    return AuthComponent(
        type=analysis.component_type,
        surface_type=analysis.surface_type,
        confidence=analysis.confidence,
        selector_hint=analysis.selector_hint,
        signals=analysis.signals,
        providers=analysis.candidate.providers,
        fields=analysis.candidate.fields,
        snippet=analysis.snippet,
        summary=analysis.message,
    )


def _dedupe_components(components: list[AuthComponent]) -> list[AuthComponent]:
    deduped: list[AuthComponent] = []
    seen: set[tuple[str, tuple[str, ...], Optional[str]]] = set()
    for component in components:
        key = (component.type, tuple(component.providers), component.snippet)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(component)
    return deduped


def _is_broad_wrapper_with_nested_form(candidate: CandidateModel) -> bool:
    if candidate.element.name == "form":
        return False
    if candidate.element.get("role") == "dialog" or candidate.element.name == "dialog":
        return False
    return candidate.element.find("form") is not None


__all__ = [
    "AuthComponent",
    "DetectionResult",
    "detect_auth_component",
    "choose_primary_component",
]
