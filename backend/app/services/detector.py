from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from bs4 import BeautifulSoup, Tag

from ..core.config import get_settings

AUTH_KEYWORDS = (
    "login",
    "log in",
    "sign in",
    "signin",
    "auth",
    "password",
    "forgot password",
    "continue with email",
    "use email",
    "continue with google",
    "continue with apple",
    "continue with facebook",
    "email me a link",
    "verification code",
    "one-time code",
    "continue as",
    "magic link",
    "passkey",
    "webauthn",
)
USERNAME_KEYWORDS = ("user", "username", "email", "login", "identifier", "member id")
NEGATIVE_KEYWORDS = (
    "search",
    "newsletter",
    "subscribe",
    "coupon",
    "promo",
    "contact",
    "feedback",
    "comment",
    "cart",
)
PROVIDER_KEYWORDS = ("google", "apple", "facebook", "github", "linkedin", "microsoft")
AUTH_CONTAINER_HINTS = ("login", "signin", "sign-in", "auth", "account", "session", "credential")
PASSWORDLESS_KEYWORDS = ("passkey", "magic link", "email me a link", "otp", "verification code", "one-time code")
PARTIAL_MARKUP_MAX_CHARS = 5000


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
class _CandidateAnalysis:
    element: Tag
    score: int
    confidence: float
    status: str
    surface_type: str
    signals: list[str]
    fields: list[ExtractedField]
    actions: list[ExtractedAction]
    providers: list[str]
    snippet: str
    message: str
    component_type: str
    selector_hint: Optional[str]


def detect_auth_component(html: str) -> DetectionResult:
    soup = BeautifulSoup(html, "lxml")
    candidates = _build_candidates(soup)
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
    analyses.sort(key=lambda item: (item.score, item.confidence), reverse=True)
    component_analyses = [item for item in analyses if item.status != "not_found"]
    best = component_analyses[0] if component_analyses else analyses[0]

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

    components = [_component_from_analysis(item) for item in component_analyses[:5]]
    primary = choose_primary_component(components)

    partial_html_markup: Optional[str] = None
    if best.status == "partial_auth_surface":
        raw = best.element.prettify(formatter="minimal").strip()
        if len(raw) > PARTIAL_MARKUP_MAX_CHARS:
            truncated = raw[: PARTIAL_MARKUP_MAX_CHARS - 3].rstrip()
            last_newline = truncated.rfind("\n")
            if last_newline > 0:
                truncated = truncated[:last_newline].rstrip()
            raw = truncated + "\n..."
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
        actions=[],
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
    return sorted(
        components,
        key=lambda component: (priority.get(component.type, 99), -component.confidence),
    )[0]


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


def _build_candidates(soup: BeautifulSoup) -> list[Tag]:
    raw_candidates: list[Tag] = []
    seen: set[int] = set()

    candidate_tags = ["form", "dialog", "section", "div", "aside", "main", "article", "span"]

    for element in soup.find_all(candidate_tags):
        if not isinstance(element, Tag) or not _is_candidate_element(element):
            continue
        identifier = id(element)
        if identifier in seen:
            continue
        seen.add(identifier)
        raw_candidates.append(element)

    for element in soup.find_all(lambda tag: isinstance(tag, Tag) and "-" in tag.name):
        identifier = id(element)
        if identifier in seen or not _is_candidate_element(element):
            continue
        seen.add(identifier)
        raw_candidates.append(element)

    return _dedupe_candidates(raw_candidates)


def _dedupe_candidates(candidates: list[Tag]) -> list[Tag]:
    deduped: list[Tag] = []
    for candidate in sorted(candidates, key=_candidate_sort_key):
        replaced = False
        for index, kept in enumerate(deduped):
            if _is_same_auth_surface(candidate, kept):
                if _prefer_candidate(candidate, kept):
                    deduped[index] = candidate
                replaced = True
                break
        if not replaced:
            deduped.append(candidate)
    return deduped


def _candidate_sort_key(element: Tag) -> tuple[int, int, int]:
    depth = len(list(element.parents))
    return (_candidate_size(element), 0 if element.name == "form" else 1, -depth)


def _candidate_size(element: Tag) -> int:
    return len(element.prettify(formatter="minimal"))


def _prefer_candidate(candidate: Tag, kept: Tag) -> bool:
    if candidate.name == "form" and kept.name != "form":
        return True
    if kept.name == "form" and candidate.name != "form":
        return False
    return _candidate_size(candidate) < _candidate_size(kept)


def _is_same_auth_surface(first: Tag, second: Tag) -> bool:
    if not (_is_overlapping_candidate(first, second) or _shares_nested_form(first, second)):
        return False

    if _shares_nested_form(first, second):
        return True

    first_providers = set(_extract_sso_providers(first))
    second_providers = set(_extract_sso_providers(second))
    if first_providers or second_providers:
        return first_providers == second_providers and bool(first_providers)

    first_field_types = {field.type for field in _extract_fields(first)} - {"unknown"}
    second_field_types = {field.type for field in _extract_fields(second)} - {"unknown"}
    if first_field_types and second_field_types and first_field_types == second_field_types:
        return True

    first_keywords = _auth_keyword_signature(first)
    second_keywords = _auth_keyword_signature(second)
    return bool(first_keywords and first_keywords == second_keywords)


def _is_overlapping_candidate(first: Tag, second: Tag) -> bool:
    return first in second.descendants or second in first.descendants


def _shares_nested_form(first: Tag, second: Tag) -> bool:
    first_form = _normalized_form_signature(first)
    second_form = _normalized_form_signature(second)
    return bool(first_form and second_form and first_form == second_form)


def _normalized_form_signature(element: Tag) -> Optional[str]:
    form = element if element.name == "form" else element.find("form")
    if not form:
        return None
    return form.prettify(formatter="minimal").strip()


def _auth_keyword_signature(element: Tag) -> tuple[str, ...]:
    blob = _element_text_blob(element)
    matches = sorted({keyword for keyword in AUTH_KEYWORDS if keyword in blob})
    return tuple(matches)


def _is_candidate_element(element: Tag) -> bool:
    if element.name == "form":
        return True
    if element.find("input", attrs={"type": "password"}):
        return True
    if element.get("role") == "dialog" or element.name == "dialog" or element.get("aria-modal") == "true":
        return True

    text_blob = _element_text_blob(element)
    if any(keyword in text_blob for keyword in AUTH_KEYWORDS):
        return True
    if _extract_sso_providers(element):
        return True

    attr_blob = " ".join(
        filter(
            None,
            [
                element.get("id"),
                " ".join(element.get("class", [])),
                element.get("data-testid"),
                element.get("slot"),
                element.name,
            ],
        )
    ).lower()
    return any(hint in attr_blob for hint in AUTH_CONTAINER_HINTS)


def _analyze_candidate(element: Tag) -> _CandidateAnalysis:
    signals: list[str] = []
    score = 0

    fields = _extract_fields(element)
    actions = _extract_actions(element)
    providers = _extract_sso_providers(element)
    surface_type = _detect_surface_type(element, fields, providers)

    field_types = {field.type for field in fields}
    has_password = "password" in field_types
    has_identity = any(field_type in {"email", "username", "phone"} for field_type in field_types)
    has_submit = any(action.type in {"submit", "continue"} for action in actions)
    has_auth_keyword = _has_auth_keyword(element)
    has_negative_signal = _has_negative_signal(element)
    has_passwordless_signal = any(keyword in _element_text_blob(element) for keyword in PASSWORDLESS_KEYWORDS)

    if has_password:
        score += 4
        signals.append("password_input")
    if has_identity:
        score += 2
        signals.append("username_or_email_input")
    if has_submit:
        score += 1
        signals.append("submit_button")
    if has_auth_keyword:
        score += 1
        signals.append("auth_keyword")
    if providers:
        score += 2
        signals.append("sso_provider")
    if surface_type in {"dialog", "drawer"}:
        score += 1
        signals.append("auth_container")
    if surface_type in {"multi_step", "sso_only"}:
        score += 1
        signals.append("progressive_auth_surface")
    if has_passwordless_signal:
        score += 1
        signals.append("passwordless_signal")
    if has_negative_signal:
        score -= 4
        signals.append("negative_context")

    status = "not_found"
    message = "Authentication component not found."
    if has_password and score >= 4 and not has_negative_signal:
        status = "found"
        message = "Authentication component detected."
    elif (
        not has_negative_signal
        and score >= 2
        and (providers or has_identity or has_passwordless_signal or any(action.type == "continue" for action in actions) or has_auth_keyword)
    ):
        status = "partial_auth_surface"
        message = "Partial authentication surface detected."

    confidence = 0.0
    if status == "found":
        confidence = round(min(max(score, 1) / 7.0, 1.0), 2)
    elif status == "partial_auth_surface":
        confidence = round(min(max(score, 1) / 6.0, 0.89), 2)

    selector_hint = _build_selector_hint(element, fields, actions)
    component_type = _detect_component_type(surface_type, fields, providers, signals, status, element)

    return _CandidateAnalysis(
        element=element,
        score=score,
        confidence=confidence,
        status=status,
        surface_type=surface_type,
        signals=signals,
        fields=fields,
        actions=actions,
        providers=providers,
        snippet=_build_snippet(element),
        message=message,
        component_type=component_type,
        selector_hint=selector_hint,
    )


def _detect_component_type(
    surface_type: str,
    fields: list[ExtractedField],
    providers: list[str],
    signals: list[str],
    status: str,
    element: Tag,
) -> str:
    field_types = {field.type for field in fields}
    text_blob = _element_text_blob(element)
    if status == "not_found":
        return "unknown_auth_surface"
    if any(token in text_blob for token in ("captcha", "verify you are human", "access denied", "blocked")):
        return "challenge"
    if "password" in field_types:
        return "traditional"
    if providers:
        return "oauth"
    if any(signal == "passwordless_signal" for signal in signals):
        return "passwordless"
    if surface_type == "multi_step":
        return "multi_step"
    return "unknown_auth_surface"


def _build_selector_hint(
    element: Tag,
    fields: list[ExtractedField],
    actions: list[ExtractedAction],
) -> Optional[str]:
    if element.name == "form":
        if element.get("id"):
            return f"form#{element.get('id')}"
        if element.get("data-testid"):
            return f"[data-testid='{element.get('data-testid')}']"
        return "form"

    if element.get("id"):
        return f"#{element.get('id')}"

    if fields and fields[0].selector_hint:
        hint = fields[0].selector_hint
        if hint and " " not in hint:
            return f"input[name='{hint}'], input[id='{hint}']"

    if actions and actions[0].selector_hint:
        return actions[0].selector_hint

    return None


def _extract_fields(element: Tag) -> list[ExtractedField]:
    fields: list[ExtractedField] = []
    for input_tag in element.find_all(["input", "textarea"]):
        field_type = _classify_input(input_tag)
        label = _extract_label(input_tag)
        name = input_tag.get("name") or input_tag.get("id")
        selector_hint = (
            input_tag.get("name")
            or input_tag.get("id")
            or input_tag.get("placeholder")
            or input_tag.get("data-testid")
        )
        required = input_tag.has_attr("required") or input_tag.get("aria-required") == "true"
        fields.append(
            ExtractedField(
                type=field_type,
                label=label,
                name=name,
                selector_hint=selector_hint,
                required=required,
            )
        )
    return _unique_fields(fields)


def _extract_actions(element: Tag) -> list[ExtractedAction]:
    actions: list[ExtractedAction] = []
    for action_tag in element.find_all(["button", "input", "a"]):
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
        provider = next((item.title() for item in PROVIDER_KEYWORDS if item in lowered), None)
        action_type = "action"
        if provider:
            action_type = "provider"
        elif any(keyword in lowered for keyword in ("continue", "next")):
            action_type = "continue"
        elif any(keyword in lowered for keyword in ("login", "log in", "sign in", "submit")):
            action_type = "submit"

        selector_hint = action_tag.get("id") or action_tag.get("name") or label
        actions.append(
            ExtractedAction(
                type=action_type,
                label=label,
                provider=provider,
                selector_hint=selector_hint,
            )
        )
    return _unique_actions(actions)


def _extract_sso_providers(element: Tag) -> list[str]:
    haystack = _element_text_blob(element)
    providers = [provider.title() for provider in PROVIDER_KEYWORDS if provider in haystack]
    return sorted(set(providers))


def _detect_surface_type(element: Tag, fields: list[ExtractedField], providers: list[str]) -> str:
    field_types = {field.type for field in fields}
    text_blob = _element_text_blob(element)
    classes = " ".join(element.get("class", []))

    if element.name == "dialog" or element.get("role") == "dialog" or element.get("aria-modal") == "true":
        return "dialog"
    if any(keyword in classes.lower() for keyword in ("drawer", "sheet", "flyout", "sidebar")):
        return "drawer"
    if providers and "password" not in field_types and not {"email", "username", "phone"} & field_types:
        return "sso_only"
    if "password" not in field_types and {"email", "username", "phone"} & field_types and any(
        keyword in text_blob for keyword in ("continue", "next", "code")
    ):
        return "multi_step"
    if any(keyword in text_blob for keyword in PASSWORDLESS_KEYWORDS):
        return "passwordless"
    if element.name == "form":
        return "form"
    return "auth_surface"


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
    if input_id:
        label = input_tag.find_parent().find("label", attrs={"for": input_id}) if input_tag.find_parent() else None
        if label:
            return label.get_text(" ", strip=True)

    parent_label = input_tag.find_parent("label")
    if parent_label:
        return parent_label.get_text(" ", strip=True)

    return None


def _has_auth_keyword(element: Tag) -> bool:
    return any(keyword in _element_text_blob(element) for keyword in AUTH_KEYWORDS)


def _has_negative_signal(element: Tag) -> bool:
    return any(keyword in _element_text_blob(element) for keyword in NEGATIVE_KEYWORDS)


def _element_text_blob(element: Tag) -> str:
    texts = [element.get_text(" ", strip=True)]
    for attr in ("id", "class", "name", "aria-label", "data-testid", "placeholder", "title"):
        value = element.get(attr)
        if isinstance(value, list):
            texts.append(" ".join(value))
        elif value:
            texts.append(str(value))
    return " ".join(texts).lower()


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


def _build_snippet(element: Tag) -> str:
    snippet_element = element if element.name == "form" else element.find("form") or element
    snippet = snippet_element.prettify(formatter="minimal").strip()
    if snippet_element.name == "form":
        return snippet

    max_length = get_settings().max_snippet_length
    if len(snippet) <= max_length:
        return snippet

    truncated = snippet[: max_length - 3].rstrip()
    last_newline = truncated.rfind("\n")
    if last_newline > 0:
        truncated = truncated[:last_newline].rstrip()
    return truncated + "\n..."
