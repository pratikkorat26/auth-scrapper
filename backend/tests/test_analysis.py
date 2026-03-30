from app.services.analysis import analyze_url, _should_use_browser_fallback


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


def test_auth_intent_page_without_shell_can_trigger_browser_fallback() -> None:
    html = """
    <html>
      <head><title>Welcome to Reddit</title></head>
      <body>Skip to main content<script src="/a.js"></script><script src="/b.js"></script><script src="/c.js"></script><script src="/d.js"></script></body>
    </html>
    """

    class Detection:
        status = "not_found"

    assert _should_use_browser_fallback("https://www.reddit.com/login/", html, Detection()) is True


def test_partial_surface_triggers_browser_fallback() -> None:
    html = """
    <section aria-label="Sign in">
      <button type="button">Continue with Google</button>
      <script src="/auth.js"></script>
      <script src="/main.js"></script>
    </section>
    """

    class Detection:
        status = "partial_auth_surface"

    assert _should_use_browser_fallback("https://example.com/login", html, Detection()) is True


def test_analyze_url_uses_browser_fallback(monkeypatch) -> None:
    static_html = """
    <html>
      <body>
        <div id="root"></div>
        <script src="/assets/runtime.js"></script>
        <script src="/assets/main.js"></script>
      </body>
    </html>
    """
    rendered_html = """
    <html>
      <body>
        <form>
          <input type="email" name="email" />
          <input type="password" name="password" />
          <button type="submit">Login</button>
        </form>
      </body>
    </html>
    """

    async def fake_fetch_html(_: str) -> str:
        return static_html

    async def fake_render_html(_: str):
        from app.services.browser import BrowserRenderResult

        return BrowserRenderResult(html=rendered_html, interaction_used=True)

    monkeypatch.setattr("app.services.analysis.fetch_html", fake_fetch_html)
    monkeypatch.setattr("app.services.analysis.render_html", fake_render_html)

    result = __import__("asyncio").run(analyze_url("https://example.com/login"))

    assert result.detection.found is True
    assert result.analysis_mode == "browser_fallback"
    assert result.fallback_used is True
    assert result.interaction_used is True
