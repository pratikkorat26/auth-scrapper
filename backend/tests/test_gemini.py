from types import SimpleNamespace

from pydantic import ValidationError

from app.services.detector import AuthComponent, DetectionResult
from app.services.gemini import (
    GeminiDecision,
    ai_fallback_available,
    extract_relevant_sections,
    should_use_ai_fallback,
)


def test_should_use_ai_fallback_for_partial_surface(monkeypatch) -> None:
    monkeypatch.setattr("app.services.gemini.get_settings", lambda: SimpleNamespace(ai_low_confidence_threshold=0.65))
    detection = DetectionResult(
        found=True,
        confidence=0.52,
        signals=["auth_keyword"],
        snippet="<section>...</section>",
        message="Partial authentication surface detected.",
        status="partial_auth_surface",
        components=[AuthComponent("oauth", "sso_only", 0.52, None, ["sso_provider"], ["Google"], [], "<section>...</section>", "Partial")],
    )
    assert should_use_ai_fallback(detection) is True


def test_should_not_use_ai_fallback_for_high_confidence_found(monkeypatch) -> None:
    monkeypatch.setattr("app.services.gemini.get_settings", lambda: SimpleNamespace(ai_low_confidence_threshold=0.65))
    detection = DetectionResult(
        found=True,
        confidence=0.91,
        signals=["password_input"],
        snippet="<form>...</form>",
        message="Authentication component detected.",
        status="found",
    )
    assert should_use_ai_fallback(detection) is False


def test_ai_fallback_availability_requires_flag_key_and_sdk(monkeypatch) -> None:
    monkeypatch.setattr("app.services.gemini.get_settings", lambda: SimpleNamespace(enable_ai_fallback=True, gemini_api_key="key"))
    monkeypatch.setattr("app.services.gemini.genai", object)
    monkeypatch.setattr("app.services.gemini.types", object)
    assert ai_fallback_available() is True


def test_extract_relevant_sections_prefers_auth_markup(monkeypatch) -> None:
    monkeypatch.setattr("app.services.gemini.get_settings", lambda: SimpleNamespace(ai_max_input_chars=300))
    html = (
        "<html><body>"
        + ("x" * 2000)
        + '<form id="login"><input type="password" /><button>Sign in</button></form>'
        + ("y" * 2000)
        + "</body></html>"
    )
    excerpt = extract_relevant_sections(html)
    assert "Sign in" in excerpt
    assert len(excerpt) <= 300


def test_gemini_decision_requires_components_for_auth_outcome() -> None:
    try:
        GeminiDecision(status="found", message="Detected", confidence=0.8, components=[])
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected ValidationError")
