from __future__ import annotations

from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag

from ..core.config import get_settings

AUTH_KEYWORDS = ("login", "log in", "sign in", "signin", "auth", "password")
USERNAME_KEYWORDS = ("user", "username", "email", "login", "identifier")
SUBMIT_KEYWORDS = ("login", "log in", "sign in", "continue", "submit")


@dataclass
class DetectionResult:
    found: bool
    confidence: float
    signals: list[str]
    snippet: str | None
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
        )

    scored = [_score_candidate(candidate) for candidate in candidates]
    best_score, signals, element = max(scored, key=lambda item: item[0])
    if best_score <= 0:
        return DetectionResult(
            found=False,
            confidence=0.0,
            signals=[],
            snippet=None,
            message="Authentication component not found.",
        )

    confidence = round(min(best_score / 5.0, 1.0), 2)
    return DetectionResult(
        found=True,
        confidence=confidence,
        signals=signals,
        snippet=_build_snippet(element),
        message="Authentication component detected.",
    )


def _build_candidates(soup: BeautifulSoup) -> list[Tag]:
    candidates: list[Tag] = []
    seen: set[int] = set()

    for form in soup.find_all("form"):
        identifier = id(form)
        if identifier not in seen:
            seen.add(identifier)
            candidates.append(form)

    for password_input in soup.find_all("input", attrs={"type": "password"}):
        container = password_input.find_parent(["form", "section", "div", "main", "article"])
        if not container:
            container = password_input
        identifier = id(container)
        if identifier not in seen:
            seen.add(identifier)
            candidates.append(container)

    return candidates


def _score_candidate(element: Tag) -> tuple[int, list[str], Tag]:
    score = 0
    signals: list[str] = []

    if element.find("input", attrs={"type": "password"}):
        score += 3
        signals.append("password_input")

    if _has_username_or_email_input(element):
        score += 1
        signals.append("username_or_email_input")

    if _has_submit_button(element):
        score += 1
        signals.append("submit_button")

    if _has_auth_keyword(element):
        score += 1
        signals.append("auth_keyword")

    return score, signals, element


def _has_username_or_email_input(element: Tag) -> bool:
    for input_tag in element.find_all("input"):
        input_type = (input_tag.get("type") or "text").lower()
        input_text = " ".join(
            filter(
                None,
                [
                    input_type,
                    input_tag.get("name"),
                    input_tag.get("id"),
                    input_tag.get("placeholder"),
                    input_tag.get("autocomplete"),
                ],
            )
        ).lower()
        if input_type in {"email", "text"} and any(keyword in input_text for keyword in USERNAME_KEYWORDS):
            return True
    return False


def _has_submit_button(element: Tag) -> bool:
    for button in element.find_all(["button", "input"]):
        button_type = (button.get("type") or "").lower()
        button_text = " ".join(
            filter(None, [button_type, button.get("value"), button.get_text(" ", strip=True)])
        ).lower()
        if button.name == "button" and (button_type in {"submit", ""} or any(keyword in button_text for keyword in SUBMIT_KEYWORDS)):
            return True
        if button.name == "input" and button_type == "submit":
            return True
    return False


def _has_auth_keyword(element: Tag) -> bool:
    texts = [element.get_text(" ", strip=True)]
    for attr in ("id", "class", "name", "aria-label", "data-testid"):
        value = element.get(attr)
        if isinstance(value, list):
            texts.append(" ".join(value))
        elif value:
            texts.append(str(value))
    haystack = " ".join(texts).lower()
    return any(keyword in haystack for keyword in AUTH_KEYWORDS)


def _build_snippet(element: Tag) -> str:
    snippet = element.prettify(formatter="minimal").strip()
    max_length = get_settings().max_snippet_length
    if len(snippet) <= max_length:
        return snippet

    truncated = snippet[: max_length - 3].rstrip()
    last_newline = truncated.rfind("\n")
    if last_newline > 0:
        truncated = truncated[:last_newline].rstrip()
    return truncated + "\n..."
