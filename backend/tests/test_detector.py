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
    assert result.status == "found"
    assert result.surface_type == "form"
    assert "password_input" in result.signals
    assert result.fields
    assert result.snippet is not None


def test_detector_marks_sso_surface_as_partial() -> None:
    html = """
    <section aria-label="Sign in">
      <button type="button">Continue with Google</button>
      <button type="button">Continue with Apple</button>
    </section>
    """

    result = detect_auth_component(html)

    assert result.found is False
    assert result.status == "partial_auth_surface"
    assert result.providers == ["Apple", "Google"]
    assert result.surface_type == "sso_only"


def test_detector_avoids_search_form_false_positive() -> None:
    html = """
    <form action="/search" class="search-form">
      <input type="text" name="q" placeholder="Search products" />
      <button type="submit">Search</button>
    </form>
    """

    result = detect_auth_component(html)

    assert result.found is False
    assert result.status == "not_found"


def test_detector_handles_modal_auth_surface() -> None:
    html = """
    <div role="dialog" aria-modal="true" aria-label="Log in">
      <input type="email" name="email" placeholder="Email" />
      <button type="button">Continue</button>
    </div>
    """

    result = detect_auth_component(html)

    assert result.status == "partial_auth_surface"
    assert result.surface_type == "dialog"
    assert any(action.type == "continue" for action in result.actions)


def test_detector_returns_full_form_markup_without_truncation(monkeypatch) -> None:
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
    assert result.snippet.startswith("<form")
    assert result.snippet.endswith("</form>")
    assert "\n" in result.snippet
    assert 'autocomplete="current-password"' in result.snippet
