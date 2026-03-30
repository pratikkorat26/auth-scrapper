from __future__ import annotations

from dataclasses import dataclass, field

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
)
USERNAME_KEYWORDS = ("user", "username", "email", "login", "identifier", "member id")
SUBMIT_KEYWORDS = ("login", "log in", "sign in", "continue", "submit", "next")
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


@dataclass
class ExtractedField:
    type: str
    label: str | None = None
    name: str | None = None
    selector_hint: str | None = None
    required: bool = False


@dataclass
class ExtractedAction:
    type: str
    label: str
    provider: str | None = None
    selector_hint: str | None = None


@dataclass
class AlternateCandidate:
    status: str
    surface_type: str
    confidence: float
    signals: list[str]
    summary: str


@dataclass
class DetectionResult:
    found: bool
    confidence: float
    signals: list[str]
    snippet: str | None
    message: str
    status: str = "not_found"
    surface_type: str | None = None
    fields: list[ExtractedField] = field(default_factory=list)
    actions: list[ExtractedAction] = field(default_factory=list)
    providers: list[str] = field(default_factory=list)
    alternate_candidates: list[AlternateCandidate] = field(default_factory=list)


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
        )

    analyses = [_analyze_candidate(candidate) for candidate in candidates]
    analyses.sort(key=lambda item: (item.score, item.confidence), reverse=True)
    best = analyses[0]

    if best.status == "not_found":
        return DetectionResult(
            found=False,
            confidence=0.0,
            signals=best.signals,
            snippet=None,
            message="Authentication component not found.",
            status="not_found",
        )

    return DetectionResult(
        found=best.status == "found",
        confidence=best.confidence,
        signals=best.signals,
        snippet=best.snippet,
        message=best.message,
        status=best.status,
        surface_type=best.surface_type,
        fields=best.fields,
        actions=best.actions,
        providers=best.providers,
        alternate_candidates=_build_alternate_candidates(analyses[1:], best.score),
    )


def _build_candidates(soup: BeautifulSoup) -> list[Tag]:
    candidates: list[Tag] = []
    seen: set[int] = set()

    candidate_tags = ["form", "dialog", "section", "div", "aside", "main", "article"]

    for element in soup.find_all(candidate_tags):
        if not isinstance(element, Tag):
            continue

        if not _is_candidate_element(element):
            continue

        identifier = id(element)
        if identifier in seen:
            continue
        seen.add(identifier)
        candidates.append(element)

    return candidates


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

    return False


def _analyze_candidate(element: Tag) -> _CandidateAnalysis:
    signals: list[str] = []
    score = 0

    fields = _extract_fields(element)
    actions = _extract_actions(element)
    providers = _extract_sso_providers(element)
    surface_type = _detect_surface_type(element, fields, providers)

    field_types = {field.type for field in fields}
    has_password = "password" in field_types
    has_identity = any(field_type in {"email", "username"} for field_type in field_types)
    has_submit = any(action.type in {"submit", "continue"} for action in actions)
    has_auth_keyword = _has_auth_keyword(element)
    has_negative_signal = _has_negative_signal(element)

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
        and score >= 3
        and (
            providers
            or has_identity
            or any(action.type == "continue" for action in actions)
            or has_auth_keyword
        )
    ):
        status = "partial_auth_surface"
        message = "Partial authentication surface detected."

    confidence = 0.0
    if status == "found":
        confidence = round(min(max(score, 1) / 7.0, 1.0), 2)
    elif status == "partial_auth_surface":
        confidence = round(min(max(score, 1) / 6.0, 0.89), 2)

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
    )


def _extract_fields(element: Tag) -> list[ExtractedField]:
    fields: list[ExtractedField] = []

    for input_tag in element.find_all("input"):
        field_type = _classify_input(input_tag)
        label = _extract_label(input_tag)
        name = input_tag.get("name") or input_tag.get("id")
        selector_hint = input_tag.get("name") or input_tag.get("id") or input_tag.get("placeholder")
        required = input_tag.has_attr("required")
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


def _detect_surface_type(
    element: Tag,
    fields: list[ExtractedField],
    providers: list[str],
) -> str:
    field_types = {field.type for field in fields}
    text_blob = _element_text_blob(element)
    classes = " ".join(element.get("class", []))

    if element.name == "dialog" or element.get("role") == "dialog" or element.get("aria-modal") == "true":
        return "dialog"
    if any(keyword in classes.lower() for keyword in ("drawer", "sheet", "flyout", "sidebar")):
        return "drawer"
    if providers and "password" not in field_types and not {"email", "username"} & field_types:
        return "sso_only"
    if "password" not in field_types and {"email", "username"} & field_types and any(
        keyword in text_blob for keyword in ("continue", "next", "code")
    ):
        return "multi_step"
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


def _extract_label(input_tag: Tag) -> str | None:
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
    seen: set[tuple[str, str | None, str | None]] = set()
    for field in fields:
        key = (field.type, field.label, field.name)
        if key in seen:
            continue
        seen.add(key)
        unique.append(field)
    return unique


def _unique_actions(actions: list[ExtractedAction]) -> list[ExtractedAction]:
    unique: list[ExtractedAction] = []
    seen: set[tuple[str, str, str | None]] = set()
    for action in actions:
        key = (action.type, action.label, action.provider)
        if key in seen:
            continue
        seen.add(key)
        unique.append(action)
    return unique


def _build_alternate_candidates(analyses: list[_CandidateAnalysis], best_score: int) -> list[AlternateCandidate]:
    alternates: list[AlternateCandidate] = []
    for candidate in analyses:
        if candidate.status == "not_found":
            continue
        if candidate.score < best_score - 2:
            continue
        alternates.append(
            AlternateCandidate(
                status=candidate.status,
                surface_type=candidate.surface_type,
                confidence=candidate.confidence,
                signals=candidate.signals,
                summary=candidate.message,
            )
        )
        if len(alternates) == 2:
            break
    return alternates


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
