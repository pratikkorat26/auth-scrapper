import asyncio

from app.services.analysis import analyze_url
from app.services.browser import BrowserMarkupSnapshot
from app.services.fetcher import FetchError
from tests.fixtures import browser_result, challenge_html, login_form_html


def test_analyze_url_uses_browser_as_primary_path(monkeypatch) -> None:
    rendered_html = login_form_html()

    async def fake_render_html(_: str):
        return browser_result(rendered_html, interaction_used=True)

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
    weak_html = '<html><body><section><input type="email" name="email" /><button type="button">Continue</button></section></body></html>'
    strong_html = login_form_html()

    async def fake_render_html(_: str):
        return browser_result(
            strong_html,
            interaction_used=True,
            typing_used=True,
            snapshots=[
                BrowserMarkupSnapshot("passive_wait", weak_html, False, False),
                BrowserMarkupSnapshot("identity_step", strong_html, True, True),
            ],
        )

    monkeypatch.setattr("app.services.analysis.render_html", fake_render_html)

    result = asyncio.run(analyze_url("https://example.com/login"))

    assert result.detection.status == "found"
    assert result.detection.snippet is not None
    assert 'type="password"' in result.detection.snippet


def test_analyze_url_keeps_secondary_components_from_other_snapshots(monkeypatch) -> None:
    strong_html = login_form_html()
    secondary_html = (
        "<html><body>"
        '<section><button type="button">Continue with passkey</button></section>'
        '<section><button type="button">Continue with Google</button></section>'
        "</body></html>"
    )

    async def fake_render_html(_: str):
        return browser_result(
            strong_html,
            interaction_used=True,
            snapshots=[
                BrowserMarkupSnapshot("passive_wait", secondary_html, False, False),
                BrowserMarkupSnapshot("identity_step", strong_html, True, True),
            ],
        )

    monkeypatch.setattr("app.services.analysis.render_html", fake_render_html)

    result = asyncio.run(analyze_url("https://example.com/login"))

    assert result.detection.status == "found"
    assert sorted(component.type for component in result.detection.components) == ["oauth", "passwordless", "traditional"]


def test_analyze_url_prefers_focused_auth_snapshot_over_noisier_final_shell(monkeypatch) -> None:
    focused_html = '<html><body><form id="login"><input type="text" name="email" /><input type="password" name="password" /><button type="submit">Log in</button></form></body></html>'
    noisy_final_html = (
        '<html><body><main class="wrapper shell"><div class="headline">Welcome back</div>'
        '<div class="login-copy">Log in to continue</div>'
        '<section><button type="button">Continue with Facebook</button></section>'
        '<form id="login"><input type="text" name="email" /><input type="password" name="password" /><button type="submit">Log in</button></form>'
        "</main></body></html>"
    )

    async def fake_render_html(_: str):
        return browser_result(
            noisy_final_html,
            interaction_used=True,
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
    partial_html = (
        '<html><body><section class="login_card wrapper">'
        '<input type="text" name="credential" placeholder="Enter email or mobile" />'
        '<button type="button">Request OTP</button>'
        '<a href="/password">Sign in with password</a>'
        "</section></body></html>"
    )

    async def fake_render_html(_: str):
        return browser_result(partial_html, snapshots=[BrowserMarkupSnapshot("settled_dom", partial_html, False, False)])

    monkeypatch.setattr("app.services.analysis.render_html", fake_render_html)

    result = asyncio.run(analyze_url("https://example.com/login"))

    assert result.detection.status == "partial_auth_surface"
    assert result.detection.snippet is not None
    assert "Request OTP" in result.detection.snippet


def test_analyze_url_falls_back_to_static_when_browser_fails(monkeypatch) -> None:
    static_html = login_form_html()

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
    rendered_html = challenge_html()

    async def fake_render_html(_: str):
        return browser_result(rendered_html, snapshots=[BrowserMarkupSnapshot("settled_dom", rendered_html, False, False)])

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
