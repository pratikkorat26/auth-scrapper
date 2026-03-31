from app.services.analysis import STRONG_DETECTION_CONFIDENCE, _is_strong_detection, _should_use_browser_fallback, analyze_url
from app.services.detector import AuthComponent, DetectionResult
from app.services.fetcher import FetchError, UpstreamTimeoutError
from app.services.gemini import AIFallbackResult


def test_spa_shell_detection_returns_true() -> None:
    html = """
    <html>
      <head><title>Login</title></head>
      <body>
        <div id="root"></div>
        <script src="/assets/runtime.js"></script>
        <script src="/assets/vendors.js"></script>
      </body>
    </html>
    """

    class Detection:
        status = "not_found"

    assert _should_use_browser_fallback("https://example.com/login", html, Detection()) is True


def test_analyze_url_uses_browser_fallback(monkeypatch) -> None:
    static_html = """
    <html><body><div id="root"></div><script src="/assets/runtime.js"></script><script src="/assets/main.js"></script></body></html>
    """
    rendered_html = """
    <html><body><form><input type="email" name="email" /><input type="password" name="password" /><button type="submit">Login</button></form></body></html>
    """

    async def fake_fetch_html(_: str) -> str:
        return static_html

    async def fake_render_html(_: str):
        from app.services.browser import BrowserRenderResult

        return BrowserRenderResult(html=rendered_html, interaction_used=True, typing_used=True, screenshot_base64="abc")

    monkeypatch.setattr("app.services.analysis.fetch_html", fake_fetch_html)
    monkeypatch.setattr("app.services.analysis.render_html", fake_render_html)

    result = __import__("asyncio").run(analyze_url("https://example.com/login"))

    assert result.detection.found is True
    assert result.analysis_mode == "browser_fallback"
    assert result.fallback_used is True
    assert result.interaction_used is True
    assert result.ai_used is False


def test_strong_static_detection_skips_browser_fallback() -> None:
    detection = DetectionResult(
        found=True,
        confidence=STRONG_DETECTION_CONFIDENCE,
        signals=["password_input"],
        snippet="<form>...</form>",
        message="Authentication component detected.",
        status="found",
        components=[],
    )

    assert _is_strong_detection(detection) is True
    assert _should_use_browser_fallback("https://example.com/login", "<html><body></body></html>", detection) is False


def test_low_confidence_found_triggers_browser_fallback() -> None:
    detection = DetectionResult(
        found=True,
        confidence=0.61,
        signals=["password_input"],
        snippet="<form>...</form>",
        message="Authentication component detected.",
        status="found",
        components=[],
    )

    assert _should_use_browser_fallback("https://example.com/login", "<html><body><form></form></body></html>", detection) is True


def test_analyze_url_uses_ai_for_partial_surface(monkeypatch) -> None:
    html = """
    <section aria-label="Sign in"><button type="button">Continue with Google</button></section>
    """

    async def fake_fetch_html(_: str) -> str:
        return html

    async def fake_refine_detection_with_ai(**kwargs):
        detection = DetectionResult(
            found=True,
            confidence=0.88,
            signals=["ai_gemini"],
            snippet="<form><input type='email' /><input type='password' /></form>",
            message="Gemini identified a traditional login form.",
            status="found",
            components=[
                AuthComponent(
                    type="traditional",
                    surface_type="form",
                    confidence=0.88,
                    selector_hint="form",
                    signals=["ai_gemini"],
                    providers=[],
                    fields=[],
                    snippet="<form><input type='email' /><input type='password' /></form>",
                    summary="Traditional login form",
                )
            ],
        )
        return AIFallbackResult(detection=detection, ai_confidence=0.88, refined=True, provider="gemini", model="gemini-2.5-flash")

    monkeypatch.setattr("app.services.analysis.fetch_html", fake_fetch_html)
    monkeypatch.setattr("app.services.analysis._should_use_browser_fallback", lambda *args: False)
    monkeypatch.setattr("app.services.analysis.ai_fallback_available", lambda: True)
    monkeypatch.setattr("app.services.analysis.refine_detection_with_ai", fake_refine_detection_with_ai)

    result = __import__("asyncio").run(analyze_url("https://example.com/login"))

    assert result.ai_used is True
    assert result.ai_refined is True
    assert result.ai_provider == "gemini"
    assert result.ai_model == "gemini-2.5-flash"
    assert result.detection.components[0].type == "traditional"


def test_analyze_url_keeps_heuristic_result_when_ai_returns_none(monkeypatch) -> None:
    html = """
    <section aria-label="Sign in"><button type="button">Continue with Google</button></section>
    """

    async def fake_fetch_html(_: str) -> str:
        return html

    async def fake_refine_detection_with_ai(**kwargs):
        return None

    monkeypatch.setattr("app.services.analysis.fetch_html", fake_fetch_html)
    monkeypatch.setattr("app.services.analysis._should_use_browser_fallback", lambda *args: False)
    monkeypatch.setattr("app.services.analysis.ai_fallback_available", lambda: True)
    monkeypatch.setattr("app.services.analysis.refine_detection_with_ai", fake_refine_detection_with_ai)

    result = __import__("asyncio").run(analyze_url("https://example.com/login"))

    assert result.detection.status == "partial_auth_surface"
    assert result.ai_used is True
    assert result.ai_refined is False


def test_analyze_url_uses_browser_after_fetch_error(monkeypatch) -> None:
    rendered_html = """
    <html><body><form><input type="email" name="email" /><input type="password" name="password" /><button type="submit">Login</button></form></body></html>
    """

    async def fake_fetch_html(_: str) -> str:
        raise FetchError("Upstream returned status 403.")

    async def fake_render_html(_: str):
        from app.services.browser import BrowserRenderResult

        return BrowserRenderResult(html=rendered_html, interaction_used=False, typing_used=False, screenshot_base64=None)

    monkeypatch.setattr("app.services.analysis.fetch_html", fake_fetch_html)
    monkeypatch.setattr("app.services.analysis.render_html", fake_render_html)

    result = __import__("asyncio").run(analyze_url("https://example.com/login"))

    assert result.analysis_mode == "browser_fallback"
    assert result.fallback_used is True
    assert result.detection.status == "found"


def test_analyze_url_uses_browser_after_timeout(monkeypatch) -> None:
    rendered_html = """
    <html><body><form><input type="email" name="email" /><input type="password" name="password" /><button type="submit">Login</button></form></body></html>
    """

    async def fake_fetch_html(_: str) -> str:
        raise UpstreamTimeoutError("Request timed out.")

    async def fake_render_html(_: str):
        from app.services.browser import BrowserRenderResult

        return BrowserRenderResult(html=rendered_html, interaction_used=False, typing_used=False, screenshot_base64=None)

    monkeypatch.setattr("app.services.analysis.fetch_html", fake_fetch_html)
    monkeypatch.setattr("app.services.analysis.render_html", fake_render_html)

    result = __import__("asyncio").run(analyze_url("https://example.com/login"))

    assert result.analysis_mode == "browser_fallback"
    assert result.fallback_used is True
    assert result.detection.status == "found"


def test_high_confidence_partial_skips_browser_fallback() -> None:
    detection = DetectionResult(
        found=True,
        confidence=0.75,
        signals=["oauth_button"],
        snippet="<section>...</section>",
        message="Partial authentication surface detected.",
        status="partial_auth_surface",
        components=[],
    )
    assert _should_use_browser_fallback("https://example.com/login", "<html><body></body></html>", detection) is False


def test_low_confidence_partial_triggers_browser_fallback() -> None:
    detection = DetectionResult(
        found=True,
        confidence=0.74,
        signals=["oauth_button"],
        snippet="<section>...</section>",
        message="Partial authentication surface detected.",
        status="partial_auth_surface",
        components=[],
    )
    assert _should_use_browser_fallback("https://example.com/login", "<html><body></body></html>", detection) is True


def test_analyze_url_returns_blocked_when_fetch_and_browser_fail(monkeypatch) -> None:
    async def fake_fetch_html(_: str) -> str:
        raise FetchError("Upstream returned status 403.")

    async def fake_render_html(_: str):
        raise FetchError("Browser fallback failed.")

    monkeypatch.setattr("app.services.analysis.fetch_html", fake_fetch_html)
    monkeypatch.setattr("app.services.analysis.render_html", fake_render_html)

    result = __import__("asyncio").run(analyze_url("https://example.com/login"))

    assert result.analysis_mode == "browser_fallback"
    assert result.fallback_used is True
    assert result.detection.status == "blocked_or_inconclusive"
