from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from bs4 import BeautifulSoup, Tag

from ..core.config import get_settings

AUTH_RE = re.compile(
    r"\b(log ?in|sign ?in|signin|authentication|auth|account access|member login|continue with email|use email|continue as|continue shopping|verify mobile number)\b",
    re.IGNORECASE,
)
PASSWORD_RE = re.compile(r"\b(password|passcode)\b", re.IGNORECASE)
CONTINUE_RE = re.compile(r"\b(continue|next|proceed|verify|use email|email me a link|request otp|send code)\b", re.IGNORECASE)
SUBMIT_RE = re.compile(r"\b(log ?in|sign ?in|submit|continue|next|request otp|send code)\b", re.IGNORECASE)
PASSWORDLESS_RE = re.compile(
    r"\b(passkey|magic link|email me a link|webauthn|verification code|one-time code|one time code|otp|one-time password)\b",
    re.IGNORECASE,
)
CHALLENGE_RE = re.compile(
    r"\b(captcha|verify you are human|access denied|request blocked|unusual activity|checkpoint)\b",
    re.IGNORECASE,
)
SECONDARY_RE = re.compile(r"\b(forgot password|reset password|recovery code|recover account)\b", re.IGNORECASE)
NEGATIVE_RE = re.compile(r"\b(search|newsletter|subscribe|coupon|promo|contact|feedback|comment|cart)\b", re.IGNORECASE)
PASSWORD_FOLLOWUP_RE = re.compile(r"\b(sign in with password|use password|password instead)\b", re.IGNORECASE)
HIDDEN_TOKEN_RE = re.compile(r"(^|[\s:_-])(hidden|sr-only|visually-hidden)($|[\s:_-])", re.IGNORECASE)
NOISE_TOKEN_RE = re.compile(r"\b(flash|alert|notice|banner|toast|message|template)\b", re.IGNORECASE)
WRAPPER_TOKEN_RE = re.compile(r"\b(wrapper|container|layout|shell|page|root|main|content)\b", re.IGNORECASE)
METADATA_INPUT_RE = re.compile(
    r"\b(authenticity_token|csrf|timestamp|timestamp_secret|return_to|allow_signup|client_id|integration|required_field_)\b",
    re.IGNORECASE,
)

USERNAME_KEYWORDS = ("user", "username", "email", "login", "identifier", "member id")
PROVIDER_KEYWORDS = (
    "google",
    "apple",
    "facebook",
    "github",
    "linkedin",
    "microsoft",
    "twitter",
    "x",
    "discord",
    "slack",
    "amazon",
)
PARTIAL_MARKUP_MAX_CHARS = 5000

logger = logging.getLogger(__name__)


@dataclass
class ExtractedField:
    type: str
    label: Optional[str] = None
    name: Optional[str] = None
    selector_hint: Optional[str] = None
    required: bool = False


@dataclass
class ExtractedAction:
    type: str
    label: str
    provider: Optional[str] = None
    selector_hint: Optional[str] = None


@dataclass
class AuthComponent:
    type: str
    surface_type: Optional[str]
    confidence: float
    selector_hint: Optional[str]
    signals: list[str]
    providers: list[str]
    fields: list[ExtractedField]
    snippet: Optional[str]
    summary: str


@dataclass
class DetectionResult:
    found: bool
    confidence: float
    signals: list[str]
    snippet: Optional[str]
    message: str
    status: str = "not_found"
    surface_type: Optional[str] = None
    fields: list[ExtractedField] = field(default_factory=list)
    actions: list[ExtractedAction] = field(default_factory=list)
    providers: list[str] = field(default_factory=list)
    components: list[AuthComponent] = field(default_factory=list)
    partial_html_markup: Optional[str] = None


@dataclass
class _CandidateSignals:
    text_blob: str
    fields: list[ExtractedField]
    actions: list[ExtractedAction]
    providers: list[str]
    has_password: bool
    has_identity: bool
    has_submit: bool
    has_continue: bool
    has_passwordless: bool
    has_challenge: bool
    has_secondary: bool
    has_negative: bool
    has_auth_text: bool
    has_password_followup: bool
    meaningful_field_types: set[str]


@dataclass
class _CandidateAnalysis:
    element: Tag
    status: str
    component_type: str
    surface_type: str
    confidence: float
    score: int
    signals: list[str]
    fields: list[ExtractedField]
    actions: list[ExtractedAction]
    providers: list[str]
    snippet: str
    message: str
    selector_hint: Optional[str]


def detect_auth_component(html: str) -> DetectionResult:
    soup = BeautifulSoup(html, "lxml")
    candidates = _build_candidates(soup)
    logger.info("candidate extraction complete", extra={"candidate_count": len(candidates)})
    if not candidates:
        return DetectionResult(
            found=False,
            confidence=0.0,
            signals=[],
            snippet=None,
            message="Authentication component not found.",
            status="not_found",
            components=[],
        )

    analyses = [_analyze_candidate(candidate) for candidate in candidates]
    for analysis in analyses:
        logger.info(
            "candidate analyzed",
            extra={
                "candidate": _candidate_descriptor(analysis.element),
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
            message="Authentication component not found.",
            status="not_found",
            components=[],
        )

    components = _dedupe_components([_component_from_analysis(item) for item in component_analyses[:5]])
    primary = choose_primary_component(components)
    logger.info(
        "candidate selection complete",
        extra={
            "winner": _candidate_descriptor(best.element),
            "winner_status": best.status,
            "winner_score": best.score,
            "primary_type": primary.type if primary else None,
        },
    )

    partial_html_markup = None
    if best.status == "partial_auth_surface":
        raw = _serialize_partial_markup(best.element)
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
        fields=primary.fields if primary else best.fields,
        actions=best.actions,
        providers=primary.providers if primary else best.providers,
        components=components,
        partial_html_markup=partial_html_markup,
    )


def choose_primary_component(components: list[AuthComponent]) -> Optional[AuthComponent]:
    if not components:
        return None
    priority = {
        "traditional": 0,
        "multi_step": 1,
        "oauth": 2,
        "passwordless": 3,
        "challenge": 4,
        "unknown_auth_surface": 5,
    }
    return sorted(components, key=lambda component: (priority.get(component.type, 99), -component.confidence))[0]


def _build_candidates(soup: BeautifulSoup) -> list[Tag]:
    seen: set[int] = set()
    candidates: list[Tag] = []
    for element in soup.find_all(["form", "dialog", "section", "div", "aside", "main", "article"]):
        if not isinstance(element, Tag) or not _is_candidate_element(element):
            continue
        if id(element) in seen:
            continue
        seen.add(id(element))
        candidates.append(element)

    for element in soup.find_all(lambda tag: isinstance(tag, Tag) and "-" in tag.name):
        if id(element) in seen or not _is_candidate_element(element):
            continue
        seen.add(id(element))
        candidates.append(element)

    return _dedupe_candidates(candidates)


def _dedupe_candidates(candidates: list[Tag]) -> list[Tag]:
    deduped: list[Tag] = []
    for candidate in sorted(candidates, key=lambda element: (_candidate_size(element), 0 if element.name == "form" else 1)):
        replaced = False
        for index, kept in enumerate(deduped):
            if _same_surface(candidate, kept):
                if _candidate_focus_score(candidate) > _candidate_focus_score(kept):
                    deduped[index] = candidate
                replaced = True
                break
        if not replaced:
            deduped.append(candidate)
    return deduped


def _same_surface(first: Tag, second: Tag) -> bool:
    if first in second.descendants or second in first.descendants:
        first_form = first if first.name == "form" else first.find("form")
        second_form = second if second.name == "form" else second.find("form")
        if first_form and second_form:
            return first_form.prettify(formatter="minimal") == second_form.prettify(formatter="minimal")
        first_focus = _select_snippet_element(first)
        second_focus = _select_snippet_element(second)
        return first_focus.prettify(formatter="minimal") == second_focus.prettify(formatter="minimal")
    return False


def _is_candidate_element(element: Tag) -> bool:
    if _is_hidden_element(element) or _is_noise_container(element):
        return False
    text_blob = _element_text_blob(element)
    if element.name == "form":
        return bool(_extract_fields(element) or _extract_actions(element) or AUTH_RE.search(text_blob) or PASSWORDLESS_RE.search(text_blob))
    if element.find("input", attrs={"type": "password"}):
        return True
    if element.find("input", attrs={"type": "email"}):
        return True
    if PASSWORDLESS_RE.search(text_blob) or CHALLENGE_RE.search(text_blob):
        return True
    if any(provider in text_blob for provider in PROVIDER_KEYWORDS) and ("continue with" in text_blob or "sign in with" in text_blob):
        return True
    return bool(AUTH_RE.search(text_blob) or PASSWORD_FOLLOWUP_RE.search(text_blob))


def _analyze_candidate(element: Tag) -> _CandidateAnalysis:
    signals = _collect_signals(element)
    rejection_reason = _candidate_rejection_reason(element, signals)
    if rejection_reason:
        return _CandidateAnalysis(
            element=element,
            status="not_found",
            component_type="unknown_auth_surface",
            surface_type="auth_surface",
            confidence=0.0,
            score=-10,
            signals=[rejection_reason],
            fields=signals.fields,
            actions=signals.actions,
            providers=signals.providers,
            snippet="",
            message="Authentication component not found.",
            selector_hint=None,
        )

    status, score, matched_signals = _classify_candidate(element, signals)
    component_type = _component_type_for(signals, status)
    surface_type = _surface_type_for(element, signals)
    confidence = _confidence_for(status, score)
    message = _message_for(status)
    snippet = _build_snippet(element)

    return _CandidateAnalysis(
        element=element,
        status=status,
        component_type=component_type,
        surface_type=surface_type,
        confidence=confidence,
        score=score,
        signals=matched_signals,
        fields=signals.fields,
        actions=signals.actions,
        providers=signals.providers,
        snippet=snippet,
        message=message,
        selector_hint=_build_selector_hint(element, signals.fields, signals.actions),
    )


def _collect_signals(element: Tag) -> _CandidateSignals:
    fields = _extract_fields(element)
    actions = _extract_actions(element)
    providers = _extract_sso_providers(element, actions)
    meaningful_field_types = {field.type for field in fields if field.type != "unknown"}
    text_blob = _element_text_blob(element)
    return _CandidateSignals(
        text_blob=text_blob,
        fields=fields,
        actions=actions,
        providers=providers,
        has_password="password" in meaningful_field_types,
        has_identity=bool({"email", "username", "phone"} & meaningful_field_types),
        has_submit=any(action.type == "submit" for action in actions),
        has_continue=any(action.type == "continue" for action in actions),
        has_passwordless=bool(PASSWORDLESS_RE.search(text_blob)),
        has_challenge=bool(CHALLENGE_RE.search(text_blob)),
        has_secondary=bool(SECONDARY_RE.search(text_blob)),
        has_negative=bool(NEGATIVE_RE.search(text_blob)),
        has_auth_text=bool(AUTH_RE.search(text_blob) or PASSWORD_RE.search(text_blob)),
        has_password_followup=bool(PASSWORD_FOLLOWUP_RE.search(text_blob)),
        meaningful_field_types=meaningful_field_types,
    )


def _candidate_rejection_reason(element: Tag, signals: _CandidateSignals) -> Optional[str]:
    strong_controls = signals.has_password or signals.has_identity or signals.providers or signals.has_continue or signals.has_submit
    if _is_hidden_element(element):
        return "hard_rejected_hidden"
    if _is_noise_container(element):
        return "hard_rejected_non_auth"
    if element.name not in {"form", "dialog"} and element.get("role") != "dialog" and _has_auth_bearing_descendant(element):
        return "hard_rejected_non_auth"
    if signals.meaningful_field_types == {"otp"} and not signals.has_passwordless:
        return "hard_rejected_non_auth"
    if signals.has_negative and not strong_controls:
        return "hard_rejected_non_auth"
    if signals.has_secondary and not (signals.has_password or signals.providers or signals.has_password_followup):
        return "hard_rejected_non_auth"
    if element.name == "form" and not strong_controls and not signals.has_auth_text and not signals.has_challenge:
        return "hard_rejected_non_auth"
    if element.name != "form" and not strong_controls and not signals.has_auth_text and not signals.has_passwordless and not signals.has_challenge:
        return "hard_rejected_non_auth"
    return None


def _classify_candidate(element: Tag, signals: _CandidateSignals) -> tuple[str, int, list[str]]:
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
        and not _is_broad_wrapper_with_nested_form(element)
    )
    email_first = signals.has_identity and (signals.has_continue or signals.has_password_followup or signals.has_auth_text)
    oauth = bool(signals.providers)
    passwordless = signals.has_passwordless and (signals.has_continue or signals.has_auth_text or signals.has_identity or bool(signals.actions))

    if signals.has_challenge and not (strong_traditional or oauth or email_first or passwordless):
        return "blocked_or_inconclusive", max(score, 1), matched
    if strong_traditional:
        return "found", max(score, 4), matched
    if oauth or email_first or passwordless:
        return "partial_auth_surface", max(score, 2), matched
    return "not_found", score, matched


def _component_type_for(signals: _CandidateSignals, status: str) -> str:
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


def _surface_type_for(element: Tag, signals: _CandidateSignals) -> str:
    classes = " ".join(element.get("class", [])).lower()
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


def _message_for(status: str) -> str:
    return {
        "found": "Authentication component detected.",
        "partial_auth_surface": "Partial authentication surface detected.",
        "blocked_or_inconclusive": "The page appears to show a challenge or blocked auth surface.",
        "not_found": "Authentication component not found.",
    }[status]


def _analysis_sort_key(analysis: _CandidateAnalysis) -> tuple[int, int, float, int, int]:
    status_priority = {"found": 3, "partial_auth_surface": 2, "blocked_or_inconclusive": 1, "not_found": 0}
    component_priority = {
        "traditional": 4,
        "multi_step": 3,
        "oauth": 2,
        "passwordless": 2,
        "challenge": 1,
        "unknown_auth_surface": 0,
    }
    snippet_size = -(len(analysis.snippet or "") or 10_000)
    return (
        status_priority.get(analysis.status, 0),
        component_priority.get(analysis.component_type, 0),
        analysis.confidence,
        _candidate_focus_score(analysis.element),
        snippet_size,
    )


def _component_from_analysis(analysis: _CandidateAnalysis) -> AuthComponent:
    return AuthComponent(
        type=analysis.component_type,
        surface_type=analysis.surface_type,
        confidence=analysis.confidence,
        selector_hint=analysis.selector_hint,
        signals=analysis.signals,
        providers=analysis.providers,
        fields=analysis.fields,
        snippet=analysis.snippet,
        summary=analysis.message,
    )


def _extract_fields(element: Tag) -> list[ExtractedField]:
    fields: list[ExtractedField] = []
    for input_tag in element.find_all(["input", "textarea"]):
        if _is_hidden_input(input_tag):
            continue
        field_type = _classify_input(input_tag)
        if field_type == "hidden":
            continue
        fields.append(
            ExtractedField(
                type=field_type,
                label=_extract_label(input_tag),
                name=input_tag.get("name") or input_tag.get("id"),
                selector_hint=input_tag.get("name") or input_tag.get("id") or input_tag.get("placeholder"),
                required=input_tag.has_attr("required") or input_tag.get("aria-required") == "true",
            )
        )
    return _unique_fields(fields)


def _extract_actions(element: Tag) -> list[ExtractedAction]:
    actions: list[ExtractedAction] = []
    for action_tag in element.find_all(["button", "input", "a"]):
        if _is_hidden_element(action_tag):
            continue
        label = " ".join(
            filter(
                None,
                [
                    action_tag.get("value"),
                    action_tag.get("aria-label"),
                    action_tag.get_text(" ", strip=True),
                ],
            )
        ).strip()
        if not label:
            continue
        lowered = label.lower()
        provider = next((item.title() for item in PROVIDER_KEYWORDS if re.search(rf"\b{re.escape(item)}\b", lowered)), None)
        action_type = "action"
        if provider:
            action_type = "provider"
        elif CONTINUE_RE.search(lowered):
            action_type = "continue"
        elif SUBMIT_RE.search(lowered):
            action_type = "submit"
        actions.append(
            ExtractedAction(
                type=action_type,
                label=label,
                provider=provider,
                selector_hint=action_tag.get("id") or action_tag.get("name") or label,
            )
        )
    return _unique_actions(actions)


def _extract_sso_providers(element: Tag, actions: Optional[list[ExtractedAction]] = None) -> list[str]:
    action_providers = [action.provider for action in (actions or []) if action.provider]
    if action_providers:
        return sorted(set(action_providers))
    haystack = _element_text_blob(element)
    providers = [provider.title() for provider in PROVIDER_KEYWORDS if re.search(rf"\b{re.escape(provider)}\b", haystack)]
    return sorted(set(providers))


def _classify_input(input_tag: Tag) -> str:
    input_type = (input_tag.get("type") or "text").lower()
    descriptor = " ".join(
        filter(
            None,
            [
                input_type,
                input_tag.get("name"),
                input_tag.get("id"),
                input_tag.get("placeholder"),
                input_tag.get("autocomplete"),
                input_tag.get("aria-label"),
                input_tag.get("data-testid"),
                input_tag.get("inputmode"),
            ],
        )
    ).lower()

    if input_type == "hidden":
        return "hidden"
    if input_type == "password":
        return "password"
    if "otp" in descriptor or "verification code" in descriptor or "one-time" in descriptor:
        return "otp"
    if input_type == "email" or "email" in descriptor:
        return "email"
    if input_type == "tel" or "phone" in descriptor:
        return "phone"
    if any(keyword in descriptor for keyword in USERNAME_KEYWORDS):
        return "username"
    return "unknown"


def _extract_label(input_tag: Tag) -> Optional[str]:
    if input_tag.get("aria-label"):
        return input_tag.get("aria-label")
    if input_tag.get("placeholder"):
        return input_tag.get("placeholder")
    input_id = input_tag.get("id")
    if input_id and input_tag.find_parent():
        label = input_tag.find_parent().find("label", attrs={"for": input_id})
        if label:
            return label.get_text(" ", strip=True)
    parent_label = input_tag.find_parent("label")
    if parent_label:
        return parent_label.get_text(" ", strip=True)
    return None


def _element_text_blob(element: Tag) -> str:
    texts = [_visible_text(element)]
    for attr in ("id", "class", "name", "aria-label", "data-testid", "placeholder", "title"):
        value = element.get(attr)
        if isinstance(value, list):
            texts.append(" ".join(value))
        elif value:
            texts.append(str(value))
    return " ".join(texts).lower()


def _element_attr_blob(element: Tag) -> str:
    texts = []
    for attr in ("id", "class", "name", "aria-label", "data-testid", "title", "style"):
        value = element.get(attr)
        if isinstance(value, list):
            texts.append(" ".join(str(item) for item in value))
        elif value:
            texts.append(str(value))
    return " ".join(texts).lower()


def _is_hidden_element(element: Tag) -> bool:
    if not isinstance(element, Tag):
        return False
    if element.has_attr("hidden"):
        return True
    if str(element.get("aria-hidden", "")).lower() == "true":
        return True
    style = str(element.get("style", "")).replace(" ", "").lower()
    if "display:none" in style or "visibility:hidden" in style:
        return True
    return bool(HIDDEN_TOKEN_RE.search(_element_attr_blob(element)))


def _is_hidden_input(input_tag: Tag) -> bool:
    if (input_tag.get("type") or "").lower() == "hidden" or _is_hidden_element(input_tag):
        return True
    identifier = " ".join(filter(None, [input_tag.get("name"), input_tag.get("id"), input_tag.get("autocomplete")]))
    return bool(METADATA_INPUT_RE.search(identifier))


def _candidate_size(element: Tag) -> int:
    return len(element.prettify(formatter="minimal"))


def _candidate_focus_score(element: Tag) -> int:
    score = 0
    text_blob = _element_text_blob(element)
    nested_forms = len(element.find_all("form"))
    visible_actions = len(_extract_actions(element))
    visible_fields = len(_extract_fields(element))
    child_auth_units = len(
        [
            child
            for child in element.find_all(["form", "section", "div", "dialog", "aside"], recursive=False)
            if not _is_hidden_element(child) and not _is_noise_container(child) and _is_auth_bearing_node(child)
        ]
    )
    if element.name == "form":
        score += 4
    if element.find("input", attrs={"type": "password"}):
        score += 5
    if element.find("input", attrs={"type": "email"}):
        score += 3
    if visible_fields:
        score += min(visible_fields, 3)
    if visible_actions:
        score += min(visible_actions, 3)
    if PASSWORD_FOLLOWUP_RE.search(text_blob):
        score += 2
    if any(provider in text_blob for provider in PROVIDER_KEYWORDS):
        score += 2
    if "passkey" in text_blob or "webauthn" in text_blob or "magic link" in text_blob:
        score += 2
    if element.name != "form" and nested_forms:
        score -= min(nested_forms * 3, 9)
    if element.name != "form" and child_auth_units:
        score -= min(child_auth_units * 2, 6)
    if element.name != "form" and WRAPPER_TOKEN_RE.search(_element_attr_blob(element)):
        score -= 2
    score -= min(_candidate_size(element) // 1500, 4)
    return score


def _build_snippet(element: Tag) -> str:
    snippet_element = _select_snippet_element(element)
    snippet = snippet_element.prettify(formatter="minimal").strip()
    if len(snippet) <= get_settings().max_snippet_length:
        return snippet
    truncated = snippet[: get_settings().max_snippet_length - 3].rstrip()
    last_newline = truncated.rfind("\n")
    if last_newline > 0:
        truncated = truncated[:last_newline].rstrip()
    return truncated + "\n..."


def _select_snippet_element(element: Tag) -> Tag:
    descendants = [
        node
        for node in element.find_all(["form", "section", "div", "dialog", "aside", "main", "article"], recursive=True)
        if node is not element and not _is_hidden_element(node) and not _is_noise_container(node) and _is_auth_bearing_node(node)
    ]
    if not descendants:
        return element
    selected = sorted(descendants, key=lambda node: (-_candidate_focus_score(node), _candidate_size(node)))[0]
    logger.info(
        "snippet focus selected",
        extra={
            "candidate": _candidate_descriptor(element),
            "selected": _candidate_descriptor(selected),
            "selected_size": _candidate_size(selected),
        },
    )
    return selected


def _is_auth_bearing_node(element: Tag) -> bool:
    signals = _collect_signals(element)
    if signals.has_password and (signals.has_identity or signals.has_submit or signals.has_auth_text):
        return True
    if signals.providers and any(action.type == "provider" for action in signals.actions):
        return True
    if signals.has_passwordless and _has_visible_passwordless_trigger(signals):
        return True
    if signals.has_identity and (signals.has_continue or signals.has_password_followup):
        return True
    return False


def _serialize_partial_markup(element: Tag) -> str:
    raw = element.prettify(formatter="minimal").strip()
    if len(raw) > PARTIAL_MARKUP_MAX_CHARS:
        truncated = raw[: PARTIAL_MARKUP_MAX_CHARS - 3].rstrip()
        last_newline = truncated.rfind("\n")
        if last_newline > 0:
            truncated = truncated[:last_newline].rstrip()
        raw = truncated + "\n..."
    return raw


def _build_selector_hint(element: Tag, fields: list[ExtractedField], actions: list[ExtractedAction]) -> Optional[str]:
    if element.name == "form":
        if element.get("id"):
            return f"form#{element.get('id')}"
        return "form"
    if element.get("id"):
        return f"#{element.get('id')}"
    if fields and fields[0].selector_hint and " " not in fields[0].selector_hint:
        hint = fields[0].selector_hint
        return f"input[name='{hint}'], input[id='{hint}']"
    if actions and actions[0].selector_hint:
        return actions[0].selector_hint
    return None


def _unique_fields(fields: list[ExtractedField]) -> list[ExtractedField]:
    unique: list[ExtractedField] = []
    seen: set[tuple[str, Optional[str], Optional[str]]] = set()
    for field in fields:
        key = (field.type, field.label, field.name)
        if key in seen:
            continue
        seen.add(key)
        unique.append(field)
    return unique


def _unique_actions(actions: list[ExtractedAction]) -> list[ExtractedAction]:
    unique: list[ExtractedAction] = []
    seen: set[tuple[str, str, Optional[str]]] = set()
    for action in actions:
        key = (action.type, action.label, action.provider)
        if key in seen:
            continue
        seen.add(key)
        unique.append(action)
    return unique


def _candidate_descriptor(element: Tag) -> str:
    identifier = element.get("id") or element.get("data-testid")
    if identifier:
        return f"{element.name}#{identifier}"
    classes = ".".join(element.get("class", [])[:2])
    return f"{element.name}.{classes}" if classes else element.name


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


def _visible_text(element: Tag) -> str:
    texts: list[str] = []
    for node in element.descendants:
        if isinstance(node, Tag):
            if node.name in {"script", "style", "template"}:
                continue
            if _is_hidden_element(node) or _is_noise_container(node):
                continue
        elif getattr(node, "strip", None):
            parent = getattr(node, "parent", None)
            if isinstance(parent, Tag) and (
                parent.name in {"script", "style", "template"} or _is_hidden_element(parent) or _is_noise_container(parent)
            ):
                continue
            text = str(node).strip()
            if text:
                texts.append(text)
    return " ".join(texts).lower()


def _is_noise_container(element: Tag) -> bool:
    if not isinstance(element, Tag):
        return False
    if element.name == "template":
        return True
    attr_blob = _element_attr_blob(element)
    text_blob = " ".join(filter(None, [element.get("id"), " ".join(element.get("class", [])) if element.get("class") else None])).lower()
    return bool(NOISE_TOKEN_RE.search(attr_blob) or NOISE_TOKEN_RE.search(text_blob))


def _has_visible_passwordless_trigger(signals: _CandidateSignals) -> bool:
    return any(
        action.type in {"continue", "action"} and PASSWORDLESS_RE.search(action.label.lower())
        for action in signals.actions
    ) or "passkey" in signals.text_blob or "magic link" in signals.text_blob


def _is_broad_wrapper_with_nested_form(element: Tag) -> bool:
    if element.name == "form":
        return False
    if element.get("role") == "dialog" or element.name == "dialog":
        return False
    return element.find("form") is not None


def _has_auth_bearing_descendant(element: Tag) -> bool:
    for node in element.find_all(["form", "section", "div", "dialog", "aside", "main", "article"], recursive=True):
        if node is element or _is_hidden_element(node) or _is_noise_container(node):
            continue
        if _is_auth_bearing_node(node):
            return True
    return False
