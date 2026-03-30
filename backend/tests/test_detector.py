from types import SimpleNamespace

from app.services.detector import detect_auth_component


def test_detector_finds_login_form() -> None:
    html = """
    <html>
      <body>
        <form id="login-form">
          <input type="text" name="username" />
          <input type="password" name="password" />
          <button type="submit">Sign in</button>
        </form>
      </body>
    </html>
    """

    result = detect_auth_component(html)

    assert result.found is True
    assert "password_input" in result.signals
    assert "submit_button" in result.signals
    assert result.snippet is not None
    assert "\n" in result.snippet
    assert '<input name="username" type="text"/>' in result.snippet


def test_detector_finds_password_only_candidate() -> None:
    html = """
    <div class="auth-panel">
      <div>
        <label>Password</label>
        <input type="password" />
      </div>
    </div>
    """

    result = detect_auth_component(html)

    assert result.found is True
    assert "password_input" in result.signals


def test_detector_returns_not_found_when_no_auth_component_exists() -> None:
    html = """
    <html>
      <body>
        <section>
          <h1>Welcome</h1>
          <p>This page has no login form.</p>
        </section>
      </body>
    </html>
    """

    result = detect_auth_component(html)

    assert result.found is False
    assert result.snippet is None


def test_detector_preserves_nested_indentation() -> None:
    html = """
    <section class="auth-shell">
      <div class="panel">
        <form>
          <div class="field-group">
            <label>Email</label>
            <input type="email" name="email" />
          </div>
          <div class="field-group">
            <label>Password</label>
            <input type="password" name="password" />
          </div>
          <button type="submit">Login</button>
        </form>
      </div>
    </section>
    """

    result = detect_auth_component(html)

    assert result.snippet is not None
    assert '<div class="field-group">' in result.snippet
    assert result.snippet.count("\n") >= 6


def test_detector_truncation_keeps_multiline_format(monkeypatch) -> None:
    html = """
    <form id="login-form">
      <div class="field-row">
        <label>Email address</label>
        <input type="email" name="email" placeholder="you@example.com" autocomplete="email" />
      </div>
      <div class="field-row">
        <label>Password</label>
        <input type="password" name="password" placeholder="Password" autocomplete="current-password" />
      </div>
      <button type="submit">Sign in</button>
    </form>
    """

    monkeypatch.setattr(
        "app.services.detector.get_settings",
        lambda: SimpleNamespace(max_snippet_length=120),
    )

    result = detect_auth_component(html)

    assert result.snippet is not None
    assert result.snippet.endswith("\n...")
    assert "\n" in result.snippet
