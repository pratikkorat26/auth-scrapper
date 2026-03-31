import asyncio

from app.services.analysis import analyze_url
from app.services.browser import BrowserMarkupSnapshot
from app.services.detector import DetectionResult
from app.services.fetcher import FetchError
from app.services.gemini import AIFallbackResult


def test_analyze_url_uses_browser_as_primary_path(monkeypatch) -> None:
    rendered_html = """
    <html><body><form><input type="email" name="email" /><input type="password" name="password" /><button type="submit">Login</button></form></body></html>
    """

    async def fake_render_html(_: str):
        from app.services.browser import BrowserRenderResult

        return BrowserRenderResult(
            html=rendered_html,
            interaction_used=True,
            typing_used=False,
            screenshot_base64="abc",
            snapshots=[BrowserMarkupSnapshot("passive_wait", rendered_html, False, False)],
        )

    async def fail_fetch_html(_: str) -> str:
        raise AssertionError("static fallback should not run when browser succeeds")

    monkeypatch.setattr("app.services.analysis.render_html", fake_render_html)
    monkeypatch.setattr("app.services.analysis.fetch_html", fail_fetch_html)

    result = asyncio.run(analyze_url("https://example.com/login"))

    assert result.analysis_mode == "browser_primary"
    assert result.fallback_used is False
    assert result.interaction_used is True
    assert result.detection.status == "found"


def test_analyze_url_chooses_best_snapshot(monkeypatch) -> None:
    weak_html = """
    <html><body><section><input type="email" name="email" /><button type="button">Continue</button></section></body></html>
    """
    strong_html = """
    <html><body><form><input type="email" name="email" /><input type="password" name="password" /><button type="submit">Login</button></form></body></html>
    """

    async def fake_render_html(_: str):
        from app.services.browser import BrowserRenderResult

        return BrowserRenderResult(
            html=strong_html,
            interaction_used=True,
            typing_used=True,
            screenshot_base64=None,
            snapshots=[
                BrowserMarkupSnapshot("passive_wait", weak_html, False, False),
                BrowserMarkupSnapshot("identity_step", strong_html, True, True),
            ],
        )

    monkeypatch.setattr("app.services.analysis.render_html", fake_render_html)

    result = asyncio.run(analyze_url("https://example.com/login"))

    assert result.detection.status == "found"
    assert result.detection.snippet is not None
    assert "type=\"password\"" in result.detection.snippet


def test_analyze_url_keeps_secondary_components_from_other_snapshots(monkeypatch) -> None:
    strong_html = """
    <html><body><form><input type="email" name="email" /><input type="password" name="password" /><button type="submit">Login</button></form></body></html>
    """
    secondary_html = """
    <html><body>
      <section><button type="button">Continue with passkey</button></section>
      <section><button type="button">Continue with Google</button></section>
    </body></html>
    """

    async def fake_render_html(_: str):
        from app.services.browser import BrowserRenderResult

        return BrowserRenderResult(
            html=strong_html,
            interaction_used=True,
            typing_used=False,
            screenshot_base64=None,
            snapshots=[
                BrowserMarkupSnapshot("passive_wait", secondary_html, False, False),
                BrowserMarkupSnapshot("identity_step", strong_html, True, True),
            ],
        )

    monkeypatch.setattr("app.services.analysis.render_html", fake_render_html)

    result = asyncio.run(analyze_url("https://example.com/login"))

    assert result.detection.status == "found"
    assert result.detection.components
    assert result.detection.components[0].type == "traditional"
    assert sorted(component.type for component in result.detection.components) == ["oauth", "passwordless", "traditional"]


def test_analyze_url_prefers_focused_auth_snapshot_over_noisier_final_shell(monkeypatch) -> None:
    focused_html = """
    <html><body><form id="login"><input type="text" name="email" /><input type="password" name="password" /><button type="submit">Log in</button></form></body></html>
    """
    noisy_final_html = """
    <html><body>
      <main class="wrapper shell">
        <div class="headline">Welcome back</div>
        <div class="login-copy">Log in to continue</div>
        <section><button type="button">Continue with Facebook</button></section>
        <form id="login"><input type="text" name="email" /><input type="password" name="password" /><button type="submit">Log in</button></form>
      </main>
    </body></html>
    """

    async def fake_render_html(_: str):
        from app.services.browser import BrowserRenderResult

        return BrowserRenderResult(
            html=noisy_final_html,
            interaction_used=True,
            typing_used=False,
            screenshot_base64=None,
            snapshots=[
                BrowserMarkupSnapshot("identity_reveal_snapshot", focused_html, True, True),
                BrowserMarkupSnapshot("final_auth_state", noisy_final_html, True, True),
            ],
        )

    monkeypatch.setattr("app.services.analysis.render_html", fake_render_html)

    result = asyncio.run(analyze_url("https://example.com/login"))

    assert result.detection.status == "found"
    assert result.detection.snippet is not None
    assert result.detection.snippet.startswith("<form")


def test_analyze_url_returns_markup_for_partial_visible_auth_shell(monkeypatch) -> None:
    partial_html = """
    <html><body>
      <section class="login_card wrapper">
        <input type="text" name="credential" placeholder="Enter email or mobile" />
        <button type="button">Request OTP</button>
        <a href="/password">Sign in with password</a>
      </section>
    </body></html>
    """

    async def fake_render_html(_: str):
        from app.services.browser import BrowserRenderResult

        return BrowserRenderResult(
            html=partial_html,
            interaction_used=False,
            typing_used=False,
            screenshot_base64=None,
            snapshots=[BrowserMarkupSnapshot("settled_dom", partial_html, False, False)],
        )

    monkeypatch.setattr("app.services.analysis.render_html", fake_render_html)

    result = asyncio.run(analyze_url("https://example.com/login"))

    assert result.detection.status == "partial_auth_surface"
    assert result.detection.snippet is not None
    assert "Request OTP" in result.detection.snippet


def test_analyze_url_falls_back_to_static_when_browser_fails(monkeypatch) -> None:
    static_html = """
    <html><body><form><input type="email" name="email" /><input type="password" name="password" /><button type="submit">Login</button></form></body></html>
    """

    async def fake_render_html(_: str):
        raise FetchError("Browser fallback failed.")

    async def fake_fetch_html(_: str) -> str:
        return static_html

    monkeypatch.setattr("app.services.analysis.render_html", fake_render_html)
    monkeypatch.setattr("app.services.analysis.fetch_html", fake_fetch_html)

    result = asyncio.run(analyze_url("https://example.com/login"))

    assert result.analysis_mode == "static_html"
    assert result.fallback_used is True
    assert result.detection.status == "found"


def test_analyze_url_returns_blocked_when_browser_and_static_fail(monkeypatch) -> None:
    async def fake_render_html(_: str):
        raise FetchError("Browser fallback failed.")

    async def fake_fetch_html(_: str) -> str:
        raise FetchError("Upstream returned status 403.")

    monkeypatch.setattr("app.services.analysis.render_html", fake_render_html)
    monkeypatch.setattr("app.services.analysis.fetch_html", fake_fetch_html)

    result = asyncio.run(analyze_url("https://example.com/login"))

    assert result.analysis_mode == "browser_primary"
    assert result.fallback_used is True
    assert result.detection.status == "blocked_or_inconclusive"
    assert "block automated access" in result.detection.message.lower()


def test_analyze_url_uses_protected_page_message_for_challenge_detection(monkeypatch) -> None:
    challenge_html = """
    <html><body><section><h2>Verify you are human</h2><div>Request blocked</div></section></body></html>
    """

    async def fake_render_html(_: str):
        from app.services.browser import BrowserRenderResult

        return BrowserRenderResult(
            html=challenge_html,
            interaction_used=False,
            typing_used=False,
            screenshot_base64=None,
            snapshots=[BrowserMarkupSnapshot("settled_dom", challenge_html, False, False)],
        )

    monkeypatch.setattr("app.services.analysis.render_html", fake_render_html)

    result = asyncio.run(analyze_url("https://example.com/login"))

    assert result.detection.status == "blocked_or_inconclusive"
    assert "block automated access" in result.detection.message.lower()


def test_analyze_url_keeps_generic_message_for_non_blocked_inconclusive(monkeypatch) -> None:
    async def fake_render_html(_: str):
        raise FetchError("Browser fallback failed.")

    async def fake_fetch_html(_: str) -> str:
        raise FetchError("Failed to fetch URL.")

    monkeypatch.setattr("app.services.analysis.render_html", fake_render_html)
    monkeypatch.setattr("app.services.analysis.fetch_html", fake_fetch_html)

    result = asyncio.run(analyze_url("https://example.com/login"))

    assert result.detection.status == "blocked_or_inconclusive"
    assert result.detection.message == "Failed to fetch URL."


def test_analyze_url_uses_gemini_as_audit_only(monkeypatch) -> None:
    rendered_html = """
    <html><body><section aria-label="Sign in"><button type="button">Continue with Google</button></section></body></html>
    """

    async def fake_render_html(_: str):
        from app.services.browser import BrowserRenderResult

        return BrowserRenderResult(
            html=rendered_html,
            interaction_used=False,
            typing_used=False,
            screenshot_base64="abc",
            snapshots=[BrowserMarkupSnapshot("passive_wait", rendered_html, False, False)],
        )

    async def fake_audit_detection_with_ai(**kwargs):
        return AIFallbackResult(
            status="found",
            message="Gemini thinks this is a full auth surface.",
            ai_confidence=0.81,
            disagreed=True,
            provider="gemini",
            model="gemini-2.5-flash",
        )

    monkeypatch.setattr("app.services.analysis.render_html", fake_render_html)
    monkeypatch.setattr("app.services.analysis.ai_fallback_available", lambda: True)
    monkeypatch.setattr("app.services.analysis.should_use_ai_fallback", lambda detection: True)
    monkeypatch.setattr("app.services.analysis.audit_detection_with_ai", fake_audit_detection_with_ai)

    result = asyncio.run(analyze_url("https://example.com/login"))

    assert result.ai_used is True
    assert result.ai_refined is True
    assert result.ai_provider == "gemini"
    assert result.ai_model == "gemini-2.5-flash"
    assert result.detection.status == "partial_auth_surface"


def test_analyze_url_keeps_detector_result_when_gemini_audit_returns_none(monkeypatch) -> None:
    rendered_html = """
    <html><body><section aria-label="Sign in"><button type="button">Continue with Google</button></section></body></html>
    """

    async def fake_render_html(_: str):
        from app.services.browser import BrowserRenderResult

        return BrowserRenderResult(
            html=rendered_html,
            interaction_used=False,
            typing_used=False,
            screenshot_base64=None,
            snapshots=[BrowserMarkupSnapshot("passive_wait", rendered_html, False, False)],
        )

    async def fake_audit_detection_with_ai(**kwargs):
        return None

    monkeypatch.setattr("app.services.analysis.render_html", fake_render_html)
    monkeypatch.setattr("app.services.analysis.ai_fallback_available", lambda: True)
    monkeypatch.setattr("app.services.analysis.should_use_ai_fallback", lambda detection: True)
    monkeypatch.setattr("app.services.analysis.audit_detection_with_ai", fake_audit_detection_with_ai)

    result = asyncio.run(analyze_url("https://example.com/login"))

    assert result.ai_used is True
    assert result.ai_refined is False
    assert result.detection.status == "partial_auth_surface"


def test_analyze_url_skips_gemini_for_strong_found(monkeypatch) -> None:
    rendered_html = """
    <html><body><form><input type="email" name="email" /><input type="password" name="password" /><button type="submit">Login</button></form></body></html>
    """

    async def fake_render_html(_: str):
        from app.services.browser import BrowserRenderResult

        return BrowserRenderResult(
            html=rendered_html,
            interaction_used=False,
            typing_used=False,
            screenshot_base64=None,
            snapshots=[BrowserMarkupSnapshot("passive_wait", rendered_html, False, False)],
        )

    monkeypatch.setattr("app.services.analysis.render_html", fake_render_html)
    monkeypatch.setattr("app.services.analysis.ai_fallback_available", lambda: True)
    monkeypatch.setattr("app.services.analysis.should_use_ai_fallback", lambda detection: False)

    result = asyncio.run(analyze_url("https://example.com/login"))

    assert result.ai_used is False
    assert result.detection.status == "found"


def test_detector_authorship_survives_audit_disagreement() -> None:
    detection = DetectionResult(
        found=True,
        confidence=0.55,
        signals=["sso_provider"],
        snippet="<section><button>Continue with Google</button></section>",
        message="Partial authentication surface detected.",
        status="partial_auth_surface",
        components=[],
    )

    audit = AIFallbackResult(
        status="found",
        message="Gemini disagrees.",
        ai_confidence=0.85,
        disagreed=True,
        provider="gemini",
        model="gemini-2.5-flash",
    )

    assert detection.status == "partial_auth_surface"
    assert audit.disagreed is True
