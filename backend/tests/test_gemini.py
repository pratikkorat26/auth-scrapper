from types import SimpleNamespace

from pydantic import ValidationError

from app.services.detector import AuthComponent, DetectionResult
from app.services.gemini import (
    GeminiDecision,
    _extract_response_text,
    _normalize_component_payload,
    _normalize_gemini_payload,
    _parse_gemini_json,
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


def test_extract_relevant_sections_keeps_auth_button_context(monkeypatch) -> None:
    monkeypatch.setattr("app.services.gemini.get_settings", lambda: SimpleNamespace(ai_max_input_chars=600))
    html = """
    <html><body>
      <div class="hero-copy">Welcome to the site</div>
      <div class="auth-shell">
        <button type="button">Continue with Google</button>
      </div>
    </body></html>
    """

    excerpt = extract_relevant_sections(html)

    assert "Continue with Google" in excerpt
    assert "auth-shell" in excerpt


def test_gemini_decision_requires_components_for_auth_outcome() -> None:
    try:
        GeminiDecision(status="found", message="Detected", confidence=0.8, components=[])
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected ValidationError")


def test_parse_gemini_json_accepts_plain_json_object() -> None:
    payload = _parse_gemini_json('{"status":"found","message":"Detected","confidence":0.8,"components":[]}')
    assert payload["status"] == "found"


def test_parse_gemini_json_accepts_code_fence() -> None:
    payload = _parse_gemini_json('```json\n{"status":"not_found","message":"No auth","confidence":0.2,"components":[]}\n```')
    assert payload["status"] == "not_found"


def test_parse_gemini_json_accepts_extra_prose() -> None:
    payload = _parse_gemini_json('Here is the result:\n{"status":"partial","message":"Maybe auth","confidence":0.6,"components":[]}\nThanks.')
    assert payload["status"] == "partial"


def test_normalize_gemini_payload_fills_missing_components_from_baseline() -> None:
    baseline = DetectionResult(
        found=True,
        confidence=0.72,
        signals=["sso_provider"],
        snippet="<section>...</section>",
        message="Partial authentication surface detected.",
        status="partial_auth_surface",
        components=[
            AuthComponent("oauth", "sso_only", 0.72, None, ["sso_provider"], ["Google"], [], "<section>...</section>", "OAuth")
        ],
    )

    normalized = _normalize_gemini_payload({"status": "found", "message": "Detected"}, baseline)

    assert normalized["status"] == "found"
    assert normalized["components"]
    assert normalized["confidence"] == 0.72
    assert normalized["components"][0]["type"] == "oauth"


def test_normalize_gemini_payload_fills_missing_message_and_confidence() -> None:
    baseline = DetectionResult(
        found=False,
        confidence=0.0,
        signals=[],
        snippet=None,
        message="Authentication component not found.",
        status="not_found",
        components=[],
    )

    normalized = _normalize_gemini_payload({"status": "blocked"}, baseline)

    assert normalized["status"] == "blocked_or_inconclusive"
    assert normalized["message"] == "The page appears blocked or inconclusive."
    assert normalized["confidence"] == 0.5


def test_normalize_component_payload_defaults_missing_summary() -> None:
    result = _normalize_component_payload({"type": "traditional", "confidence": 0.8})
    assert result["summary"] == "Authentication component"


def test_normalize_component_payload_coerces_invalid_type() -> None:
    result = _normalize_component_payload({"type": "login_form", "confidence": 0.8, "summary": "Login"})
    assert result["type"] == "unknown_auth_surface"


def test_normalize_component_payload_clamps_confidence_over_range() -> None:
    assert _normalize_component_payload({"type": "traditional", "confidence": 120, "summary": "x"})["confidence"] == 1.0
    assert _normalize_component_payload({"type": "traditional", "confidence": -5, "summary": "x"})["confidence"] == 0.0


def test_normalize_component_payload_handles_non_dict_item() -> None:
    result = _normalize_component_payload("not a dict")
    assert result["type"] == "unknown_auth_surface"
    assert result["summary"] == "Authentication component"
    assert 0.0 <= result["confidence"] <= 1.0


def test_normalize_gemini_payload_normalizes_each_component() -> None:
    baseline = DetectionResult(
        found=False, confidence=0.0, signals=[], snippet=None,
        message="Not found.", status="not_found", components=[],
    )
    payload = {
        "status": "found",
        "message": "Found",
        "confidence": 0.9,
        "components": [
            {"type": "login_form", "confidence": 999, "summary": ""},
            {"type": "oauth", "confidence": 0.7},
            "bad_item",
        ],
    }
    normalized = _normalize_gemini_payload(payload, baseline)
    assert normalized["components"][0]["type"] == "unknown_auth_surface"
    assert normalized["components"][0]["confidence"] == 1.0
    assert normalized["components"][0]["summary"] == "Authentication component"
    assert normalized["components"][1]["summary"] == "Authentication component"
    assert normalized["components"][2]["type"] == "unknown_auth_surface"


def test_extract_response_text_reads_fallback_candidate_parts() -> None:
    response = SimpleNamespace(
        text="",
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[SimpleNamespace(text='{"status":"not_found","message":"No auth","confidence":0.2,"components":[]}')]))],
    )

    extracted = _extract_response_text(response)
    assert '"status":"not_found"' in extracted
